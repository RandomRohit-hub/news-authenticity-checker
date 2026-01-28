from __future__ import annotations

import argparse
import csv
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from dateutil import parser as dtparser
from playwright.sync_api import Page, sync_playwright


BASE_URL = "https://timesofindia.indiatimes.com"


DEFAULT_VALID_CATEGORIES = {
    # TOI top-level sections commonly seen on nav/home
    "india",
    "world",
    "business",
    "sports",
    "technology",
    "tech",
    "health-fitness",
    "science",
    "environment",
    "education",
}


@dataclass(frozen=True)
class Article:
    source: str
    category: str
    url: str
    published_time: str  # ISO8601
    content: str


def _clean_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _safe_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def get_categories(page: Page, allowed: set[str]) -> list[str]:
    """
    Returns category URLs. We whitelist categories by slug to avoid random site links.
    """
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)

    hrefs = page.eval_on_selector_all(
        "a[href^='/']",
        "els => els.map(e => e.getAttribute('href')).filter(Boolean)",
    )
    categories: set[str] = set()

    for href in hrefs:
        if not isinstance(href, str):
            continue
        if any(bad in href for bad in ["/topic/", "/search", "/videos", "/photos", "?utm", "#"]):
            continue
        # keep only clean top-level paths: /world, /sports, etc.
        if href.count("/") == 1 and href != "/":
            slug = href.strip("/").lower()
            if (not allowed) or ("*" in allowed) or (slug in allowed):
                categories.add(BASE_URL + href)

    return sorted(categories)


def fallback_categories(allowed: set[str]) -> list[str]:
    """
    If nav parsing yields nothing (common when sites render links dynamically),
    fall back to constructing category URLs directly from known section slugs.
    """
    slugs = sorted(allowed) if allowed else sorted(DEFAULT_VALID_CATEGORIES)
    return [f"{BASE_URL}/{s}" for s in slugs]


def get_article_links(page: Page) -> list[str]:
    hrefs = page.eval_on_selector_all(
        "a[href*='/articleshow/']",
        "els => Array.from(new Set(els.map(e => e.getAttribute('href')).filter(Boolean)))",
    )
    urls: set[str] = set()
    for href in hrefs:
        if isinstance(href, str) and href.startswith("/"):
            urls.add(BASE_URL + href.split("?")[0])
        elif isinstance(href, str) and href.startswith("http"):
            urls.add(href.split("?")[0])
    return list(urls)


def _jsonld_candidates(page: Page) -> list[dict[str, Any]]:
    raw_list = page.eval_on_selector_all(
        "script[type='application/ld+json']",
        "els => els.map(e => e.textContent).filter(Boolean)",
    )
    out: list[dict[str, Any]] = []
    for raw in raw_list:
        if not isinstance(raw, str):
            continue
        raw = raw.strip()
        try:
            data = json.loads(raw)
        except Exception:
            # Sometimes JSON-LD is invalid; skip quietly
            continue
        if isinstance(data, dict):
            out.append(data)
        elif isinstance(data, list):
            out.extend([x for x in data if isinstance(x, dict)])
    return out


def _find_newsarticle_jsonld(page: Page) -> Optional[dict[str, Any]]:
    for obj in _jsonld_candidates(page):
        t = obj.get("@type")
        if t == "NewsArticle" or (isinstance(t, list) and "NewsArticle" in t):
            return obj
        # Sometimes wrapped in @graph
        graph = obj.get("@graph")
        if isinstance(graph, list):
            for g in graph:
                if isinstance(g, dict):
                    gt = g.get("@type")
                    if gt == "NewsArticle" or (isinstance(gt, list) and "NewsArticle" in gt):
                        return g
    return None


def extract_published_dt(page: Page) -> Optional[datetime]:
    """
    Prefer JSON-LD timestamps (datePublished/dateModified), fallback to regex.
    """
    obj = _find_newsarticle_jsonld(page)
    for key in ("datePublished", "dateModified"):
        if obj and isinstance(obj.get(key), str):
            try:
                return dtparser.parse(obj[key])
            except Exception:
                pass

    text = page.inner_text("body")
    m = re.search(r"(Updated|Published):\s*(.*?IST)", text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(2).strip(), "%b %d, %Y, %H:%M IST").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def extract_article_text(page: Page) -> str:
    """
    Prefer JSON-LD articleBody; fallback to DOM paragraphs.
    """
    obj = _find_newsarticle_jsonld(page)
    body = obj.get("articleBody") if obj else None
    if isinstance(body, str) and body.strip():
        return _clean_ws(body)

    paragraphs = page.locator("article p").all_inner_texts()
    if not paragraphs:
        paragraphs = page.locator("div p").all_inner_texts()
    return _clean_ws(" ".join(paragraphs))


