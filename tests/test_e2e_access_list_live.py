"""Live end-to-end test for the ``sees=`` access-list primitive.

Deselected by default (``addopts = -m 'not e2e'``). Run explicitly with:

    uv run pytest -m e2e_access

Skipped automatically when no cliproxy/OpenAI-compatible endpoint is configured
(``OPENAI_API_BASE`` + ``OPENAI_API_KEY``), or when the configured model is the
default Google model (which needs ``GOOGLE_API_KEY`` separately). This is the
realistic counterpart to the mocked access-list scenarios in
``tests/test_workflow_feature.py`` — it proves the primitive works against a
live LLM, not just a fake ``run_agent``.

Configure via the cliproxy env (see CLAUDE.md "Gotchas"):

    export DEFAULT_MODEL_CONFIG=openai:glm-5.2
    export OPENAI_API_BASE=... OPENAI_API_KEY=...
    uv run pytest -m e2e_access
"""

import os

import pytest

from dialectica import workflow as wf
from dialectica.workflow import Workflow

pytestmark = [
    pytest.mark.e2e_access,
    pytest.mark.skipif(
        not (
            os.getenv("OPENAI_API_BASE")
            and os.getenv("OPENAI_API_KEY")
            and os.getenv("DEFAULT_MODEL_CONFIG", "").startswith("openai:")
        ),
        reason="needs cliproxy: OPENAI_API_BASE + OPENAI_API_KEY + "
        "DEFAULT_MODEL_CONFIG=openai:<model>",
    ),
]


async def test_access_list_makes_prior_output_visible_to_a_live_model():
    """A ``sees=[label]`` agent can quote a fact the first agent produced.

    The first agent is told a secret word and asked to emit it. The second
    agent has NO direct knowledge of the secret — only what the access list
    injects from the first agent's output. If the primitive works against a
    real model, the second agent's answer contains the secret; without the
    access list (isolation) it cannot.
    """
    secret = "CIRRUS-9"

    async def script_sees():
        await wf.agent(
            f"Write down this value verbatim: {secret}. "
            "Output the value and nothing else.",
            label="secret_holder",
        )
        return await wf.agent(
            "The prior context above contains a value. Output that value "
            "verbatim and nothing else.",
            label="retriever",
            sees=["secret_holder"],
        )

    result = await Workflow(script_sees).run()
    assert isinstance(result, str)
    assert secret in result.upper(), (
        f"access list did not surface prior output to the live model; got: {result!r}"
    )


async def test_default_isolation_holds_against_a_live_model():
    """Without ``sees=``, the second agent cannot reproduce the first's secret.

    This is the anti-collapse guarantee: by default an agent sees only its own
    prompt, never another agent's transcript. A live model given no access
    list must NOT emit the secret the first agent held.
    """
    secret = "STRATUS-4"

    async def script_isolated():
        await wf.agent(
            f"The secret codeword for this run is {secret}. "
            "Reply with only the codeword, nothing else.",
            label="secret_holder",
        )
        return await wf.agent(
            "You do not know any secret. If you were given prior context "
            "containing a codeword, reply with ONLY that codeword. "
            "Otherwise reply with the single word UNKNOWN.",
            label="retriever",
        )

    result = await Workflow(script_isolated).run()
    assert isinstance(result, str)
    assert secret not in result.upper(), (
        f"isolation leaked prior output to the live model; got: {result!r}"
    )
