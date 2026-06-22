"""Faithful Tree-of-Thoughts vs single call on Game-of-24 — the search test.

The repo's headline finding ("no pure-LLM scaffold beats a prompt-matched
single call") was measured on open-ended *advisory* tasks that do not require
search, with a ToT implementation that (a) builds full strategies instead of
partial states, (b) never backtracks, (c) scores standalone quality instead of
*lookahead value*, and (d) writes the answer with a fresh synthesis call that
ignores which branch won. That experiment cannot speak to whether *faithful*
ToT beats a single call.

This module runs the missing experiment on ToT's canonical benchmark
(Yao et al., NeurIPS 2023, arXiv:2305.10601):

  Game-of-24 — combine four numbers with + - * / (each used once) to make 24.

It is verifiable (Python ground truth, no LLM judge), search-requiring (the
first arithmetic choice constrains everything; ~60% of single CoT chains die at
step 1 with no way to recover), and decomposes into genuine partial states
(the remaining numbers). Faithful ToT here:

  * node = a *partial state* (the remaining numbers + the expression so far);
  * propose = the LLM picks the next move (which two numbers, which op) — Python
    does the bookkeeping arithmetic, so an invalid/hallucinated move is dropped;
  * value  = the LLM rates a partial state's *lookahead* ("can these numbers
    still reach 24?": sure / likely / impossible) — the grounded prune signal;
  * search = BFS keeping the b best partial states per depth;
  * answer = the winning leaf's expression — search SELECTS the output, there is
    no synthesis call papering over the tree.

Baselines at matched cost: a single CoT call, and CoT-SC@k (k independent CoT
samples, pass if ANY is correct — the strongest cheap baseline ToT must beat).

Live (needs a model — set GOOGLE_API_KEY, or OPENAI_API_BASE + OPENAI_API_KEY +
DEFAULT_MODEL_CONFIG=openai:<model>). Run:
    uv run python -m evals.game24 [--limit N --beam 5 --cot-sc-k K --json out.json]
"""

import argparse
import ast
import asyncio
import json
import operator
import re
from dataclasses import dataclass, field
from fractions import Fraction

from dialectica import agent_runtime
from dialectica.agent_factory import create_agent
from dialectica.llm_config import get_model_config

# Puzzles span the difficulty range. The hard ones (few or single solutions,
# requiring an unobvious first move) are exactly where a single CoT pass fails
# and search has to pay off.
PUZZLES: list[tuple[int, int, int, int]] = [
    (4, 4, 6, 8),
    (2, 4, 6, 8),
    (3, 4, 6, 8),
    (1, 4, 8, 8),
    (2, 9, 10, 12),
    (4, 9, 10, 13),
    (1, 5, 5, 5),
    (5, 5, 5, 9),
    (3, 3, 7, 7),
    (1, 3, 4, 6),
    (2, 5, 5, 10),
    (4, 6, 8, 8),
    (2, 2, 10, 10),
    (1, 2, 7, 7),
    (6, 6, 6, 6),
]

# The literature's hardest tier: every one needs a fraction intermediate or a
# non-obvious first move, so a single left-to-right CoT pass tends to die at
# step 1 with no way back. This is the regime where search must pay off — and
# where a strong model is least likely to ceiling. All verified solvable.
HARD_PUZZLES: list[tuple[int, int, int, int]] = [
    (3, 3, 8, 8),
    (1, 3, 4, 6),
    (1, 4, 5, 6),
    (1, 5, 5, 5),
    (3, 3, 7, 7),
    (2, 5, 5, 10),
    (4, 4, 7, 7),
    (1, 6, 6, 8),
    (2, 2, 11, 11),
    (5, 5, 7, 11),
]

