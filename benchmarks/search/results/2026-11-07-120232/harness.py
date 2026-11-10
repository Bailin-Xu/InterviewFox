#!/usr/bin/env python3
"""Reproducible HTTP comparison on disposable MySQL and Elasticsearch instances."""

import argparse
import concurrent.futures
import csv
import gzip
import hashlib
import http.client
import json
import math
import platform
import random
import secrets
import socket
import statistics
import subprocess
import tempfile
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
INDEX = "interviewfox-question-v1"
SEED = 20261107
TOPICS = {
    "redis": 8, "kafka": 6, "mysql": 6, "postgresql": 4,
    "elasticsearch": 4, "docker": 4, "kubernetes": 3, "spring": 5,
    "kotlin": 3, "python": 4, "rabbitmq": 2, "mongodb": 2,
    "nginx": 2, "terraform": 2, "prometheus": 2, "grpc": 2,
}
ASPECTS = ["replication", "concurrency", "indexing", "recovery", "transactions", "deployment", "monitoring", "pagination"]
LEVELS = ["beginner", "intermediate", "advanced"]
SENTENCES = [
    "A service processes incoming requests across several independent worker instances.",
    "The team must investigate inconsistent observations after a network interruption.",
    "Compare the behavior during normal operation with the behavior after a process restart.",
    "Describe how resource limits affect the maximum sustainable arrival rate.",
    "Explain how you would identify contention using measurements and execution traces.",
    "Discuss the ordering guarantees required when messages arrive more than once.",
    "Describe an experiment that distinguishes a slow dependency from an overloaded worker.",
    "Consider a failure that occurs after a write succeeds but before its acknowledgement arrives.",
    "Identify the observable signals needed to detect stale results and incomplete processing.",
    "Explain the tradeoffs between additional storage and the cost of repeated computation.",
    "Describe the assumptions needed to recover safely after a partial operation.",
    "Discuss how an uneven distribution of incoming work changes the resource requirements.",
]


