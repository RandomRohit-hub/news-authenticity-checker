# Fake News Analyzer (live news → full articles → embeddings → API)

This repo is a **real-world news ingestion + analysis** skeleton:

- **Playwright** collects *full* article content (not just headlines)
- **Time-window filtering** (last 24h / last 7 days)
- Output stored in **CSV** for NLP/ML pipelines
- **Flask API** loads the CSV and can generate **Ollama embeddings**

## Setup (Conda)

Activate your environment (example: `globalenv`) and install deps:

```bash
pip install -r requirements.txt
playwright install
```

## Scrape live news (Times of India)

Last 24 hours:

```bash
python news_scraper.py --last-hours 24 --out news.csv --headless
```

Last 7 days (default):

```bash
python news_scraper.py --last-days 7 --out news.csv --headless
```

The CSV schema is:

- `source`
- `category`
- `url`
- `published_time` (ISO8601)
- `content` (full article text)

## Run Flask API (testing + embeddings)

Start Ollama locally, then run:

```bash
set NEWS_CSV=news.csv
set OLLAMA_URL=http://localhost:11434
set OLLAMA_EMBED_MODEL=nomic-embed-text
python server.py
```

### Useful endpoints

- `GET /health`
- `GET /articles?limit=20&category=world`
- `POST /embed` (embed by `url` from CSV or arbitrary `text`)

Example:

```bash
curl -X POST http://localhost:5000/embed ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://.../articleshow/...\",\"model\":\"nomic-embed-text\"}"
```
