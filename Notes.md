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