def command(args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def sql_string(value):
    return "'" + str(value).replace("'", "''") + "'"


def dataset(path, count):
    rng = random.Random(SEED)
    histogram = Counter()
    content_bytes = []
    digest = hashlib.sha256()
    with gzip.open(path, "wt", encoding="utf-8") as output:
        output.write("USE interviewfox;\n")
        authors = [f"({i},'bench{i}','benchmark-only','Author {i}')" for i in range(1, 65)]
        output.write("INSERT INTO user (id,userAccount,userPassword,userName) VALUES " + ",".join(authors) + ";\n")
        batch = []
        for question_id in range(1, count + 1):
            topic = rng.choices(list(TOPICS), weights=list(TOPICS.values()))[0]
            level = rng.choice(LEVELS)
            aspect = rng.choice(ASPECTS)
            title = f"{topic.title()} {aspect}: incident {question_id:05d}"
            content = f"How would you diagnose {topic} behavior in this {aspect} scenario? "
            content += " ".join(rng.choices(SENTENCES, k=rng.randint(8, 18)))
            answer = " ".join(rng.sample(SENTENCES, k=rng.randint(3, 6)))
            tags = json.dumps([topic, level, "backend"])
            author = rng.randint(1, 64)
            row = f"({question_id},{sql_string(title)},{sql_string(content)},{sql_string(tags)},{sql_string(answer)},{author},'2026-01-01','2026-01-01','2026-01-01')"
            digest.update(row.encode())
            batch.append(row)
            histogram[topic] += 1
            histogram[(topic, level)] += 1
            content_bytes.append(len(content.encode()))
            if len(batch) == 500 or question_id == count:
                output.write("INSERT INTO question (id,title,content,tags,answer,userId,editTime,createTime,updateTime) VALUES " + ",".join(batch) + ";\n")
                batch = []

    cases = []
    for topic in TOPICS:
        for level in [None] + LEVELS:
            body = {"searchText": topic, "current": rng.choice([1, 2, 5]), "pageSize": 10, "sortField": "id", "sortOrder": "ascend"}
            if level:
                body["tags"] = [level]
            cases.append({"id": f"{topic}-{level or 'all'}", "body": body, "expected_total": histogram[(topic, level)] if level else histogram[topic]})
    for number in range(8):
        cases.append({"id": f"missing-{number}", "body": {"searchText": f"absentterm{number:05d}", "current": 1, "pageSize": 10, "sortField": "id", "sortOrder": "ascend"}, "expected_total": 0})
    return cases, {
        "rows": count, "authors": 64, "seed": SEED, "synthetic": True,
        "row_sha256": digest.hexdigest(), "topic_counts": {topic: histogram[topic] for topic in TOPICS},
        "content_bytes_mean": statistics.mean(content_bytes), "content_bytes_min": min(content_bytes),
        "content_bytes_max": max(content_bytes), "cases": len(cases),
    }


class Environment:
    def __init__(self, output):
        self.output = output
        self.suffix = secrets.token_hex(4)
        self.password = secrets.token_hex(16)
        self.containers = []
        self.app = None
        self.logs = []
        self.temp = tempfile.TemporaryDirectory(prefix="interviewfox-benchmark-")

    def container(self, kind, image, port, options, extra=()):
        name = f"interviewfox-bench-{kind}-{self.suffix}"
        command(["docker", "run", "--rm", "-d", "--name", name, "--cpus=2", "--memory=2g",
                 "-p", f"127.0.0.1::{port}"] + options + [image] + list(extra))
        self.containers.append(name)
        address = command(["docker", "port", name, f"{port}/tcp"])
        return name, int(address.rsplit(":", 1)[1])

    def mysql(self, sql=None, source=None):
        args = ["docker", "exec", "-i", "-e", f"MYSQL_PWD={self.password}", self.mysql_name,
                "mysql", "-uroot", "--batch", "--skip-column-names", "--default-character-set=utf8mb4"]
        if source is not None:
            with gzip.open(source, "rb") as stream:
                result = subprocess.run(args, input=stream.read(), capture_output=True, timeout=120)
        else:
            result = subprocess.run(args, input=sql.encode(), capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.decode())
        return result.stdout.decode().strip()

    def start(self, jar):
        self.mysql_name, mysql_port = self.container(
            "mysql", "mysql:8.4", 3306, ["-e", f"MYSQL_ROOT_PASSWORD={self.password}"],
            ["--innodb-buffer-pool-size=536870912", "--max-connections=100"])
        _, es_port = self.container(
            "es", "docker.elastic.co/elasticsearch/elasticsearch:7.17.4", 9200,
            ["-e", "discovery.type=single-node", "-e", "xpack.security.enabled=false",
             "-e", "ES_JAVA_OPTS=-Xms768m -Xmx768m", "-e", "ingest.geoip.downloader.enabled=false"])
        self.es = f"http://127.0.0.1:{es_port}"
        wait_for("MySQL ready", lambda: self.mysql("SELECT 1;") == "1")
        wait_for("Elasticsearch ready", lambda: http_json(self.es + "/")["version"]["number"] == "7.17.4")
        self.mysql((ROOT / "sql/create_table.sql").read_text())
        self.mysql(source=self.output / "dataset.sql.gz")
        # Backfill existing rows, rather than measuring an artificial backlog of seed inserts.
        self.mysql("USE interviewfox;\n" + (ROOT / "sql/question_search_sync.sql").read_text())
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            app_port = listener.getsockname()[1]
        self.base = f"http://127.0.0.1:{app_port}"
        config = Path(self.temp.name) / "application.properties"
        config.write_text(f"""server.port={app_port}
server.address=127.0.0.1
server.servlet.context-path=/api
spring.datasource.url=jdbc:mysql://127.0.0.1:{mysql_port}/interviewfox?allowPublicKeyRetrieval=true&useSSL=false&serverTimezone=UTC
spring.datasource.username=root
spring.datasource.password={self.password}
spring.datasource.hikari.maximum-pool-size=16
spring.session.store-type=none
spring.mvc.pathmatch.matching-strategy=ant_path_matcher
spring.elasticsearch.uris={self.es}
spring.elasticsearch.socket-timeout=10s
mybatis-plus.configuration.map-underscore-to-camel-case=false
mybatis-plus.configuration.log-impl=org.apache.ibatis.logging.nologging.NoLoggingImpl
wx.mp.app-id=benchmark-app
wx.mp.secret=benchmark-only
wx.mp.token=benchmark-only
cos.client.access-key=benchmark-only
cos.client.secret-key=benchmark-only
cos.client.region=ap-toronto
cos.client.bucket=benchmark-only
interviewfox.search.elasticsearch.enabled=true
interviewfox.search.elasticsearch.sync-delay-ms=1000
logging.level.com.berlin.interviewfox.aop.LogInterceptor=WARN
logging.level.com.berlin.interviewfox.exception.GlobalExceptionHandler=OFF
""")
        log = (self.output / "application.log").open("w")
        self.logs.append(log)
        self.app = subprocess.Popen(
            ["java", "-Xms256m", "-Xmx768m", "-XX:ActiveProcessorCount=4", "-jar", str(jar),
             f"--spring.config.location={config}"], stdout=log, stderr=subprocess.STDOUT)

    def close(self):
        if self.app and self.app.poll() is None:
            self.app.terminate()
            try:
                self.app.wait(15)
            except subprocess.TimeoutExpired:
                self.app.kill()
                self.app.wait()
        for name in reversed(self.containers):
            subprocess.run(["docker", "stop", "-t", "10", name], capture_output=True, timeout=35)
        for log in self.logs:
            log.close()
        self.temp.cleanup()


def http_json(url, body=None):
    parsed = urlsplit(url)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=15)
    try:
        connection.request("POST" if body is not None else "GET", parsed.path or "/",
                           json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
        response = connection.getresponse()
        data = response.read()
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}: {data[:200]!r}")
        return json.loads(data)
    finally:
        connection.close()


