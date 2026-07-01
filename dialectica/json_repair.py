"""Shared JSON-repair helpers for schema-constrained LLM output.

Split out of the former ``gan_evaluator.py`` when the ToT+GAN engine was
demoted to a reference pattern (``examples/patterns/tot_gan_pattern.py``):
these two functions are genuinely shared infrastructure — ``workflow.py``'s
``agent(schema=...)`` depends on them for its own fence/escape-repair — while
everything else in that module (the GAN refine loop, the discriminator
circuit breaker) was engine-specific and did not survive the demotion.
"""

import re

# Local models (e.g. gemma via ollama) often wrap their JSON verdict in a
# markdown code fence even when asked for raw JSON.
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)

# Backslash not starting a valid JSON escape — local models emit things like
# LaTeX "\(O(n)\)" inside JSON strings, which strict parsing rejects.
_BAD_ESCAPE_RE = re.compile(r'\\(?![\\"/bfnrtu])')


def strip_code_fence(text: str) -> str:
    """Return the body of a markdown code fence, or ``text`` unchanged."""
    match = _FENCE_RE.match(text)
    return match.group(1) if match else text


def repair_json_escapes(text: str) -> str:
    """Escape lone backslashes that would make JSON string parsing fail."""
    return _BAD_ESCAPE_RE.sub(r"\\\\", text)
