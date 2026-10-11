"""A pre-run cost estimate for a real-model grid. Shown BEFORE any API call.

The charter is strict: never start a paid run without putting a dollar figure in
front of the user first. This module produces that figure offline — no network,
no `count_tokens` call — by approximating tokens from character length. It is an
order-of-magnitude guide, deliberately rounded up, not an invoice:

  - tokens are estimated at ~4 characters/token (English prose; code and
    non-ASCII run denser, so this under-counts those — we offset with a worst-
    case per-call input assumption below).
  - each run is assumed to make `avg_steps` model calls, and each call is
    assumed to carry the FULL document plus the system prompt (an upper bound,
    since early calls carry less).

Real spend depends on how many steps the model actually takes and the exact
tokeniser, so treat the output as "about this much, probably less".
"""

from dataclasses import dataclass

from .corpus import Carrier
from .defenses import SPOTLIGHT_PROMPT

# Input/output USD per million tokens, from the claude-api reference
# (cached 2026-06-24). VERIFY against current pricing before billing.
PRICES_USD_PER_MTOK = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
}

_CHARS_PER_TOKEN = 4
_OUTPUT_TOKENS_PER_CALL = 48  # one short JSON action


@dataclass
class CostEstimate:
    model: str
    n_runs: int
    avg_steps: int
    calls: int
    input_tokens: int
    output_tokens: int
    usd: float | None  # None if the model's price is unknown
    note: str


def _tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def estimate_cost(carrier: Carrier, cells, arms, model: str, *,
                  avg_steps: int = 4) -> CostEstimate:
    """Estimate the cost of running every cell under every arm on `model`.

    `cells` and `arms` are the same objects passed to `measure.run_grid`.
    """
    n_runs = len(cells) * len(arms)
    calls = n_runs * avg_steps

    # Upper-bound per-call input: longest system prompt + the request + the
    # largest document the model will read in this grid.
    sys_tokens = _tokens(SPOTLIGHT_PROMPT)
    req_tokens = _tokens(carrier.user_request)
    doc_tokens = max((_tokens(c.document_text) for c in cells), default=0)
    per_call_input = sys_tokens + req_tokens + doc_tokens

    input_tokens = calls * per_call_input
    output_tokens = calls * _OUTPUT_TOKENS_PER_CALL

    price = PRICES_USD_PER_MTOK.get(model)
    if price is None:
        usd = None
        note = f"no cached price for {model!r}; verify before running"
    else:
        in_rate, out_rate = price
        usd = input_tokens / 1e6 * in_rate + output_tokens / 1e6 * out_rate
        note = (f"~{_CHARS_PER_TOKEN} chars/token, {avg_steps} calls/run, "
                f"full-document input per call (upper bound)")

    return CostEstimate(model, n_runs, avg_steps, calls,
                        input_tokens, output_tokens, usd, note)


def format_estimate(est: CostEstimate) -> str:
    usd = "unknown (no cached price)" if est.usd is None else f"${est.usd:.2f}"
    return (
        f"Cost estimate (model={est.model})\n"
        f"  runs (cells x arms):   {est.n_runs}\n"
        f"  est. model calls:      {est.calls}  (~{est.avg_steps}/run)\n"
        f"  est. input tokens:     {est.input_tokens:,}\n"
        f"  est. output tokens:    {est.output_tokens:,}\n"
        f"  est. cost:             {usd}\n"
        f"  basis:                 {est.note}\n"
        f"  NOTE: rough upper bound; real spend is usually lower. No API call "
        f"was made to produce this."
    )
