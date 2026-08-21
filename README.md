# Code Compass

Semantic search for Python codebases. Index a repository, ask a question in natural language, and get back the files and functions most relevant to your question.

## Why Code Compass?

Grep is great when you already know what you're looking for.

But what if you know what the code *does* without knowing the function name, file name, or exact phrase? That's where keyword search starts to fall short.

Code Compass indexes Python source into meaningful code chunks, creates embeddings for those chunks, and lets you search the codebase by meaning rather than exact keywords.

## Quickstart

**Prerequisites**

- Docker + Docker Compose
- Python 3.12+
- A Google API key for embeddings

Clone the repository:

```bash
git clone https://github.com/Vijeta-kanwar/code-compass.git
cd code-compass
```

Create the environment file and add your API key:

```bash
cp .env.example .env
# then edit .env:
# GOOGLE_API_KEY=your_api_key_here
```

Create a virtual environment and install the dependencies. This is needed because Alembic runs on the host, not inside the container:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Start the application and run the migrations:

```bash
docker compose up -d
alembic upgrade head
```

Index a repository:

```bash
curl -X POST http://localhost:8000/repositories \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://github.com/Vijeta-kanwar/code-compass"}'
```

The response returns a job ID and a repository ID. Indexing runs in the background — poll it:

```bash
curl http://localhost:8000/jobs/<JOB_ID>
```

Once the job reports `ready`, search the repository:

```bash
curl "http://localhost:8000/repositories/<REPO_ID>/search?q=how+are+rate+limits+handled"
```

```json
[
  {
    "symbol_name": "embed_query",
    "file_path": "codecompass/embedding/client.py",
    "start_line": 79,
    "end_line": 104,
    "distance": 0.28229932294491866
  },
  {
    "symbol_name": null,
    "file_path": "codecompass/services/embedding_service.py",
    "start_line": 1,
    "end_line": 13,
    "distance": 0.28317378263629656
  },
  {
    "symbol_name": null,
    "file_path": "codecompass/services/search_service.py",
    "start_line": 1,
    "end_line": 8,
    "distance": 0.3065702549731427
  }
]
```

Results are ordered by cosine distance, so **lower `distance` means a closer match**.

## Architecture

The indexing and retrieval pipeline is intentionally straightforward:

```
clone → walk → hash → AST chunk → embed → pgvector
                                             ↓
                             question → embed → search → ranked chunks
```

When indexing, Code Compass clones the repository, walks its Python files, hashes their contents, and parses them into AST-based chunks. Each chunk is embedded and stored in PostgreSQL using pgvector.

When a user asks a question, the question is embedded using the same embedding model. The resulting vector is compared against the stored vectors and the closest code chunks are returned.

### Project layers

| Layer | Responsibility |
|---|---|
| `api/` | HTTP endpoints and request/response handling |
| `services/` | Application logic and workflows |
| `repositories/` | Database access and queries |
| `parsing/` | Python parsing and AST-based chunking |
| `embedding/` | Embedding provider integration |
| `ingestion/` | Repository cloning and file walking |
| `models.py` | Database models |

A core design principle is that the parser doesn't know anything about the database. It produces plain parsed data, and persistence happens outside the parsing layer.

## Design Decisions

### PostgreSQL + pgvector

**Decision:** Use PostgreSQL with pgvector instead of a dedicated vector database.

**Reasoning:** Code Compass needs both relational metadata and vector similarity search. Keeping them together gives us transactions, SQL filtering, and vector search without introducing another datastore.

**Tradeoff:** A dedicated vector database could make sense at larger scale, but would add operational complexity that isn't necessary here.

### AST-based chunking

**Decision:** Chunk Python code using the AST rather than fixed-size text windows.

**Reasoning:** A function is a meaningful unit of code. When a function is retrieved, the result maps naturally back to a real source boundary instead of an arbitrary slice of text.

**Tradeoff:** Very large AST nodes can still produce oversized chunks and aren't automatically split yet.

### Context headers

**Decision:** Add contextual headers to `embedded_text`, but never modify `content`.

**Reasoning:** The embedding model benefits from knowing where a chunk came from. The actual source content has to remain untouched so retrieved results and citations point at real source code.

```
embedded_text → retrieval context + source content
content       → original source code, byte for byte
```

**Tradeoff:** The text used for embedding differs from the text displayed as source.

