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


def _is_rate_limit(exc: Exception) -> bool:
    # String matching is fragile — the SDK's own error type would be better.
    # TODO: catch google.genai.errors.ClientError and check status_code == 429.
    text = str(exc)
    return "429" in text or "RESOURCE_EXHAUSTED" in text


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a batch for storage. Raises QuotaExhausted when retries run out."""
    settings = get_settings()
    client = genai.Client(api_key=settings.google_api_key)

    last_error = ""

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
            if not _is_rate_limit(exc):
                raise

            last_error = str(exc)

            # Exponential backoff with jitter. The jitter matters: without it,
            # every retrying client wakes at the same instant and re-collides.
            delay = min(2 ** attempt, 90) + random.uniform(0, 1)

            # Log Google's own message — it names which quota was hit (RPM, TPM
            # or RPD), and each one calls for a completely different fix.
            logger.warning(
                "rate limited on %d texts, attempt %d, sleeping %.1fs: %s",
                len(texts), attempt + 1, delay, last_error[:500],
            )
            time.sleep(delay)

    raise QuotaExhausted(
        f"Still rate limited after {settings.embedding_max_retries} attempts. "
        f"Last error: {last_error[:300]}"
    )


def embed_query(text: str) -> list[float]:
    """Embed a user's question for search.

    RETRIEVAL_QUERY, not RETRIEVAL_DOCUMENT: the model places questions near the
    passages that answer them, which is not the same space as similar questions.
    """
    settings = get_settings()
    client = genai.Client(api_key=settings.google_api_key)

    try:
        result = client.models.embed_content(
            model=settings.embedding_model,
            contents=[text],
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=settings.embedding_dimensions,
            ),
        )
    except Exception as exc:
        if _is_rate_limit(exc):
            raise QuotaExhausted(
                "Gemini embedding quota is currently exhausted."
            ) from exc
        raise

    return _unit(result.embeddings[0].values)