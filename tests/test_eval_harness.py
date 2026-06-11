"""Unit tests for the eval harness building blocks (mocked LLM)."""

import json
from unittest.mock import patch

from dialectica import agent_runtime
from evals.harness import EvalReport, ProblemResult, count_agent_calls, render_markdown
from evals.judge import BlindJudge, create_judge_agent


def _result(problem_id: str, winner: str) -> ProblemResult:
    return ProblemResult(
        problem_id=problem_id,
        problem="p",
        engine_answer="e",
        baseline_answer="b",
        engine_calls=10,
        baseline_calls=1,
        engine_seconds=2.0,
        baseline_seconds=0.5,
        winner=winner,
        judge_reasoning=["r1", "r2"],
    )


async def test_count_agent_calls_restores_the_seam():
    async def fake(agent, instruction: str) -> str:
        return "ok"

    with patch("dialectica.agent_runtime.run_agent", fake):
        with count_agent_calls() as counter:
            await agent_runtime.run_agent(None, "x")
        assert counter.count == 1
        assert agent_runtime.run_agent is fake


async def test_judge_normalizes_winner_case_and_whitespace():
    engine_answer, baseline_answer = "ENGINE", "BASELINE"

    async def fake(agent, instruction: str) -> str:
        a_start = instruction.index("**Answer A:**")
        b_start = instruction.index("**Answer B:**")
        winner = " a " if engine_answer in instruction[a_start:b_start] else "B\n"
        return json.dumps({"winner": winner, "reasoning": "r"})

    judge = BlindJudge(create_judge_agent())
    with patch("dialectica.agent_runtime.run_agent", fake):
        comparison = await judge.compare("p", engine_answer, baseline_answer)
    assert comparison.winner == "engine"


def test_report_aggregates_verdicts():
    report = EvalReport.from_results(
        [_result("a", "engine"), _result("b", "baseline"), _result("c", "tie")]
    )
    assert (report.engine_wins, report.baseline_wins, report.ties) == (1, 1, 1)


def test_render_markdown_summarizes_report():
    report = EvalReport.from_results([_result("cloud-costs", "engine")])
    text = render_markdown(report)
    assert "cloud-costs" in text
    assert "engine" in text
    assert "1" in text
