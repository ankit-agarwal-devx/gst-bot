"""Deterministic failure roll (FAILURE_CONTRACT.md §B1). Live tax-model uses the same code."""
import hashlib

# Order matters: slow, stall, drop, 503, 502. Remaining probability is "ok".
PROFILES: dict[str, list[tuple[str, float]]] = {
    "calm":   [("slow", 0.05), ("stall", 0.00), ("drop", 0.00), ("503", 0.00), ("502", 0.00)],
    "normal": [("slow", 0.10), ("stall", 0.03), ("drop", 0.07), ("503", 0.06), ("502", 0.04)],
    "storm":  [("slow", 0.10), ("stall", 0.10), ("drop", 0.15), ("503", 0.15), ("502", 0.10)],
}


def roll(api_key: str, n: int, profile: list[tuple[str, float]]) -> tuple[str, float]:
    d = hashlib.sha256(f"{api_key}|{n}".encode()).digest()
    u = int.from_bytes(d[:8], "big") / 2**64
    acc = 0.0
    for mode, p in profile:
        acc += p
        if u < acc:
            break
    else:
        mode = "ok"
    extra = int.from_bytes(d[8:10], "big")
    delay = {
        "ok": 0.2 + (extra % 1301) / 1000,
        "slow": 3.0 + (extra % 5001) / 1000,
        "stall": 40.0,
    }.get(mode, 0.0)
    return mode, delay