# --- Ground truth (pure Python, no LLM) ----------------------------------

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def _eval_exact(node: ast.AST) -> Fraction:
    """Evaluate an arithmetic expression with exact rational arithmetic."""
    if isinstance(node, ast.Expression):
        return _eval_exact(node.body)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_exact(node.left), _eval_exact(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_exact(node.operand)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Fraction(node.value)
    raise ValueError(f"illegal expression node: {ast.dump(node)}")


def check_24(expr: str, numbers: tuple[int, ...]) -> tuple[bool, str]:
    """Verify ``expr`` uses exactly ``numbers`` (each once) and equals 24.

    Returns ``(passed, reason)``. This is the objective oracle — every arm is
    scored through it, so a hallucinated or arithmetically-wrong answer fails
    regardless of how confident the model sounded.
    """
    used = [int(n) for n in re.findall(r"\d+", expr)]
    if sorted(used) != sorted(numbers):
        return False, f"uses {sorted(used)} != {sorted(numbers)}"
    try:
        value = _eval_exact(ast.parse(expr, mode="eval"))
    except (SyntaxError, ValueError, ZeroDivisionError) as e:
        return False, f"unparseable ({e})"
    if value == 24:
        return True, "ok"
    return False, f"= {float(value):.4g}, not 24"


def extract_expression(text: str) -> str:
    """Pull the final arithmetic expression out of a model's answer.

    Prefers an explicit ``Answer:`` line; falls back to the last line that
    looks like a bare arithmetic expression.
    """
    for line in reversed(text.strip().splitlines()):
        m = re.search(r"answer\s*[:=]\s*(.+)", line, re.IGNORECASE)
        if m:
            return m.group(1).strip().strip("`").rstrip(".")
    for line in reversed(text.strip().splitlines()):
        candidate = line.split("=")[0].strip().strip("`")
        if candidate and re.fullmatch(r"[0-9+\-*/().\s]+", candidate):
            return candidate
    return text.strip().splitlines()[-1] if text.strip() else ""


def _fmt(n: Fraction) -> str:
    return str(n.numerator) if n.denominator == 1 else f"{n.numerator}/{n.denominator}"


# --- Faithful Tree-of-Thoughts -------------------------------------------


@dataclass
class State:
    """A partial state: the numbers left to combine and the expression so far."""

    nums: tuple[Fraction, ...]
    exprs: tuple[str, ...]
    value: float = 0.0
    history: list[str] = field(default_factory=list)

    def display(self) -> str:
        return " ".join(_fmt(n) for n in self.nums)


_MOVE_RE = re.compile(
    r"(-?\d+(?:/\d+)?)\s*([+\-*x×/])\s*(-?\d+(?:/\d+)?)", re.IGNORECASE
)
_OP_FN = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "x": operator.mul,
    "×": operator.mul,
    "/": operator.truediv,
}

PROPOSE_PROMPT = """Game of 24. You have these numbers: {nums}
Pick TWO of them and combine with one of + - * / to get a new number. You may
reorder. List several promising next moves, one per line, in the form
    a op b = c
using only numbers from the list above. Do not solve the whole puzzle — just
propose single next moves."""

VALUE_PROMPT = """Game of 24. Remaining numbers: {nums}
Can these numbers be combined with + - * / (each used once) to make exactly 24?
Answer with a single word: sure, likely, or impossible."""

_VALUE_MAP = {"sure": 3.0, "likely": 1.0, "impossible": 0.001}


def _parse_moves(text: str, nums: tuple[Fraction, ...]) -> list[tuple[int, int, str]]:
    """Parse proposed ``a op b`` moves, keeping only ones valid for ``nums``.

    Returns ``(i, j, op)`` index pairs into ``nums``. A move naming a number
    not present (a hallucinated operand) is silently dropped — Python, not the
    model, decides which moves are legal.
    """
    moves: list[tuple[int, int, str]] = []
    seen: set[tuple[int, int, str]] = set()
    for line in text.splitlines():
        m = _MOVE_RE.search(line)
        if not m:
            continue
        a, op, b = Fraction(m.group(1)), m.group(2).lower(), Fraction(m.group(3))
        i = next((k for k in range(len(nums)) if nums[k] == a), None)
        j = next((k for k in range(len(nums)) if nums[k] == b and k != i), None)
        if i is None or j is None:
            continue
        key = (min(i, j), max(i, j), op)
        if key not in seen:
            seen.add(key)
            moves.append((i, j, op))
    return moves


def _apply(state: State, i: int, j: int, op: str) -> State | None:
    a, b = state.nums[i], state.nums[j]
    if op == "/" and b == 0:
        return None
    result = _OP_FN[op](a, b)
    rest = [
        (state.nums[k], state.exprs[k])
        for k in range(len(state.nums))
        if k not in (i, j)
    ]
    new_nums = tuple(n for n, _ in rest) + (result,)
    new_exprs = tuple(e for _, e in rest) + (
        f"({state.exprs[i]} {op} {state.exprs[j]})",
    )
    step = f"{_fmt(a)} {op} {_fmt(b)} = {_fmt(result)}"
    return State(new_nums, new_exprs, history=state.history + [step])


class Counter:
    def __init__(self) -> None:
        self.calls = 0


async def _propose(
    agent, state: State, counter: Counter, max_moves: int
) -> list[State]:
    counter.calls += 1
    text = await agent_runtime.run_agent(
        agent, PROPOSE_PROMPT.format(nums=state.display())
    )
    children = [_apply(state, i, j, op) for i, j, op in _parse_moves(text, state.nums)]
    return [c for c in children if c is not None][:max_moves]


async def _value(agent, state: State, counter: Counter) -> float:
    counter.calls += 1
    text = (
        await agent_runtime.run_agent(agent, VALUE_PROMPT.format(nums=state.display()))
    ).lower()
    # Take the last verdict word the model emits.
    found = [w for w in re.findall(r"sure|likely|impossible", text)]
    return _VALUE_MAP[found[-1]] if found else _VALUE_MAP["likely"]