def wait_for(description, check, timeout=300):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            if check():
                print(description, flush=True)
                return
        except (OSError, RuntimeError, http.client.HTTPException) as error:
            last = str(error)
        time.sleep(1)
    raise RuntimeError(f"{description} timed out: {last}")


class SearchClient:
    def __init__(self, base):
        self.url = urlsplit(base)
        self.local = threading.local()

    def query(self, engine, case):
        connection = getattr(self.local, "connection", None)
        if connection is None:
            connection = http.client.HTTPConnection(self.url.hostname, self.url.port, timeout=15)
            self.local.connection = connection
        try:
            connection.request("POST", f"/api/question/list/page/vo?engine={engine}", json.dumps(case["body"]),
                               {"Content-Type": "application/json"})
            response = connection.getresponse()
            data = json.loads(response.read())
            if response.status != 200 or data.get("code") != 0:
                raise RuntimeError(f"HTTP {response.status}, application code {data.get('code')}")
            page = data["data"]
            if int(page["total"]) != case["expected_total"]:
                raise RuntimeError(f"unexpected total for {case['id']}: {page['total']}")
            return page
        except Exception:
            connection.close()
            self.local.connection = None
            raise


def percentile(values, percentage):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percentage / 100) - 1)] if ordered else None


def run_round(client, engine, cases, rate, duration, workers, round_number):
    rows = []
    schedule = list(cases)
    random.Random(SEED + round_number).shuffle(schedule)

    def request(number, scheduled, submitted):
        started = time.perf_counter()
        case = schedule[number % len(schedule)]
        error = ""
        total = None
        try:
            page = client.query(engine, case)
            total = int(page["total"])
        except Exception as failure:
            error = f"{type(failure).__name__}: {failure}"
        finished = time.perf_counter()
        return {
            "rate": rate, "round": round_number + 1, "engine": engine, "case": case["id"],
            "latency_ms": (finished - scheduled) * 1000, "http_ms": (finished - started) * 1000,
            "queue_ms": (started - submitted) * 1000, "scheduler_ms": (submitted - scheduled) * 1000,
            "total": total, "error": error,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        start = time.perf_counter() + 0.1
        futures = []
        for number in range(round(rate * duration)):
            scheduled = start + number / rate
            time.sleep(max(0, scheduled - time.perf_counter()))
            futures.append(executor.submit(request, number, scheduled, time.perf_counter()))
        for future in futures:
            rows.append(future.result())
        elapsed = time.perf_counter() - start
    summary = summarize(rows)
    summary.update({"engine": engine, "rate": rate, "round": round_number + 1, "elapsed_seconds": elapsed,
                    "achieved_rps": summary["successes"] / elapsed})
    print(json.dumps(summary), flush=True)
    return rows, summary


def summarize(rows):
    successful = [row for row in rows if not row["error"]]
    values = [row["latency_ms"] for row in successful]
    return {
        "requests": len(rows), "successes": len(successful), "errors": len(rows) - len(successful),
        "p50_ms": percentile(values, 50), "p95_ms": percentile(values, 95), "p99_ms": percentile(values, 99),
        "mean_ms": statistics.mean(values) if values else None,
        "http_p95_ms": percentile([row["http_ms"] for row in successful], 95),
        "queue_p95_ms": percentile([row["queue_ms"] for row in successful], 95),
        "scheduler_p95_ms": percentile([row["scheduler_ms"] for row in successful], 95),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=50_000)
    parser.add_argument("--rates", type=int, nargs="+", default=[2, 3])
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if min(args.rows, *args.rates, args.seconds, args.rounds, args.workers, args.warmup) <= 0:
        parser.error("All numeric arguments must be positive")
    output = args.output or Path(__file__).parent / "results" / datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d-%H%M%S")
    output.mkdir(parents=True, exist_ok=False)
    jar = ROOT / "target/interviewFox-backend-0.0.1-SNAPSHOT.jar"
    if not jar.is_file():
        parser.error("Build the application with mvn package before running")
    cases, manifest = dataset(output / "dataset.sql.gz", args.rows)
    (output / "queries.json").write_text(json.dumps(cases, indent=2))
    metadata = {
        "started_at": datetime.now(ZoneInfo("America/Toronto")).isoformat(), "source_commit": command(["git", "rev-parse", "HEAD"]),
        "source_dirty": bool(command(["git", "status", "--porcelain"])),
        "jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(),
        "platform": platform.platform(), "architecture": platform.machine(), "python": platform.python_version(),
        "java": subprocess.run(["java", "-version"], capture_output=True, text=True).stderr.strip(),
        "docker": json.loads(command(["docker", "info", "--format", '{"cpus":{{.NCPU}},"memory":{{.MemTotal}},"version":"{{.ServerVersion}}"}'])),
        "settings": {"rates": args.rates, "seconds": args.seconds, "rounds": args.rounds, "workers": args.workers,
                     "warmup_per_engine": args.warmup, "container_cpus_each": 2, "container_memory_each": "2g",
                     "mysql_buffer_pool": "512MiB", "es_heap": "768MiB", "application_heap": "768MiB",
                     "hikari_pool": 16, "es_shards": 1, "es_replicas": 0, "arrival_model": "fixed-rate",
                     "latency_definition": "scheduled request time through JSON response validation, including client queue wait",
                     "percentile": "nearest rank over successful requests; errors reported separately"},
        "dataset": manifest,
    }
    (output / "environment.json").write_text(json.dumps(metadata, indent=2))
    environment = Environment(output)
    try:
        environment.start(jar)
        wait_for("50000-row database imported" if args.rows == 50_000 else "Database imported",
                 lambda: int(environment.mysql("USE interviewfox; SELECT COUNT(*) FROM question WHERE isDelete=0;")) == args.rows)
        client = SearchClient(environment.base)
        wait_for("Full sync and initial drain complete",
                 lambda: client.query("elasticsearch", cases[0]) is not None)
        count = http_json(environment.es + f"/{INDEX}/_count")["count"]
        if count != args.rows:
            raise RuntimeError(f"Index contains {count} documents instead of {args.rows}")
        metadata["mysql_version"] = environment.mysql("SELECT VERSION();")
        metadata["elasticsearch_version"] = http_json(environment.es + "/")["version"]["number"]
        container_format = '{"image":{{json .Config.Image}},"image_id":{{json .Image}},"nano_cpus":{{.HostConfig.NanoCpus}},"memory_bytes":{{.HostConfig.Memory}}}'
        metadata["containers"] = [json.loads(line) for line in command(
            ["docker", "inspect", "--format", container_format] + environment.containers).splitlines()]
        metadata["harness_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if platform.system() == "Darwin":
            metadata["host_memory_bytes"] = int(command(["sysctl", "-n", "hw.memsize"]))
            metadata["host_logical_cpus"] = int(command(["sysctl", "-n", "hw.logicalcpu"]))
        (output / "environment.json").write_text(json.dumps(metadata, indent=2))
        verification = []
        for case in cases:
            mysql = client.query("mysql", case)
            es = client.query("elasticsearch", case)
            mysql_ids = [row["id"] for row in mysql["records"]]
            es_ids = [row["id"] for row in es["records"]]
            if mysql_ids != es_ids:
                raise RuntimeError(f"Different result IDs for {case['id']}")
            verification.append({"case": case["id"], "total": case["expected_total"], "ids_equal": True})
        (output / "correctness.json").write_text(json.dumps(verification, indent=2))
        print(f"Verified counts and ordered IDs for all {len(cases)} queries", flush=True)
        for engine in ["mysql", "elasticsearch"]:
            for number in range(args.warmup):
                client.query(engine, cases[number % len(cases)])
                time.sleep(0.05)
        all_rows = []
        rounds = []
        with (output / "requests.csv").open("w", newline="") as raw:
            writer = None
            for rate in args.rates:
                for number in range(args.rounds):
                    order = ["mysql", "elasticsearch"] if number % 2 == 0 else ["elasticsearch", "mysql"]
                    for engine in order:
                        rows, summary = run_round(client, engine, cases, rate, args.seconds, args.workers, number)
                        if writer is None:
                            writer = csv.DictWriter(raw, fieldnames=list(rows[0]))
                            writer.writeheader()
                        writer.writerows(rows)
                        raw.flush()
                        all_rows.extend(rows)
                        rounds.append(summary)
                        time.sleep(2)
        aggregate = []
        for rate in args.rates:
            for engine in ["mysql", "elasticsearch"]:
                selected = [row for row in all_rows if row["rate"] == rate and row["engine"] == engine]
                aggregate.append({"rate": rate, "engine": engine, **summarize(selected)})
        result = {"rounds": rounds, "aggregate": aggregate, "source_commit": metadata["source_commit"],
                  "complete": True, "synthetic_local_benchmark": True}
        (output / "summary.json").write_text(json.dumps(result, indent=2))
        print("RESULTS " + str(output.resolve()), flush=True)
    finally:
        environment.close()


if __name__ == "__main__":
    main()
