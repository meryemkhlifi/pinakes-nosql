"""Timing helpers: percentiles and repeated measurements (owner: A)."""

import time
from collections.abc import Callable


def percentile(values: list[float], p: float) -> float:
    """Percentile with linear interpolation (the same as numpy.percentile)."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    k = (len(ordered) - 1) * p / 100
    low = int(k)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (k - low)


def summarize(times_ms: list[float]) -> dict:
    """p50 = typical request, p95 = 95 % of the requests are faster."""
    return {
        "runs": len(times_ms),
        "p50_ms": round(percentile(times_ms, 50), 3),
        "p95_ms": round(percentile(times_ms, 95), 3),
        "mean_ms": round(sum(times_ms) / len(times_ms), 3),
        "min_ms": round(min(times_ms), 3),
        "max_ms": round(max(times_ms), 3),
    }


def time_calls(
    fn: Callable[[int], object], runs: int = 30, warmup: int = 3
) -> tuple[list[float], list[object]]:
    """Call fn(i) warmup + runs times. Returns the durations (ms) and the timed answers."""
    for i in range(warmup):
        fn(i)
    times, answers = [], []
    for i in range(runs):
        start = time.perf_counter()
        answers.append(fn(warmup + i))
        times.append((time.perf_counter() - start) * 1000)
    return times, answers