### Content hashing

**Decision:** Hash file contents for incremental indexing.

**Reasoning:** If a file hasn't changed, there's no reason to parse and embed it again. Hashing makes repeated indexing much cheaper. Hashing content rather than modification time matters here — a fresh clone gives every file a new mtime.

**Tradeoff:** The stored hash is a claim that chunks exist, so it's written last in the same transaction as the chunks it vouches for.

### 768-dimensional embeddings

**Decision:** Use 768-dimensional embeddings instead of the model's native 3072-dimensional output.

**Reasoning:** This is a hard pgvector constraint, not a preference. pgvector's HNSW and IVFFlat indexes support vectors up to 2000 dimensions. A 3072-dimensional column would be legal but unindexable, so every query would fall back to a sequential scan.

**Tradeoff:** Lower-dimensional embeddings may lose some representational capacity.

### No LangChain

**Decision:** Use direct SDK/API calls instead of LangChain.

**Reasoning:** Code Compass is meant to make the retrieval pipeline understandable. Cloning, parsing, chunking, embedding, storage, and search are all explicit pieces of the application.

**Tradeoff:** More orchestration code to maintain directly.

### No dedicated queue

**Decision:** Keep indexing as an in-process background job for this version.

**Reasoning:** The project had a roughly ten-day implementation budget, so operating a durable worker and queue wasn't worth the scope for a first version.

**Tradeoff:** An in-process job dies if the API restarts. A startup reaper marks such jobs failed so they don't block the repository, but the real fix is a worker backed by a queue.

## Concepts

- **Content-addressed indexing** — file contents are hashed so unchanged files can be identified and skipped on later runs.
- **AST chunking** — source is parsed into syntactic units such as functions, instead of split at arbitrary character boundaries.
- **Recall@5** — the percentage of evaluation questions where at least one expected file appears in the top five results.
- **MRR@5** — how high the first relevant result appears. A hit at rank 1 contributes more than one at rank 5.
- **Vector search** — code chunks and questions become vectors; retrieval returns the chunks closest to the question vector.

## Results

The retrieval evaluation contains 20 golden questions covering different parts of the codebase.

| Change | Recall@5 | MRR@5 |
|---|---|---|
| Baseline — vector search | 85% | 0.522 |
| Exclude `app.py` | 95% | 0.522 |
| Dedup — max 2 chunks/file | 95% | 0.522 |
| Dedup — max 1 chunk/file | 95% | 0.546 |

The most interesting result was the deduplication experiment. Recall stayed at 95% while MRR improved from 0.522 to 0.546 — deduplication didn't help the system discover additional answers, it moved already-relevant results higher in the ranking.

The intermediate `max_per_file=2` setting was useful precisely because it had no measurable effect. Adding the mechanism wasn't enough; the stricter cap was what changed the ranking.

One caveat: the 85% → 95% step isn't a perfectly controlled comparison, because `search_service.py` was written between those two runs. The deduplication comparison is clean — the pipeline was identical and only the per-file cap changed.

## Known Limitations

- **In-process indexing** — a running indexing job disappears if the API process restarts.
- **No durable worker queue** — the long-term fix is a dedicated worker backed by a queue.
- **Oversized chunks** — very large AST nodes aren't automatically split yet.
- **Embedding quotas** — free-tier API limits shaped several implementation and testing decisions.
- **Small evaluation set** — 20 questions catch obvious retrieval problems but don't support strong statistical claims.
- **Retrieval only** — Code Compass returns relevant code chunks. It doesn't yet generate a natural-language answer from them.

## Running Tests

```bash
pytest
```

## Project Layout

```
code-compass/
├── codecompass/
│   ├── api/
│   ├── embedding/
│   ├── ingestion/
│   ├── parsing/
│   ├── repositories/
│   ├── services/
│   ├── models.py
│   └── main.py
├── tests/
├── migrations/
├── eval/
├── NOTES.md
├── docker-compose.yml
├── .env.example
└── README.md
```

## Status

**Working:** repository indexing, incremental indexing, AST-based chunking, embeddings, pgvector search, per-file result deduplication, and retrieval evaluation.

**Current result:** 95% Recall@5 / 0.546 MRR@5 on the 20-question evaluation set.

**Next:** natural-language answer generation, a durable worker/queue for indexing, better handling of oversized chunks, and a larger evaluation set.