def _category_slug_from_url(category_url: str) -> str:
    slug = category_url.replace(BASE_URL, "").strip("/").split("/")[0].lower()
    return slug or "unknown"


def normalize_category(slug: str) -> str:
    """
    Map site section slugs into your ML-friendly buckets.
    """
    s = (slug or "").lower()
    if s in {"world"}:
        return "world"
    if s in {"business"}:
        return "business"
    if s in {"sports"}:
        return "sports"
    if s in {"technology", "tech", "science"}:
        return "technology"
    if s in {"health", "health-fitness"}:
        return "health"
    if s in {"india", "politics"}:
        return "politics"
    return s or "unknown"


def scrape(
    *,
    output_csv: str,
    window_hours: Optional[int],
    window_days: Optional[int],
    headless: bool,
    allowed_categories: set[str],
    max_articles_per_category: int,
    min_chars: int,
    delay_s: float,
) -> int:
    now = datetime.now(timezone.utc)
    if window_hours is not None:
        cutoff = now - timedelta(hours=window_hours)
    elif window_days is not None:
        cutoff = now - timedelta(days=window_days)
    else:
        cutoff = now - timedelta(days=7)

    written = 0
    seen_urls: set[str] = set()
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source", "category", "url", "published_time", "content"])

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            )

            categories = get_categories(page, allowed_categories)
            if not categories:
                categories = fallback_categories(allowed_categories)
            print(f"Using {len(categories)} categories: {[c.replace(BASE_URL + '/', '') for c in categories]}")

            for category_url in categories:
                slug = _category_slug_from_url(category_url)
                category = normalize_category(slug)
                print(f"\nCategory: {category} ({category_url})")

                try:
                    page.goto(category_url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(1500)
                except Exception:
                    continue

                links = get_article_links(page)
                print(f"Found {len(links)} article links")

                count = 0
                for url in links:
                    if count >= max_articles_per_category:
                        break
                    if url in seen_urls:
                        continue
                    # Reduce cross-section noise: keep links that appear to belong to this section
                    path = url.replace(BASE_URL, "")
                    if slug and not path.startswith(f"/{slug}/"):
                        continue
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_timeout(1000)

                        dt = extract_published_dt(page)
                        if not dt:
                            continue
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        if dt < cutoff:
                            continue

                        content = extract_article_text(page)
                        if len(content) < min_chars:
                            continue

                        w.writerow(["timesofindia", category, url, _safe_iso(dt), content])
                        seen_urls.add(url)
                        written += 1
                        count += 1
                        print("Saved:", url)
                        time.sleep(max(delay_s, 0.0))
                    except Exception:
                        continue

            browser.close()

    print(f"\nDONE: wrote {written} rows to {output_csv}")
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description="Scrape full-length TOI news articles with time-window filtering.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--last-hours", type=int, default=None, help="Only keep articles from last N hours (e.g. 24).")
    g.add_argument("--last-days", type=int, default=7, help="Only keep articles from last N days (default: 7).")

    ap.add_argument("--out", default="news.csv", help="Output CSV path.")
    ap.add_argument("--headless", action="store_true", help="Run browser headless.")
    ap.add_argument("--max-per-category", type=int, default=200, help="Safety cap per category.")
    ap.add_argument("--min-chars", type=int, default=800, help="Minimum content length to save.")
    ap.add_argument("--delay", type=float, default=1.5, help="Delay between article requests (seconds).")
    ap.add_argument(
        "--categories",
        default=",".join(sorted(DEFAULT_VALID_CATEGORIES)),
        help="Comma-separated category slugs to include.",
    )

    args = ap.parse_args()
    allowed = {c.strip().lower() for c in args.categories.split(",") if c.strip()}

    scrape(
        output_csv=args.out,
        window_hours=args.last_hours,
        window_days=None if args.last_hours is not None else args.last_days,
        headless=args.headless,
        allowed_categories=allowed,
        max_articles_per_category=args.max_per_category,
        min_chars=args.min_chars,
        delay_s=args.delay,
    )


if __name__ == "__main__":
    main()


