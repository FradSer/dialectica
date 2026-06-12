"""CLI entry point: ``uv run python -m evals``.

Two suites:
- ``advice`` (default): open-ended problems, blind LLM judge.
- ``swe``: HumanEval-style code problems, verified by running unit tests —
  ground truth, no judge.

As a development tool (unlike the library), this loads ``dialectica/.env``.
"""

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from dialectica import create_engine

from .baseline import SingleCallBaseline, create_baseline_agent
from .code_eval import (
    CODE_CRITERIA,
    render_code_markdown,
    render_rescue_markdown,
    run_code_eval,
    run_rescue_eval,
)
from .code_problems import SWE_PROBLEMS
from .harness import render_markdown, run_eval
from .judge import BlindJudge, create_judge_agent
from .problems import DEFAULT_PROBLEMS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="evals", description="Compare the engine against a single-call baseline."
    )
    parser.add_argument(
        "--suite",
        choices=("advice", "swe", "lcb"),
        default="advice",
        help="advice: judged open-ended problems; swe: test-verified code "
        "problems; lcb: LiveCodeBench-hard competition problems (rescue only, "
        "downloads from HuggingFace on first use).",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="swe suite: run the engine on every problem instead of rescue "
        "mode (engine only on baseline failures).",
    )
    parser.add_argument(
        "--screen-attempts",
        type=int,
        default=2,
        help="swe rescue mode: baseline attempts before a problem counts as failed.",
    )
    parser.add_argument(
        "--no-structured-output",
        action="store_true",
        help="Disable the discriminator's JSON output schema (for backends "
        "that break on enforced JSON mode, e.g. some gemma API variants).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Number of benchmark problems to run (default: all in the suite).",
    )
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--beam-width", type=int, default=2)
    parser.add_argument("--gan-rounds", type=int, default=2)
    parser.add_argument("--threshold", type=float, default=7.0)
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Also write the full report as JSON to this path.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    load_dotenv(Path(__file__).resolve().parent.parent / "dialectica" / ".env")

    def make_engine_factory(criteria: str | None):
        def engine_factory(statement: str):
            return create_engine(
                statement,
                max_depth=args.max_depth,
                beam_width=args.beam_width,
                max_gan_rounds=args.gan_rounds,
                score_threshold=args.threshold,
                criteria=criteria,
                structured_output=not args.no_structured_output,
            )

        return engine_factory

    baseline = SingleCallBaseline(create_baseline_agent())

    if args.suite == "lcb":
        from .lcb import build_lcb_statement, load_problems, verify_stdin_solution

        problems = load_problems()[: args.limit]
        report = await run_rescue_eval(
            problems,
            engine_factory=make_engine_factory(CODE_CRITERIA),
            baseline=baseline,
            screen_attempts=args.screen_attempts,
            verifier=lambda problem, code: verify_stdin_solution(code, problem.cases),
            statement_builder=build_lcb_statement,
        )
        print(render_rescue_markdown(report))
    elif args.suite == "swe":
        problems = SWE_PROBLEMS[: args.limit]
        if args.full:
            report = await run_code_eval(
                problems,
                engine_factory=make_engine_factory(CODE_CRITERIA),
                baseline=baseline,
            )
            print(render_code_markdown(report))
        else:
            report = await run_rescue_eval(
                problems,
                engine_factory=make_engine_factory(CODE_CRITERIA),
                baseline=baseline,
                screen_attempts=args.screen_attempts,
            )
            print(render_rescue_markdown(report))
    else:
        problems = DEFAULT_PROBLEMS[: args.limit]
        report = await run_eval(
            problems,
            engine_factory=make_engine_factory(None),
            baseline=baseline,
            judge=BlindJudge(create_judge_agent()),
        )
        print(render_markdown(report))

    if args.json:
        args.json.write_text(json.dumps(report.model_dump(), indent=2))
        print(f"JSON report written to {args.json}")


if __name__ == "__main__":
    asyncio.run(main())
