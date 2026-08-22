import logging

from google import genai
from google.genai import types

from codecompass.config import get_settings
from codecompass.embedding.client import QuotaExhausted, _is_rate_limit

logger = logging.getLogger(__name__)


def generate_answer(system_prompt: str, user_prompt: str) -> str:
    settings = get_settings()
    client = genai.Client(api_key=settings.google_api_key)

    try:
        response = client.models.generate_content(
            model=settings.llm_model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.1,
                max_output_tokens=1024,
            ),
        )
    except Exception as exc:
        if _is_rate_limit(exc):
            raise QuotaExhausted(
                "Gemini generation quota is exhausted."
            ) from exc
        raise

    return response.text or ""