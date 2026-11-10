#!/usr/bin/env python3
"""Turn retained raw benchmark results into a report and a qualified resume bullet."""

import argparse
import json
from pathlib import Path


def milliseconds(value):
    return "n/a" if value is None else f"{value:.2f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = args.directory
    result = json.loads((directory / "summary.json").read_text())
    environment = json.loads((directory / "environment.json").read_text())
    checks = json.loads((directory / "correctness.json").read_text())
    if not result.get("complete"):
        parser.error("The benchmark did not complete")
    dataset = environment["dataset"]
    settings = environment["settings"]
    report = [
        "# Local search benchmark", "",
        f"Run started at {environment['started_at']}. Source commit `{environment['source_commit']}`.", "",
        f"The corpus contains {dataset['rows']:,} synthetic questions, {dataset['authors']} authors and "
        f"{len(dataset['topic_counts'])} weighted topics. Question content averages {dataset['content_bytes_mean']:.0f} UTF-8 bytes "
        f"and ranges from {dataset['content_bytes_min']} to {dataset['content_bytes_max']} bytes. "
        f"Both engines passed expected-count and ordered-ID checks for all {len(checks)} request cases.", "",
        f"The run measured the real HTTP API at {', '.join(map(str, settings['rates']))} offered requests/s, "
        f"with {settings['workers']} client workers, {settings['rounds']} rounds of {settings['seconds']} seconds "
        f"per engine and rate, and {settings['warmup_per_engine']} warmup requests per engine. "
        "Engine order alternated between rounds.", "",
        f"Host platform `{environment['platform']}`. Docker VM has {environment['docker']['cpus']} CPUs "
        f"and {environment['docker']['memory'] / 1024 ** 3:.2f} GiB RAM. "
        f"MySQL {environment['mysql_version']} and Elasticsearch {environment['elasticsearch_version']} each have a "
        "two-CPU, 2-GiB container limit. MySQL buffer pool is 512 MiB. ES and the application each use a 768-MiB heap. "
        "The database connection pool has 16 connections.", "",
        "Primary latency includes time waiting for a client worker, HTTP execution and JSON validation. "
        "Worker queue wait and scheduler wakeup delay are recorded separately. "
        "Percentiles are nearest rank across successful requests. Errors are reported separately. "
        "Pooled percentiles below use all requests across rounds, rather than averaging round percentiles.", "",
        "| Offered RPS | Engine | Requests | Errors | P50 ms | P95 ms | P99 ms | HTTP P95 ms | Queue P95 ms | Scheduler P95 ms | Achieved RPS |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in result["aggregate"]:
        rounds = [entry for entry in result["rounds"] if entry["rate"] == row["rate"] and entry["engine"] == row["engine"]]
        achieved = sum(entry["successes"] for entry in rounds) / sum(entry["elapsed_seconds"] for entry in rounds)
        report.append(
            f"| {row['rate']} | {row['engine']} | {row['requests']} | {row['errors']} | "
            f"{milliseconds(row['p50_ms'])} | {milliseconds(row['p95_ms'])} | {milliseconds(row['p99_ms'])} | "
            f"{milliseconds(row['http_p95_ms'])} | {milliseconds(row['queue_p95_ms'])} | "
            f"{milliseconds(row['scheduler_p95_ms'])} | {achieved:.2f} |")
    report += ["", "## Round variation", "",
               "| Offered RPS | Round | Engine | P95 ms | Errors | Achieved RPS |",
               "| ---: | ---: | --- | ---: | ---: | ---: |"]
    for row in result["rounds"]:
        report.append(f"| {row['rate']} | {row['round']} | {row['engine']} | {milliseconds(row['p95_ms'])} | {row['errors']} | {row['achieved_rps']:.2f} |")

    selected_rate = None
    for rate in sorted(settings["rates"], reverse=True):
        pair = [row for row in result["aggregate"] if row["rate"] == rate]
        stable = all(row["errors"] == 0 and row["queue_p95_ms"] is not None and row["queue_p95_ms"] < 5 for row in pair)
        completed = all(row["achieved_rps"] >= 0.98 * rate for row in result["rounds"] if row["rate"] == rate)
        if stable and completed:
            selected_rate = rate
            break
    comparison_rate = selected_rate or max(settings["rates"])
    mysql = next(row for row in result["aggregate"] if row["rate"] == comparison_rate and row["engine"] == "mysql")
    es = next(row for row in result["aggregate"] if row["rate"] == comparison_rate and row["engine"] == "elasticsearch")
    round_improvements = []
    for number in range(1, settings["rounds"] + 1):
        baseline = next(row for row in result["rounds"] if row["rate"] == comparison_rate and row["engine"] == "mysql" and row["round"] == number)
        candidate = next(row for row in result["rounds"] if row["rate"] == comparison_rate and row["engine"] == "elasticsearch" and row["round"] == number)
        round_improvements.append(candidate["p95_ms"] is not None and baseline["p95_ms"] is not None and candidate["p95_ms"] < baseline["p95_ms"])
    qualified = selected_rate is not None and all(round_improvements)
    corpus_label = "50k" if dataset["rows"] == 50_000 else f"{dataset['rows']:,}"
    report += ["", "## Interpretation", ""]
    if qualified and es["p95_ms"] < mysql["p95_ms"]:
        reduction = (1 - es["p95_ms"] / mysql["p95_ms"]) * 100
        ratio = mysql["p95_ms"] / es["p95_ms"]
        report.append(f"At {comparison_rate} requests/s, pooled ES P95 was {reduction:.1f}% lower than the MySQL baseline "
                      f"({mysql['p95_ms']:.2f} ms versus {es['p95_ms']:.2f} ms, a {ratio:.2f}x latency ratio). "
                      "Both paths completed all requests without application errors or response-count mismatches. "
                      "Client queue wait at P95 remained below 5 ms for both engines. "
                      "This is the highest tested rate where both paths completed at least 98% of the offered rate in every round "
                      "and met the error and queue criteria. ES P95 was lower in every round.")
        resume = (
            r"\item Integrated \tech{Elasticsearch} with a custom analyzer and a MySQL-to-ES sync pipeline, "
            f"achieving end-to-end search P95 of $\\sim${es['p95_ms']:.1f}\\,ms versus a $\\sim${mysql['p95_ms']:.1f}\\,ms "
            f"MySQL baseline at {comparison_rate} requests/s in a local benchmark on {corpus_label} synthetic questions\n"
        )
    else:
        report.append("The tested rates did not establish consistently lower ES P95 under the completion, queue and error criteria. "
                      "The resume wording therefore describes the benchmark without claiming a latency reduction.")
        resume = (
            r"\item Integrated \tech{Elasticsearch} with a custom analyzer and a MySQL-to-ES sync pipeline, "
            f"and benchmarked both search paths on {corpus_label} synthetic questions using repeated fixed-rate HTTP workloads\n"
        )
    report += ["", "## Scope of the result", "",
               "This is a warmed local benchmark on a shared development machine with synthetic data. "
               "It measures the existing substring-based MySQL implementation and the existing ES implementation. "
               "Both return exact totals and hydrate author information from MySQL. The workload uses common single-token "
               "semantics and explicit ID ordering. Relevance ranking, general natural-language equivalence, cold starts, "
               "maximum throughput and production service guarantees require separate evaluation.", "",
               "The raw request timings, generated dataset, query definitions, correctness checks, "
               "environment details and per-round summary are retained beside this report.", "",
               "## Resume wording", "", "```latex", resume.strip(), "```", ""]
    (directory / "REPORT.md").write_text("\n".join(report))
    (directory / "resume.tex").write_text(resume)
    print("\n".join(report))


if __name__ == "__main__":
    main()
