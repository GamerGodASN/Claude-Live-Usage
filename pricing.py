"""Model pricing (Anthropic API rates, USD per million tokens) and cost math.

Only models whose canonical name contains opus/sonnet/haiku are priced; anything
else returns 0.0 cost and is reported as n/a by callers.
"""

# USD per million tokens: (input, output, cache_write_5m, cache_read)
_RATES = {
    "opus": (5.00, 25.00, 6.25, 0.50),
    "sonnet": (3.00, 15.00, 3.75, 0.30),
    "haiku": (1.00, 5.00, 1.25, 0.10),
}


def family(model: str) -> str | None:
    """Return 'opus' / 'sonnet' / 'haiku' for a model id, else None."""
    if not model:
        return None
    m = model.lower()
    for fam in _RATES:
        if fam in m:
            return fam
    return None


def cost_usd(model: str, inp: int, out: int, cache_write: int, cache_read: int) -> float:
    """Cost in USD for one usage record. Unknown models cost 0.0."""
    fam = family(model)
    if fam is None:
        return 0.0
    ri, ro, rw, rr = _RATES[fam]
    return (
        inp * ri + out * ro + cache_write * rw + cache_read * rr
    ) / 1_000_000.0
