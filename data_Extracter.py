from playwright.sync_api import sync_playwright
import csv
from datetime import datetime, timedelta
import re
import time

BASE_URL = "https://timesofindia.indiatimes.com"
MAX_ARTICLES_PER_CATEGORY = 5000   # realistic safety cap

# ------------------ HELPERS ------------------

def get_categories(page):
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(4000)

    links = page.locator("a[href^='/']").all()
    categories = set()

    INVALID_KEYWORDS = [
        "/topic/",
        "/search",
        "/videos",
        "/photos",
        "?utm",
        "#"
    ]

    for link in links:
        href = link.get_attribute("href")
        if not href:
            continue

        # Reject unwanted links
        if any(bad in href for bad in INVALID_KEYWORDS):
            continue

        # Accept only clean category paths like /world, /business
        if href.count("/") == 1 and href != "/":
            categories.add(BASE_URL + href)

    return sorted(categories)


def get_article_links(page):
    """Extract article links from category page"""
    links = page.locator("a[href*='/articleshow/']").all()
    urls = set()

    for link in links:
        href = link.get_attribute("href")
        if href and href.startswith("/"):
            urls.add(BASE_URL + href)

    return list(urls)


def extract_publish_time(page):
    """Extract article publish/update time"""
    text = page.inner_text("body")

    match = re.search(r"(Updated|Published):\s*(.*?IST)", text)
    if not match:
        return None

    try:
        return datetime.strptime(match.group(2).strip(), "%b %d, %Y, %H:%M IST")
    except:
        return None


def extract_article_text(page):
    """Extract full article content"""
    paragraphs = page.locator("article p").all_inner_texts()

    if not paragraphs:
        paragraphs = page.locator("div p").all_inner_texts()

    return " ".join(paragraphs).strip()


# ------------------ MAIN ------------------

now = datetime.now()
last_1_week = now - timedelta(days=7)   # ✅ CHANGE HERE (1 WEEK)

with open("last_1_week_news.csv", "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow(["category", "url", "published_time", "content"])

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )

        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        )

        # 1️⃣ Get categories
        categories = get_categories(page)
        print(f"✅ Found {len(categories)} categories")

        for category_url in categories:
            print(f"\n📂 Category: {category_url}")

            page.goto(category_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)

            article_links = get_article_links(page)
            print(f"🔗 Found {len(article_links)} article links")

            count = 0

            for article_url in article_links:
                if count >= MAX_ARTICLES_PER_CATEGORY:
                    break

                try:
                    page.goto(article_url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(3000)

                    publish_time = extract_publish_time(page)
                    if not publish_time or publish_time < last_1_week:
                        continue

                    content = extract_article_text(page)
                    if len(content) < 500:
                        continue

                    writer.writerow([
                        category_url,
                        article_url,
                        publish_time.strftime("%Y-%m-%d %H:%M"),
                        content
                    ])

                    count += 1
                    print("✔ Saved")

                    time.sleep(2)   # anti-blocking

                except:
                    continue

        browser.close()

print("\n✅ DONE: last_1_week_news.csv created")
