import sys
import uuid

import requests
import yaml

from codecompass.db import SessionLocal
from codecompass.models import SourceFile
from codecompass.repositories.chunk_store import ChunkStore

from eval.query_embedding_cache import get_query_embedding


TOP_K = 5
API_URL = "http://localhost:8000"


def load_questions():
    with open("eval/questions.yaml", "r") as f:
        return yaml.safe_load(f)


def validate_citation(
    session,
    repository_id: uuid.UUID,
    citation: dict,
) -> bool:
    """Check that a citation points to a real indexed file and valid lines."""

    source_file = session.query(SourceFile).filter(
        SourceFile.repository_id == repository_id,
        SourceFile.path == citation["file_path"],
    ).first()

    if source_file is None:
        return False

    start_line = citation["start_line"]
    end_line = citation["end_line"]

    return (
        1 <= start_line <= end_line
        and end_line <= source_file.line_count
    )


def evaluate(repository_id: uuid.UUID, api_key: str):
    questions = load_questions()

    hits = 0
    reciprocal_ranks = []

    total_citations = 0
    valid_citations = 0

    with SessionLocal() as session:
        store = ChunkStore(session)

        for i, item in enumerate(questions, start=1):
            question = item["q"]
            expected_files = set(item["files"])

            # ---------------------------------------------------------
            # Existing retrieval evaluation
            # ---------------------------------------------------------

            query_vector = get_query_embedding(question)

            results = store.search_by_vector(
                repository_id=repository_id,
                query_vector=query_vector,
                limit=TOP_K,
            )

            retrieved_files = [
                chunk.source_file.path
                for chunk, distance in results
            ]

            first_correct_rank = None

            for rank, path in enumerate(retrieved_files, start=1):
                if path in expected_files:
                    first_correct_rank = rank
                    break

            if first_correct_rank is None:
                reciprocal_ranks.append(0.0)
            else:
                reciprocal_ranks.append(
                    1.0 / first_correct_rank
                )

            hit = bool(
                expected_files.intersection(retrieved_files)
            )

            if hit:
                hits += 1

            print(f"\nQ{i}: {question}")
            print(f"Expected: {sorted(expected_files)}")

            print("Retrieved:")
            for rank, path in enumerate(
                retrieved_files,
                start=1,
            ):
                print(f"  {rank}. {path}")

            print(
                "RETRIEVAL:",
                "HIT" if hit else "MISS",
            )

            # ---------------------------------------------------------
            # Actual /ask evaluation
            # ---------------------------------------------------------

            response = requests.post(
                f"{API_URL}/repositories/{repository_id}/ask",
                headers={
                    "X-API-Key": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "question": question,
                },
                timeout=120,
            )

            if response.status_code != 200:
                print(
                    f"ASK ERROR: HTTP {response.status_code}"
                )
                print(response.text)

                continue

            data = response.json()

            citations = data.get("citations", [])

            print(
                f"Citations returned: {len(citations)}"
            )

            # ---------------------------------------------------------
            # Citation validity
            # ---------------------------------------------------------

            question_valid = True

            for citation in citations:
                total_citations += 1

                valid = validate_citation(
                    session=session,
                    repository_id=repository_id,
                    citation=citation,
                )

                if valid:
                    valid_citations += 1
                else:
                    question_valid = False

                print(
                    f"  citation [{citation.get('n')}]: "
                    f"{citation.get('file_path')}:"
                    f"{citation.get('start_line')}-"
                    f"{citation.get('end_line')} "
                    f"→ {'VALID' if valid else 'INVALID'}"
                )

            print(
                "CITATIONS:",
                "VALID" if question_valid else "INVALID",
            )

    recall = hits / len(questions)

    mrr = (
        sum(reciprocal_ranks)
        / len(reciprocal_ranks)
    )

    if total_citations == 0:
          print("Citation validity: n/a")
    else:
          citation_rate = valid_citations / total_citations
          print(
        f"Citation validity: "
        f"{valid_citations}/{total_citations} = {citation_rate:.1%}"
    )

    print("\n" + "=" * 60)

    print(
        f"Recall@{TOP_K}: "
        f"{hits}/{len(questions)} = {recall:.1%}"
    )

    print(
        f"MRR@{TOP_K}: {mrr:.3f}"
    )

    print(
        f"Citation validity: "
        f"{valid_citations}/{total_citations} "
        f"= {citation_validity:.1%}"
    )

    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: "
            "python eval/run_eval.py "
            "<repository_id> <api_key>"
        )
        sys.exit(1)

    repository_id = uuid.UUID(sys.argv[1])
    api_key = sys.argv[2]

    evaluate(
        repository_id=repository_id,
        api_key=api_key,
    )