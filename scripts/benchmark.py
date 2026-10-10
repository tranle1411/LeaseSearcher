"""Measure the running API; this does not measure Render cold starts."""

import argparse
import asyncio
import json
import math
import platform
import time
from pathlib import Path

import httpx


async def benchmark(url, output):
    semaphore = asyncio.Semaphore(10)
    async with httpx.AsyncClient(base_url=url, timeout=30) as client:
        metadata = (await client.get("/api/metadata")).json()
        for _ in range(5):
            (await client.post("/api/search", json={})).raise_for_status()

        async def call():
            async with semaphore:
                start = time.perf_counter()
                response = await client.post("/api/search", json={})
                response.raise_for_status()
                return (time.perf_counter() - start) * 1000, len(response.json()["matches"])

        samples = await asyncio.gather(*(call() for _ in range(100)))
        exports = []
        for _ in range(10):
            start = time.perf_counter()
            (await client.post("/api/export", json={})).raise_for_status()
            exports.append((time.perf_counter() - start) * 1000)
    durations = sorted(value for value, _ in samples)
    result = {
        "environment": platform.system(),
        "target": url,
        "dataset_version": metadata["version"],
        "mode": metadata["mode"],
        "eligibility_policy": metadata["eligibility_policy"],
        "pricing_policy": metadata["pricing_policy"],
        "requests": 100,
        "concurrency": 10,
        "search_p50_ms": round(durations[49], 2),
        "search_p95_ms": round(durations[94], 2),
        "export_p95_ms": round(sorted(exports)[math.ceil(0.95 * len(exports)) - 1], 2),
        "returned_matches": sorted(set(count for _, count in samples)),
        "limitation": "Local warm API using default search and the reported snapshot/policy. Not a hosted SLA or Render cold-start measurement.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("docs/benchmark.json"))
    args = parser.parse_args()
    asyncio.run(benchmark(args.url, args.output))
