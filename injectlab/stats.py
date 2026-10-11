"""The statistics the report is allowed to use. Standard library only.

Two tools, chosen so every number we publish carries its uncertainty:

  wilson_interval  a 95% confidence interval for a proportion. We never report a
                   bare rate: "0/20 blocked" and "0/2000 blocked" are different
                   claims, and Wilson stays sane at the extremes (0 and 1) and at
                   small n, where the textbook normal interval does not.

  mcnemar_exact    the exact paired test. Two defenses are measured on the SAME
                   cells, so the comparison is paired. Only the DISCORDANT pairs
                   carry information — cells where the two arms agree tell us
                   nothing about which is better. McNemar's exact test is just a
                   two-sided binomial sign test on those discordant counts, with
                   no large-sample approximation to break at small n.
"""

import math


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% (default z) Wilson score interval for k successes in n trials.

    Returns (low, high), clamped to [0, 1]. n == 0 yields (0.0, 0.0): no data,
    no claim.
    """
    if n < 0 or k < 0 or k > n:
        raise ValueError(f"need 0 <= k <= n, got k={k}, n={n}")
    if n == 0:
        return (0.0, 0.0)

    phat = k / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (phat + z2 / (2 * n)) / denom
    half = (z / denom) * math.sqrt(phat * (1 - phat) / n + z2 / (4 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from discordant pair counts.

    b and c are the two kinds of disagreement between a defense and the baseline
    on the same cells, e.g. b = baseline leaked but the defense blocked (the
    defense helped), c = baseline was safe but the defense leaked (it hurt).
    Under "the defense changes nothing" each discordant pair is a fair coin, so
    the p-value is the two-sided binomial tail with p=0.5. No discordant pairs
    (b == c == 0) means no evidence either way -> 1.0.
    """
    if b < 0 or c < 0:
        raise ValueError(f"counts must be non-negative, got b={b}, c={c}")
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)
