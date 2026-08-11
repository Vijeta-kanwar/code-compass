import logging
import math
import random
import time

from google import genai
from google.genai import types

from codecompass.config import get_settings

logger = logging.getLogger(__name__)


class QuotaExhausted(RuntimeError):
    """Rate limited beyond what's worth waiting out in-process."""


def _unit(vector: list[float]) -> list[float]:
    """Scale to unit length.

    Truncating a 3072-dim embedding to 768 does not preserve norm, and any
    inner-product search would silently mis-rank without this.
    """
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else vector


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a batch for storage. Raises QuotaExhausted when retries run out."""
    settings = get_settings()
    client = genai.Client(api_key=settings.google_api_key)

    for attempt in range(settings.embedding_max_retries):
        try:
            result = client.models.embed_content(
                model=settings.embedding_model,
                contents=texts,
                config=types.EmbedContentConfig(
                    # Documents and queries are embedded differently on purpose.
                    task_type="RETRIEVAL_DOCUMENT",
                    output_dimensionality=settings.embedding_dimensions,
                ),
            )
            return [_unit(e.values) for e in result.embeddings]

        except Exception as exc:
            if "429" not in str(exc) and "RESOURCE_EXHAUSTED" not in str(exc):
                raise
            # Exponential backoff with jitter. The jitter matters: without it,
            # every retrying client wakes at the same instant and re-collides.
            delay = min(2 ** attempt, 90) + random.uniform(0, 1)
            logger.warning("rate limited, sleeping %.1fs (attempt %d)", delay, attempt + 1)
            time.sleep(delay)

    raise QuotaExhausted(
        f"Still rate limited after {settings.embedding_max_retries} attempts."
    )