from playwright.sync_api import sync_playwright

NEWS_SITES = {
    "TOI_Bhopal": "https://timesofindia.indiatimes.com/city/bhopal",
    "NDTV_India": "https://www.ndtv.com/india",
    "HindustanTimes": "https://www.hindustantimes.com/india-news",
    "IndianExpress": "https://indianexpress.com/section/india/",
    "TheHindu": "https://www.thehindu.com/news/national/",
    "BBC_India": "https://www.bbc.com/news/world/asia/india",
    "Reuters_India": "https://www.reuters.com/world/india/"
}

def clean_text(text):
    lines = text.splitlines()
    clean_lines = [line.strip() for line in lines if len(line.strip()) > 40]
    return " ".join(clean_lines)


with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"]
    )

    page = browser.new_page(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"
    )

    collected_data = []

    for source, url in NEWS_SITES.items():
        try:
            print(f"Scraping: {source}")

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            page.wait_for_timeout(4000)

            raw_text = page.inner_text("body")
            text = clean_text(raw_text)

            collected_data.append(
                f"\nSOURCE: {source}\nURL: {url}\n{text}\n"
            )

        except Exception as e:
            print(f"❌ Failed: {source} | {e}")

    browser.close()


with open("REAL_NEWS_DATA.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(collected_data))

print("✅ News data collection completed")
