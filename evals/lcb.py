"""LiveCodeBench-hard rescue problems: competition tasks 32B models fail.

Problem pool: the LiveCodeBench leaderboard's per-problem data
(performances_generation.json) shows ~95 hard-split problems where at least
two of three 32B-class open models score pass@1 = 0. ``CURATED_HARD_IDS``
picks recent (2025-01..04) stdin-style ones from that pool; problems and
ground-truth test cases download from the HuggingFace dataset
``livecodebench/code_generation_lite`` (test6.jsonl) on first use.

Verification feeds each test case to the candidate program on stdin in a
subprocess and compares stdout (whitespace-normalized). Case count and input
size are capped to keep local verification tractable, so a "pass" here is
against a strong subset of the official cases, not all of them.
"""

import base64
import json
import pickle
import subprocess
import sys
import zlib

from pydantic import BaseModel, Field

from .code_eval import VerifyResult

# Hard-split problems failed (pass@1 = 0) by >=2 of: OpenReasoning-Nemotron-32B,
# EXAONE-4.0-32B, OpenCodeReasoning-Nemotron-1.1-32B — all stdin-style,
# contest dates 2025-01..04 (newest window, lowest contamination risk).
CURATED_HARD_IDS = [
    "abc397_d",
    "arc192_e",
    "arc193_b",
    "arc192_b",
    "abc397_g",
    "arc195_c",
    "arc196_c",
    "abc399_e",
]

LCB_STATEMENT_TEMPLATE = """Solve the following competitive programming problem.

{content}

Requirements:
- Read the input from standard input and write the answer to standard output,
  exactly in the format the problem specifies.
- The program must be a complete, runnable Python script.
- Mind the constraints: choose an algorithm efficient enough for the stated
  input bounds.

Output: a single ```python code block containing the full program. No
commentary outside the code block."""


class LcbCase(BaseModel):
    """One stdin/stdout test case."""

    input: str
    output: str


class LcbProblem(BaseModel):
    """One LiveCodeBench problem with its ground-truth cases."""

    id: str
    title: str = ""
    platform: str = ""
    contest_date: str = ""
    content: str = Field(..., description="Full problem statement.")
    cases: list[LcbCase]


def build_lcb_statement(problem: LcbProblem) -> str:
    return LCB_STATEMENT_TEMPLATE.format(content=problem.content)


def _decode_private_cases(blob: str) -> list[dict]:
    return json.loads(pickle.loads(zlib.decompress(base64.b64decode(blob.encode()))))


def load_problems(
    ids: list[str] | None = None,
    max_cases: int = 15,
    max_input_bytes: int = 100_000,
) -> list[LcbProblem]:
    """Load curated problems from the HuggingFace dataset (cached locally).

    Public cases are kept first; private cases fill up to ``max_cases``,
    skipping cases with inputs larger than ``max_input_bytes``.
    """
    from huggingface_hub import hf_hub_download

    wanted = ids if ids is not None else CURATED_HARD_IDS
    path = hf_hub_download(
        "livecodebench/code_generation_lite", "test6.jsonl", repo_type="dataset"
    )
    by_id: dict[str, LcbProblem] = {}
    with open(path) as f:
        for line in f:
            row = json.loads(line)
            if row.get("question_id") not in wanted:
                continue
            raw_cases = json.loads(row["public_test_cases"]) + _decode_private_cases(
                row["private_test_cases"]
            )
            cases = [
                LcbCase(input=c["input"], output=c["output"])
                for c in raw_cases
                if len(c["input"]) <= max_input_bytes
            ][:max_cases]
            by_id[row["question_id"]] = LcbProblem(
                id=row["question_id"],
                title=row.get("question_title", ""),
                platform=row["platform"],
                contest_date=row["contest_date"][:10],
                content=row["question_content"],
                cases=cases,
            )
    return [by_id[i] for i in wanted if i in by_id]


def _normalize(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def verify_stdin_solution(
    code: str, cases: list[LcbCase], timeout_per_case: float = 10.0
) -> VerifyResult:
    """Run ``code`` against every case, comparing normalized stdout."""
    for i, case in enumerate(cases):
        try:
            completed = subprocess.run(
                [sys.executable, "-c", code],
                input=case.input,
                capture_output=True,
                text=True,
                timeout=timeout_per_case,
            )
        except subprocess.TimeoutExpired:
            return VerifyResult(
                passed=False, output=f"case {i}: timeout after {timeout_per_case}s"
            )
        if completed.returncode != 0:
            return VerifyResult(
                passed=False,
                output=f"case {i}: crashed: {(completed.stderr or '')[-300:]}",
            )
        if _normalize(completed.stdout) != _normalize(case.output):
            return VerifyResult(
                passed=False,
                output=(
                    f"case {i}: wrong answer "
                    f"(got {completed.stdout[:120]!r}, want {case.output[:120]!r})"
                ),
            )
    return VerifyResult(passed=True)
