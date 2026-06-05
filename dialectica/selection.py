"""Search-frontier selection policies (the ``Selector`` protocol)."""

from .models import ThoughtData, score_of


class BeamSearch:
    """Keep the top-``width`` nodes by score (classic beam search)."""

    def __init__(self, width: int = 3):
        self.width = width

    def select(self, nodes: list[ThoughtData]) -> list[ThoughtData]:
        return sorted(nodes, key=score_of, reverse=True)[: self.width]


class GreedySearch:
    """Keep only the single highest-scoring node (beam width 1)."""

    def select(self, nodes: list[ThoughtData]) -> list[ThoughtData]:
        return sorted(nodes, key=score_of, reverse=True)[:1]
