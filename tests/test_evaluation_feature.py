"""Step definitions for features/adversarial_evaluation.feature — mocked LLM."""

import asyncio
from unittest.mock import patch

from helpers import make_call_agent
from pytest_bdd import given, parsers, scenarios, then, when

from dialectica.agent_factory import create_agent
from dialectica.gan_evaluator import AdversarialEvaluator
from dialectica.models import DiscriminatorVerdict

scenarios("features/adversarial_evaluation.feature")


@given(
    parsers.parse(
        "an adversarial evaluator with max rounds {rounds:d} and score threshold {threshold:g}"
    ),
    target_fixture="evaluator",
)
def evaluator(rounds: int, threshold: float):
    generator = create_agent(role="Generator", role_name="Generator")
    discriminator = create_agent(
        role="Discriminator",
        role_name="Discriminator",
        output_schema=DiscriminatorVerdict,
    )
    return AdversarialEvaluator(
        generator=generator,
        discriminator=discriminator,
        max_rounds=rounds,
        score_threshold=threshold,
    )


@given(
    parsers.parse('an adversarial evaluator with custom criteria "{criteria}"'),
    target_fixture="evaluator",
)
def evaluator_with_criteria(criteria: str):
    generator = create_agent(role="Generator", role_name="Generator")
    discriminator = create_agent(
        role="Discriminator",
        role_name="Discriminator",
        output_schema=DiscriminatorVerdict,
    )
    return AdversarialEvaluator(
        generator=generator,
        discriminator=discriminator,
        criteria=criteria,
    )


@given(
    parsers.parse('the discriminator returns scores "{scores}"'),
    target_fixture="llm_spec",
)
def llm_spec_from_scores(scores: str):
    verdicts = [{"score": float(s)} for s in scores.split(",")]
    return {"verdicts": verdicts, "refined": "A refined, stronger thought."}


@given("the discriminator always returns malformed output", target_fixture="llm_spec")
def llm_spec_malformed():
    return {"malformed": True, "refined": "A refined, stronger thought."}


@given(
    parsers.parse("the discriminator returns score {score:g} with termination"),
    target_fixture="llm_spec",
)
def llm_spec_with_termination(score: float):
    return {
        "verdicts": [{"score": score, "should_terminate": True}],
        "refined": "A refined, stronger thought.",
    }


@given(parsers.parse('the generator refines thoughts to "{refined}"'))
def generator_refines_to(llm_spec, refined: str):
    llm_spec["refined"] = refined


def _build_fake(llm_spec):
    if llm_spec.get("malformed"):

        async def fake(agent, instruction: str) -> str:
            if "Discriminator" in agent.name:
                return "this is not a JSON verdict"
            return llm_spec["refined"]

        return fake
    return make_call_agent(llm_spec["verdicts"], refined=llm_spec["refined"])


@when(parsers.parse('the evaluator judges "{thought}"'), target_fixture="result")
def judge(evaluator, llm_spec, thought: str):
    fake = _build_fake(llm_spec)
    instructions: list[str] = []

    async def recording(agent, instruction: str) -> str:
        if "Discriminator" in agent.name:
            instructions.append(instruction)
        return await fake(agent, instruction)

    with patch("dialectica.agent_runtime.run_agent", recording):
        result = asyncio.run(evaluator.evaluate(thought, {"problem": "p"}))
    llm_spec["instructions"] = instructions
    return result


@when(
    parsers.parse('the evaluator judges "{thought}" expecting failure'),
    target_fixture="failure",
)
def judge_expecting_failure(evaluator, llm_spec, thought: str):
    fake = _build_fake(llm_spec)
    with patch("dialectica.agent_runtime.run_agent", fake):
        try:
            asyncio.run(evaluator.evaluate(thought, {"problem": "p"}))
        except RuntimeError as e:
            return e
    return None


@then(parsers.parse("the result score is {score:g}"))
def result_score_is(result, score: float):
    assert result.score == score


@then(parsers.parse("the loop ran {rounds:d} round"))
@then(parsers.parse("the loop ran {rounds:d} rounds"))
def loop_ran_rounds(result, rounds: int):
    assert result.adversarial_rounds == rounds
    assert len(result.history) == rounds


@then(parsers.parse('the refined thought is "{refined}"'))
def refined_thought_is(result, refined: str):
    assert result.refined_thought == refined


@then("the evaluation requests termination")
def evaluation_requests_termination(result):
    assert result.should_terminate is True


@then(parsers.parse('the discriminator was instructed with "{text}"'))
def discriminator_instructed_with(llm_spec, text: str):
    assert llm_spec["instructions"]
    assert all(text in i for i in llm_spec["instructions"])


@then(
    parsers.parse("the evaluation aborts after {n:d} consecutive unparseable verdicts")
)
def evaluation_aborts(failure, n: int):
    assert isinstance(failure, RuntimeError)
    assert "unparseable" in str(failure).lower()
