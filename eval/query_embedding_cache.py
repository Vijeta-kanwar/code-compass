import hashlib
import json
from pathlib import Path

from codecompass.embedding.client import embed_query


CACHE_FILE = Path(__file__).parent / "query_embedding_cache.json"


def _key(text: str) -> str:
    normalized = " ".join(text.strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _load_cache() -> dict[str, list[float]]:
    if not CACHE_FILE.exists():
        return {}

    with CACHE_FILE.open("r") as f:
        return json.load(f)


def _save_cache(cache: dict[str, list[float]]) -> None:
    with CACHE_FILE.open("w") as f:
        json.dump(cache, f)


def get_query_embedding(text: str) -> list[float]:
    cache = _load_cache()
    key = _key(text)

    if key in cache:
        print("cache hit:", text)
        return cache[key]

    print("cache miss:", text)

    vector = embed_query(text)
    cache[key] = vector
    _save_cache(cache)

    return vector
