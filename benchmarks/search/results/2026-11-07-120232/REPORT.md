# Local search benchmark

Run started at 2026-11-07T12:02:33.974912-05:00. Source commit `729a66234675e4c1a3f28d38468a35053c3ae645`.

The corpus contains 50,000 synthetic questions, 64 authors and 16 weighted topics. Question content averages 1163 UTF-8 bytes and ranges from 685 to 1655 bytes. Both engines passed expected-count and ordered-ID checks for all 72 request cases.

The run measured the real HTTP API at 2, 3 offered requests/s, with 16 client workers, 3 rounds of 30 seconds per engine and rate, and 100 warmup requests per engine. Engine order alternated between rounds.

Host platform `macOS-15.7.9-arm64-arm-64bit`. Docker VM has 8 CPUs and 7.65 GiB RAM. MySQL 8.4.13 and Elasticsearch 7.17.4 each have a two-CPU, 2-GiB container limit. MySQL buffer pool is 512 MiB. ES and the application each use a 768-MiB heap. The database connection pool has 16 connections.

Primary latency includes time waiting for a client worker, HTTP execution and JSON validation. Worker queue wait and scheduler wakeup delay are recorded separately. Percentiles are nearest rank across successful requests. Errors are reported separately. Pooled percentiles below use all requests across rounds, rather than averaging round percentiles.

| Offered RPS | Engine | Requests | Errors | P50 ms | P95 ms | P99 ms | HTTP P95 ms | Queue P95 ms | Scheduler P95 ms | Achieved RPS |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | mysql | 180 | 0 | 262.16 | 317.67 | 333.17 | 310.91 | 0.27 | 10.09 | 2.02 |
| 2 | elasticsearch | 180 | 0 | 26.60 | 38.96 | 63.20 | 34.40 | 0.44 | 10.05 | 2.03 |
| 3 | mysql | 270 | 0 | 240.32 | 298.10 | 347.59 | 293.51 | 0.28 | 5.05 | 3.01 |
| 3 | elasticsearch | 270 | 0 | 23.05 | 29.77 | 37.12 | 25.78 | 0.30 | 5.06 | 3.03 |

## Round variation

| Offered RPS | Round | Engine | P95 ms | Errors | Achieved RPS |
| ---: | ---: | --- | ---: | ---: | ---: |
| 2 | 1 | mysql | 314.98 | 0 | 2.02 |
| 2 | 1 | elasticsearch | 41.51 | 0 | 2.03 |
| 2 | 2 | elasticsearch | 37.07 | 0 | 2.03 |
| 2 | 2 | mysql | 322.32 | 0 | 2.01 |
| 2 | 3 | mysql | 317.67 | 0 | 2.01 |
| 2 | 3 | elasticsearch | 44.89 | 0 | 2.03 |
| 3 | 1 | mysql | 296.21 | 0 | 3.01 |
| 3 | 1 | elasticsearch | 32.68 | 0 | 3.03 |
| 3 | 2 | elasticsearch | 29.04 | 0 | 3.03 |
| 3 | 2 | mysql | 293.27 | 0 | 3.01 |
| 3 | 3 | mysql | 304.48 | 0 | 3.01 |
| 3 | 3 | elasticsearch | 26.75 | 0 | 3.03 |

## Interpretation

At 3 requests/s, pooled ES P95 was 90.0% lower than the MySQL baseline (298.10 ms versus 29.77 ms, a 10.01x latency ratio). Both paths completed all requests without application errors or response-count mismatches. Client queue wait at P95 remained below 5 ms for both engines. This is the highest tested rate where both paths completed at least 98% of the offered rate in every round and met the error and queue criteria. ES P95 was lower in every round.

## Scope of the result

This is a warmed local benchmark on a shared development machine with synthetic data. It measures the existing substring-based MySQL implementation and the existing ES implementation. Both return exact totals and hydrate author information from MySQL. The workload uses common single-token semantics and explicit ID ordering. Relevance ranking, general natural-language equivalence, cold starts, maximum throughput and production service guarantees require separate evaluation.

The raw request timings, generated dataset, query definitions, correctness checks, environment details and per-round summary are retained beside this report.

## Resume wording

```latex
\item Integrated \tech{Elasticsearch} with a custom analyzer and a MySQL-to-ES sync pipeline, achieving end-to-end search P95 of $\sim$29.8\,ms versus a $\sim$298.1\,ms MySQL baseline at 3 requests/s in a local benchmark on 50k synthetic questions
```
