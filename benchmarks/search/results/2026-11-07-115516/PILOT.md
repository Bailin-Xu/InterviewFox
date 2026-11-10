# Overload pilot

This pilot was intentionally stopped after the initial workload exceeded the MySQL baseline capacity. The planned 60-requests/s profile was not executed. This directory contains completed rounds only and is separate from the stable benchmark.

| Engine | Offered RPS | Round | Requests | Errors | Achieved RPS | Scheduled P95 ms | HTTP P95 ms | Scheduled-to-worker P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mysql | 20 | 1 | 400 | 0 | 4.09 | 76135.85 | 5619.30 | 72597.27 |
| elasticsearch | 20 | 1 | 400 | 0 | 20.02 | 31.05 | 23.65 | 10.18 |
| elasticsearch | 20 | 2 | 400 | 0 | 20.03 | 28.37 | 19.86 | 10.13 |

A container stats sample observed MySQL at 200.34% CPU against its two-CPU limit. The original pilot metric named queue_ms includes scheduler wakeup delay and worker queue wait. The subsequent stable harness separates these values. The complete original harness, dataset, environment and raw completed request rows are retained here.

These overloaded scheduled latencies are not used as the normal search latency claim in the resume.
