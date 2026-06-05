"""Validation for thought-tree nodes.

Builds a ``ThoughtData`` from raw node fields, returning the validated model or
``None`` if it fails — the model *is* the schema, so there is no intermediate
dict to keep in sync.
"""

import logging

from pydantic import ValidationError

from .models import ThoughtData

logger = logging.getLogger(__name__)


def validate_thought_node(
    thought_id: str,
    parent_id: str | None,
    content: str,
    depth: int,
    status: str = "generated",
    evaluation_score: float | None = None,
) -> ThoughtData | None:
    """Validate node fields against ``ThoughtData``.

    Returns the validated ``ThoughtData`` on success, or ``None`` if the fields
    fail validation (e.g. empty content) — the caller decides how to handle a
    rejected node.
    """
    try:
        return ThoughtData(
            parentId=parent_id,
            thoughtId=thought_id,
            thought=content,
            depth=depth,
            evaluationScore=evaluation_score,
            status=status,
        )
    except ValidationError as e:
        logger.warning("Thought node %r failed validation: %s", thought_id, e.errors())
        return None
