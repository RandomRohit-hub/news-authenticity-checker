from playwright.sync_api import sync_playwright

URLS = [
    "https://timesofindia.indiatimes.com/city/bhopal",
    "https://timesofindia.indiatimes.com/city/crime-news",
    "https://timesofindia.indiatimes.com/business/budget",
]

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"]
    )

    page = browser.new_page(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"
    )

    all_text = []

    for url in URLS:
        try:
            print(f"Loading: {url}")

            page.goto(
                url,
                wait_until="domcontentloaded",  # ✅ faster
                timeout=60000                  # ✅ 60 seconds
            )

            page.wait_for_timeout(5000)

            text = page.inner_text("body")
            all_text.append(f"\n--- {url} ---\n{text}")

        except Exception as e:
            print(f"Failed to load {url}")
            print(e)

    browser.close()

with open("NEWS_DATA.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(all_text))

print("Done")
