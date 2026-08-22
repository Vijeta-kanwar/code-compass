import uuid
import re
import time

from codecompass.models import QueryLog
from sqlalchemy.orm import Session

from codecompass.config import get_settings
from codecompass.embedding.client import embed_query
from codecompass.repositories.chunk_store import ChunkStore
from codecompass.embedding.llm import generate_answer
from dataclasses import dataclass

@dataclass
class AnswerResult:
    answer: str
    citations: list[dict]
    latency_ms: int

SYSTEM_PROMPT = """
You are a code assistant answering questions about a specific codebase.

Rules:
- Answer ONLY from the code excerpts provided below.
- Cite every claim with the excerpt number in square brackets, e.g. [1].
- If the excerpts do not contain the answer, say so plainly.
- Do not guess.
- Do not use general knowledge about how such systems usually work.
- Be concise.
- Prefer naming the specific function or class that does the work.
"""

def retrieve_chunks(
    session: Session,
    repository_id: uuid.UUID,
    question: str,
):
    settings = get_settings()

    # 1. Convert question into an embedding
    query_vector = embed_query(question)

    # 2. Search the repository
    store = ChunkStore(session)

    results = store.search_by_vector(
        repository_id=repository_id,
        query_vector=query_vector,
        limit=settings.answer_top_k,
    )

    # 3. No results
    if not results:
        return []

    # 4. Threshold check
    best_distance = results[0][1]

    if best_distance > settings.answer_max_distance:
        return []

    return results

def build_context(
    results: list[tuple],
    token_budget: int,
):
    context_parts = []
    used_chunks = []
    used_tokens = 0

    for chunk, distance in results:
        chunk_tokens = chunk.token_count

        # Don't exceed the context budget
        if used_tokens + chunk_tokens > token_budget:
            break

        citation_number = len(used_chunks) + 1

        context_parts.append(
            f"[{citation_number}] "
            f"{chunk.source_file.path}:"
            f"{chunk.start_line}-{chunk.end_line}\n"
            f"{chunk.content}"
        )

        used_chunks.append(chunk)
        used_tokens += chunk_tokens

    context = "\n\n".join(context_parts)

    return context, used_chunks

def build_user_prompt(
    question: str,
    context: str,
) -> str:
    return f"""Question: {question}

Code excerpts:

{context}
"""

def generate_grounded_answer(
    question: str,
    context: str,
) -> str:
    user_prompt = build_user_prompt(
        question=question,
        context=context,
    )

    answer = generate_answer(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )

    if not answer.strip():
        raise RuntimeError("LLM returned an empty answer.")

    return answer

def extract_citations(
    answer: str,
    used_chunks: list,
) -> list[dict]:
    numbers = re.findall(r"\[(\d+)\]", answer)

    citations = []
    seen = set()

    for number in numbers:
        n = int(number)

        # Ignore citations that don't exist
        if n < 1 or n > len(used_chunks):
            continue

        # Avoid duplicate citations
        if n in seen:
            continue

        seen.add(n)

        chunk = used_chunks[n - 1]

        citations.append(
            {
                "n": n,
                "file_path": chunk.source_file.path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
            }
        )

    return citations

def save_query_log(
    session: Session,
    repository_id: uuid.UUID,
    question: str,
    answer: str,
    used_chunks: list,
    latency_ms: int,
) -> None:
    log = QueryLog(
        repository_id=repository_id,
        question=question,
        answer=answer,
        retrieved_chunk_ids=[chunk.id for chunk in used_chunks],
        latency_ms=latency_ms,
    )

    session.add(log)
    session.commit()

def answer_question(
    session: Session,
    repository_id: uuid.UUID,
    question: str,
) -> AnswerResult:
    """Retrieve, ground, answer, and return verified citations."""

    start = time.perf_counter()

    settings = get_settings()

    # 1. Retrieve relevant chunks
    results = retrieve_chunks(
        session=session,
        repository_id=repository_id,
        question=question,
    )

    # 2. No sufficiently relevant results
    if not results:
        latency_ms = int(
            (time.perf_counter() - start) * 1000
        )

        return AnswerResult(
            answer="I couldn't find this in the repository.",
            citations=[],
            latency_ms=latency_ms,
        )

    # 3. Build context within token budget
    context, used_chunks = build_context(
        results=results,
        token_budget=settings.answer_context_token_budget,
    )

    # 4. No chunks fit within the context budget
    if not used_chunks:
        latency_ms = int(
            (time.perf_counter() - start) * 1000
        )

        return AnswerResult(
            answer="I couldn't find this in the repository.",
            citations=[],
            latency_ms=latency_ms,
        )

    answer = generate_grounded_answer(
    question=question,
    context=context,
    )

    citations = extract_citations(
    answer=answer,
    used_chunks=used_chunks,
    )

    latency_ms = int(
    (time.perf_counter() - start) * 1000
    )

    save_query_log(
    session=session,
    repository_id=repository_id,
    question=question,
    answer=answer,
    used_chunks=used_chunks,
    latency_ms=latency_ms,
    )

    return AnswerResult(
        answer=answer,
        citations=citations,
        latency_ms=latency_ms,
    )