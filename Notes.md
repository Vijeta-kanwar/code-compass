# Notes

## Free-tier embedding constraints (measured 2026-08-11)
- gemini-embedding-001 free tier: 100 RPM, 30K TPM, 1000 RPD
- The SDK issues one request per text — passing a list to `contents` does not
  batch server-side. Batch size therefore controls transaction size, not
  request rate.
- Observed ~3.4 requests per chunk once 429 retries are counted, so retries are
  quota-negative: each one spends a request from the daily 1000.
- psf/requests = 743 chunks, which does not fit in one day's quota. Switched to
  indexing this repo instead.
- Consequence: ingestion is designed to be resumable rather than transactional.
  `WHERE embedding IS NULL` is the resume point.

## Known limitations
- BackgroundTasks run in the API process; a restart kills any in-flight job.
  Mitigated by a startup reaper. Correct fix is a separate worker + queue.
- Oversized chunks are not split (chunker pass 6 skipped).
- Typing-protocol stubs with empty bodies get embedded but can never answer
  anything. Candidate filter — measure on Day 9 before adding it.


## Vector-only retrieval, observed 2026-08-12 (116 chunks, own repo)

"how are rate limits handled"
  - correct answer (embed_documents retry loop) ranked 6th
  - ranks 2-3 were import-only module chunks, matching on the filename in
    their context header
  - spread 0.354-0.411

"QuotaExhausted" (exact identifier)
  - rank 1, distance 0.240, clear gap to rank 2 (0.337)
  - CloneFailed ranked 3rd: structurally identical two-line exception class.
    Semantic similarity working correctly and being unhelpful.
  - NOTE: the expected failure of vector search on identifiers did NOT
    reproduce at this scale — rare tokens dominate small chunks.

"where are chunk line numbers calculated"
  - 4 of top 10 were test functions; the real answer ranked 3rd and 4th
  - test names paraphrase natural-language questions, so they embed well and
    contain no implementation
  - spread 0.269-0.325

Candidates to measure on Day 9:
1. exclude tests from results by default
2. drop or down-weight import-only module chunks
3. lexical search + RRF