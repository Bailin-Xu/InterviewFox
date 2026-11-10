# Search benchmark

Run from the repository root with Python 3.9+, Java 11, Maven and Docker running.
The harness creates disposable containers with random names and loopback ports,
uses a separate temporary application configuration and removes the containers
after the run. Existing application databases and Elasticsearch indices are not
used. Images remain in Docker's local image cache.

```bash
mvn -B -ntp clean package -Dtest=QuestionSearchControllerTest
python3 benchmarks/search/run.py
```

Default settings generate 50,000 synthetic questions and measure the real
`POST /api/question/list/page/vo` endpoint at 2 and 3 offered requests per
second. Each engine runs three 30-second rounds at each rate, with 16 client
workers and the same deterministic request schedule. Engine order alternates
between rounds. Both engines receive 100 warmup requests before measurement.
The database and index are fully populated before correctness checks and load.

The initial 20-requests/s pilot saturated the two-CPU MySQL baseline and created
a large client backlog. Its completed raw rounds and original harness are
retained separately. The stable comparison therefore uses 2 and 3 requests/s.
The stable harness records scheduler wakeup delay separately from worker queue
wait. This keeps operating-system timer jitter distinct from worker saturation.

The corpus has 64 authors, 16 technical topics with unequal frequencies, three
difficulty tags, distinct question titles, varied question text and answers.
The output includes the generated SQL compressed with gzip. Dataset generation
uses a fixed seed and records a checksum of the inserted rows.

The 72-query workload covers common and less frequent single-token terms,
tag-filtered searches, pages 1/2/5 and no-match queries. All queries request ten
results sorted by ID. Before load, expected hit counts and ordered page IDs are
checked against both engines. This comparison deliberately uses queries whose
semantics agree between substring matching and token search. It does not measure
relevance ranking, natural-language quality or accent normalization.

MySQL 8.4 and Elasticsearch 7.17.4 each have a two-CPU, 2-GiB container limit.
MySQL's buffer pool is 512 MiB, ES's heap is 768 MiB, and the application runs
with a 768-MiB heap and a 16-connection database pool. ES uses one shard and zero
replicas. SQL and request logging are disabled equally for both paths. The
existing one-second sync polling remains active during both measurements.
The measured response includes exact total counts, question serialization and
author hydration from MySQL. No additional application result cache is enabled.
This is a warmed local comparison on a shared host, not a cold-cache test or a
measurement of maximum sustainable throughput.

The client submits at a fixed arrival rate rather than submitting the next
request only when the previous request finishes. Primary latency starts at the
scheduled arrival and ends after JSON validation, including client queue wait.
Raw results also separate HTTP duration, worker queue wait and scheduler wakeup
delay. Percentiles use nearest
rank over successful requests; errors and achieved throughput are reported
separately. Inspect queue wait, round variation and errors before quoting a P95.

Results are saved under `benchmarks/search/results/<local timestamp>/`:

- `environment.json` records versions, resource limits, build and harness hashes.
- `dataset.sql.gz` and `queries.json` reproduce the corpus and workload.
- `correctness.json` records the pre-load checks.
- `requests.csv` records every measured request, including errors.
- `summary.json` contains per-round and pooled metrics for each rate and engine.
- `application.log` contains startup and synchronization logs.

Generate the report and resume wording after a completed run:

```bash
python3 benchmarks/search/report.py benchmarks/search/results/<local timestamp>
```

The report includes both tested arrival rates and all round metrics. Numerical
resume wording uses the highest stable tested rate and requires zero errors,
at least 98% of the offered throughput in every round, less than 5 ms of client
queue wait at P95 for both engines, and lower ES P95 in every round. It retains
the synthetic-data and local-environment qualifications.

To change the workload, use explicit flags and retain them with the report:

```bash
python3 benchmarks/search/run.py --rows 50000 --rates 2 3 --seconds 30 --rounds 3 --workers 16 --warmup 100
```

Container startup and full synchronization can take several minutes. A failed
correctness check stops the run instead of producing a performance claim.

## Retained measurements

- [Stable comparison and resume wording](results/2026-11-07-120232/REPORT.md)
- [Overload pilot](results/2026-11-07-115516/PILOT.md)

The stable run completed 900 measured requests with zero errors. At 3 requests/s,
pooled end-to-end P95 was 298.10 ms for MySQL and 29.77 ms for Elasticsearch.
These values describe the documented local synthetic workload. The raw files
and exact harness snapshots are retained in the corresponding result folders.
