"""ChromaDB vector DB connection and collection management."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb
import httpx
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings, Space
from chromadb.config import Settings
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR") or str(BACKEND_DIR / "chroma_db")
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME") or "festivals"


class OllamaEmbeddingFunction(EmbeddingFunction[Documents]):
    """Embeddings from a local Ollama `/api/embed` endpoint (free, no external service)."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3-embedding:4b",
        timeout: float = 120.0,
        chunk_size: int = 25,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.chunk_size = chunk_size

    def __call__(self, input: Documents) -> Embeddings:
        if not input:
            return []
        out: Embeddings = []
        with httpx.Client(timeout=self.timeout) as client:
            for i in range(0, len(input), self.chunk_size):
                resp = client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": self.model, "input": list(input[i : i + self.chunk_size])},
                )
                resp.raise_for_status()
                embeddings = resp.json().get("embeddings")
                if not isinstance(embeddings, list):
                    raise RuntimeError(f"Unexpected Ollama embed response: {resp.text[:200]}")
                out.extend(embeddings)
        return out

    @staticmethod
    def name() -> str:
        return "httpx_ollama"

    def default_space(self) -> Space:
        return "cosine"

    def supported_spaces(self) -> list[Space]:
        return ["cosine", "l2", "ip"]

    def get_config(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "model": self.model,
            "timeout": self.timeout,
            "chunk_size": self.chunk_size,
        }

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> OllamaEmbeddingFunction:
        return OllamaEmbeddingFunction(
            base_url=str(config.get("base_url") or "http://localhost:11434"),
            model=str(config.get("model") or "qwen3-embedding:4b"),
            timeout=float(config.get("timeout") or 120.0),
            chunk_size=int(config.get("chunk_size") or 25),
        )


def _build_embedding_function() -> EmbeddingFunction[Documents] | None:
    """Ollama embeddings when OLLAMA_EMBED_MODEL is set, else Chroma's built-in default."""
    model = (os.getenv("OLLAMA_EMBED_MODEL") or "").strip()
    if not model:
        return None
    base = (os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").strip()
    return OllamaEmbeddingFunction(base_url=base, model=model)


@lru_cache(maxsize=1)
def get_chroma_client() -> ClientAPI:
    Path(CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=CHROMA_PERSIST_DIR, settings=Settings(anonymized_telemetry=False)
    )


def get_festivals_collection() -> Collection:
    """Get or create the collection holding festival documents + metadata."""
    kwargs: dict[str, Any] = {
        "name": CHROMA_COLLECTION_NAME,
        "metadata": {"hnsw:space": "cosine"},
    }
    ef = _build_embedding_function()
    if ef is not None:
        kwargs["embedding_function"] = ef
    return get_chroma_client().get_or_create_collection(**kwargs)


def init_db() -> Collection:
    return get_festivals_collection()
