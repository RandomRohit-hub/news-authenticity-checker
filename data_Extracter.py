from playwright.sync_api import sync_playwright
import csv
from datetime import datetime, timedelta
import re
import time

BASE_URL = "https://timesofindia.indiatimes.com"
MAX_ARTICLES_PER_CATEGORY = 5000  # safety cap

def get_all_categories(page):
    links = page.locator("a[href^='/']").all()
    categories = set()

    for link in links:
        href = link.get_attribute("href")
        if href and href.count("/") == 2:
            categories.add(BASE_URL + href)

    return list(categories)


def extract_article_links(page):
    links = page.locator("a[href*='/articleshow/']").all()
    urls = set()

    for link in links:
        href = link.get_attribute("href")
        if href and href.startswith("/"):
            urls.add(BASE_URL + href)

    return list(urls)


def extract_publish_time(page):
    text = page.inner_text("body")
    match = re.search(r"(Updated|Published):\s*(.*?IST)", text)
    if not match:
        return None

    try:
        return datetime.strptime(match.group(2).strip(), "%b %d, %Y, %H:%M IST")
    except:
        return None


def extract_article_content(page):
    paragraphs = page.locator("article p").all_inner_texts()
    if not paragraphs:
        paragraphs = page.locator("div p").all_inner_texts()
    return " ".join(paragraphs).strip()


now = datetime.now()
last_24_hours = now - timedelta(hours=24)

with open("last_24_hours_news.csv", "w", newline="", encoding="utf-8") as file:
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

        # 1️⃣ Open homepage
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("a", timeout=10000)

        categories = get_all_categories(page)
        print(f"Found {len(categories)} categories")

        for category_url in categories:
            print(f"\n📂 Category: {category_url}")
            page.goto(category_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("a", timeout=10000)

            article_links = extract_article_links(page)
            count = 0

            for article_url in article_links:
                if count >= MAX_ARTICLES_PER_CATEGORY:
                    break

                try:
                    page.goto(article_url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_selector("p", timeout=8000)

                    publish_time = extract_publish_time(page)
                    if not publish_time or publish_time < last_24_hours:
                        continue

                    content = extract_article_content(page)
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

                    time.sleep(2)

                except:
                    continue

        browser.close()

print("\n✅ LAST 24 HOURS NEWS DATASET CREATED")
