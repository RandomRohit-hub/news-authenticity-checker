from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, List, Optional

import requests


@dataclass(frozen=True)
class EmbeddingResult:
    model: str
    embedding: List[float]


class OllamaClient:
    """
    Minimal client for Ollama embeddings.

    Requires Ollama running locally (default): http://localhost:11434
    """

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")

    def embed(self, text: str, model: str = "nomic-embed-text") -> EmbeddingResult:
        url = f"{self.base_url}/api/embeddings"
        payload = {"model": model, "prompt": text}
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        emb = data.get("embedding")
        if not isinstance(emb, list):
            raise ValueError(f"Unexpected Ollama response (no embedding list): {json.dumps(data)[:500]}")
        return EmbeddingResult(model=model, embedding=[float(x) for x in emb])


