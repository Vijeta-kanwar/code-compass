import sys
import uuid

import yaml

from codecompass.db import SessionLocal
from codecompass.repositories.chunk_store import ChunkStore

from eval.query_embedding_cache import get_query_embedding


TOP_K = 5


def load_questions():
    with open("eval/questions.yaml", "r") as f:
        return yaml.safe_load(f)

reciprocal_ranks = []
def evaluate(repository_id: uuid.UUID):
    questions = load_questions()
    hits = 0

    with SessionLocal() as session:
        store = ChunkStore(session)

        for i, item in enumerate(questions, start=1):
            question = item["q"]
            expected_files = set(item["files"])

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
                  reciprocal_ranks.append(1.0 / first_correct_rank)
            hit = bool(expected_files.intersection(retrieved_files))

            if hit:
                hits += 1

            print(f"\nQ{i}: {question}")
            print(f"Expected: {sorted(expected_files)}")
            print("Retrieved:")

            for rank, path in enumerate(retrieved_files, start=1):
                print(f"  {rank}. {path}")

            print("RESULT:", "HIT" if hit else "MISS")

    recall = hits / len(questions)

    print("\n" + "=" * 50)
    print(f"Recall@{TOP_K}: {hits}/{len(questions)} = {recall:.1%}")
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)
    print(f"MRR@{TOP_K}: {mrr:.3f}")
    print("=" * 50)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python eval/run_eval.py <repository_id>")
        sys.exit(1)

    repository_id = uuid.UUID(sys.argv[1])
    evaluate(repository_id)