async def solve_tot(
    agent, numbers: tuple[int, ...], beam: int = 5, max_moves: int = 8
) -> tuple[str | None, int]:
    """Faithful BFS Tree-of-Thoughts. Returns ``(winning_expression, llm_calls)``.

    The winning leaf's expression IS the answer — there is no synthesis pass.
    """
    counter = Counter()
    start = State(tuple(Fraction(n) for n in numbers), tuple(str(n) for n in numbers))
    beam_states = [start]

    while beam_states and len(beam_states[0].nums) > 1:
        proposals = await asyncio.gather(
            *(_propose(agent, s, counter, max_moves) for s in beam_states)
        )
        children = [c for group in proposals for c in group]
        if not children:
            break

        # Terminal children (one number left) are checked directly; only
        # non-terminal partial states need the lookahead value to be ranked.
        for child in children:
            if len(child.nums) == 1 and child.nums[0] == 24:
                ok, _ = check_24(child.exprs[0], numbers)
                if ok:
                    return child.exprs[0], counter.calls

        non_terminal = [c for c in children if len(c.nums) > 1]
        if not non_terminal:
            break
        scores = await asyncio.gather(
            *(_value(agent, c, counter) for c in non_terminal)
        )
        for child, score in zip(non_terminal, scores):
            child.value = score
        beam_states = sorted(non_terminal, key=lambda s: s.value, reverse=True)[:beam]

    return None, counter.calls


# --- Baselines ------------------------------------------------------------

COT_PROMPT = """Game of 24: use each of these four numbers exactly once, with
+ - * / and parentheses, to make 24: {nums}
Think step by step, then end with a line in exactly this form:
Answer: <expression>"""


async def solve_single_call(agent, numbers: tuple[int, ...]) -> bool:
    text = await agent_runtime.run_agent(
        agent, COT_PROMPT.format(nums=" ".join(str(n) for n in numbers))
    )
    ok, _ = check_24(extract_expression(text), numbers)
    return ok


async def solve_cot_sc(agent, numbers: tuple[int, ...], k: int) -> bool:
    """CoT-SC: k independent CoT samples, pass if ANY is correct (pass@k)."""
    results = await asyncio.gather(
        *(solve_single_call(agent, numbers) for _ in range(k))
    )
    return any(results)


# --- Runner ---------------------------------------------------------------


async def run(limit: int, beam: int, cot_sc_k: int, hard: bool = False) -> dict:
    agent = create_agent(
        role="Generator",
        role_name="Solver",
        model_config=get_model_config("GENERATOR"),
    )
    pool = HARD_PUZZLES if hard else PUZZLES
    puzzles = pool[:limit] if limit else pool

    tot_pass = single_pass = sc_pass = 0
    tot_calls = 0
    rows = []
    for nums in puzzles:
        expr, calls = await solve_tot(agent, nums, beam=beam)
        tot_ok = expr is not None
        single_ok = await solve_single_call(agent, nums)
        sc_ok = await solve_cot_sc(agent, nums, cot_sc_k)
        tot_pass += tot_ok
        single_pass += single_ok
        sc_pass += sc_ok
        tot_calls += calls
        rows.append(
            {
                "puzzle": nums,
                "tot": tot_ok,
                "tot_calls": calls,
                "tot_expr": expr,
                "single_call": single_ok,
                "cot_sc": sc_ok,
            }
        )

    n = len(puzzles)
    return {
        "n": n,
        "beam": beam,
        "cot_sc_k": cot_sc_k,
        "tot": tot_pass,
        "single_call": single_pass,
        "cot_sc": sc_pass,
        "avg_tot_calls": round(tot_calls / max(1, n), 1),
        "rows": rows,
    }


def render(result: dict) -> str:
    lines = [
        "# Faithful ToT vs single call vs CoT-SC | Game-of-24 (ground-truth verified)\n"
    ]
    for r in result["rows"]:
        nums = " ".join(str(x) for x in r["puzzle"])
        lines.append(
            f"[{nums:>14}] tot={int(r['tot'])} ({r['tot_calls']} calls)  "
            f"single={int(r['single_call'])}  cot_sc={int(r['cot_sc'])}  "
            f"{r['tot_expr'] or ''}"
        )
    n = result["n"]
    lines.append(
        f"\n# TOTAL  faithful_ToT={result['tot']}/{n}  "
        f"single_call={result['single_call']}/{n}  "
        f"CoT-SC@{result['cot_sc_k']}={result['cot_sc']}/{n}  "
        f"| avg ToT calls/puzzle={result['avg_tot_calls']}"
    )
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Faithful ToT vs single call on Game-of-24."
    )
    p.add_argument("--limit", type=int, default=0, help="Only run the first N puzzles.")
    p.add_argument("--beam", type=int, default=5, help="BFS beam width b (paper: 5).")
    p.add_argument("--cot-sc-k", type=int, default=5, help="CoT-SC samples (pass@k).")
    p.add_argument(
        "--hard",
        action="store_true",
        help="Use the hard fraction-requiring puzzle set.",
    )
    p.add_argument(
        "--json", type=str, default="", help="Write raw results to this path."
    )
    args = p.parse_args()

    result = asyncio.run(run(args.limit, args.beam, args.cot_sc_k, hard=args.hard))
    print(render(result))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()
