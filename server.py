from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request

from ollama_embeddings import OllamaClient


@dataclass(frozen=True)
class ArticleRow:
    source: str
    category: str
    url: str
    published_time: str
    content: str


def load_articles(csv_path: str) -> List[ArticleRow]:
    rows: List[ArticleRow] = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            # Support both your old schema and the new schema
            if "published_time" not in row and "content" in row and "category" in row and "url" in row:
                rows.append(
                    ArticleRow(
                        source=row.get("source") or "unknown",
                        category=row.get("category") or "unknown",
                        url=row.get("url") or "",
                        published_time=row.get("published_time") or "",
                        content=row.get("content") or "",
                    )
                )
            else:
                rows.append(
                    ArticleRow(
                        source=row.get("source") or "unknown",
                        category=row.get("category") or "unknown",
                        url=row.get("url") or "",
                        published_time=row.get("published_time") or "",
                        content=row.get("content") or "",
                    )
                )
    return rows


def _cache_key(url: str, model: str) -> str:
    h = hashlib.sha256(f"{model}|{url}".encode("utf-8")).hexdigest()
    return h


def create_app() -> Flask:
    app = Flask(__name__)

    csv_path = os.environ.get("NEWS_CSV", "news.csv")
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    embed_model = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    cache_path = Path(os.environ.get("EMBED_CACHE", "embeddings_cache.jsonl"))

    ollama = OllamaClient(base_url=ollama_url)

    @app.get("/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "news_csv": csv_path,
                "ollama_url": ollama_url,
                "embed_model": embed_model,
                "embed_cache": str(cache_path),
            }
        )

    @app.get("/articles")
    def articles():
        limit = int(request.args.get("limit", "50"))
        category = request.args.get("category")
        rows = load_articles(csv_path)
        if category:
            rows = [r for r in rows if r.category.lower() == category.lower()]
        rows = rows[: max(0, limit)]
        return jsonify(
            [
                {
                    "source": r.source,
                    "category": r.category,
                    "url": r.url,
                    "published_time": r.published_time,
                    "content_chars": len(r.content),
                }
                for r in rows
            ]
        )

    def _load_cache() -> Dict[str, Any]:
        cache: Dict[str, Any] = {}
        if not cache_path.exists():
            return cache
        with cache_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                k = obj.get("key")
                if isinstance(k, str):
                    cache[k] = obj
        return cache

    def _append_cache(obj: Dict[str, Any]) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    @app.post("/embed")
    def embed():
        """
        Body:
          - url: optional (embed matching article from CSV)
          - text: optional (embed arbitrary text)
          - model: optional (defaults to OLLAMA_EMBED_MODEL)
          - force: optional bool (re-embed even if cached)
        """
        body = request.get_json(force=True, silent=False) or {}
        url: Optional[str] = body.get("url")
        text: Optional[str] = body.get("text")
        model: str = body.get("model") or embed_model
        force: bool = bool(body.get("force", False))

        if not text:
            if not url:
                return jsonify({"error": "Provide either 'text' or 'url'"}), 400
            rows = load_articles(csv_path)
            match = next((r for r in rows if r.url == url), None)
            if not match:
                return jsonify({"error": f"url not found in csv: {url}"}), 404
            text = match.content

        if url:
            key = _cache_key(url, model)
            cache = _load_cache()
            if (not force) and key in cache:
                return jsonify({"cached": True, **cache[key]})
        else:
            key = None

        res = ollama.embed(text=text, model=model)
        out = {
            "key": key,
            "model": res.model,
            "dims": len(res.embedding),
            "embedding": res.embedding,
            "url": url,
        }
        if key:
            _append_cache(out)
        return jsonify({"cached": False, **out})

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)


