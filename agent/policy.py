from __future__ import annotations

import random
from dataclasses import dataclass, field

from schemas.events import ActionVocabulary


@dataclass
class ActionDistribution:
    top_dist: dict[str, float]
    sub_dist: dict[str, dict[str, float]]
    leaf_category_weights: dict[str, dict[str, float]] = field(default_factory=dict)


class Policy:
    def __init__(self, action_vocab: ActionVocabulary, blocked_leaves: set[str] | None = None):
        self.vocab = action_vocab
        raw = blocked_leaves or set()
        all_known = set(action_vocab.all_leaves)
        unknown = raw - all_known
        if unknown:
            raise ValueError(
                f"blocked_leaf_actions contains unknown leaf names: {sorted(unknown)}. "
                f"Known leaves: {sorted(all_known)}"
            )
        self.blocked_leaves: frozenset[str] = frozenset(raw)

    def _allowed_leaves(self, top: str) -> list[str]:
        return [leaf for leaf in self.vocab.categories.get(top, []) if leaf not in self.blocked_leaves]

    def propose(self, state) -> ActionDistribution:
        categories = self.vocab.categories
        top_scores: dict[str, float] = {}
        for top in sorted(categories.keys()):
            allowed = self._allowed_leaves(top)
            if not allowed:
                continue
            top_scores[top] = 1.0
            for leaf in allowed:
                affinity = self.vocab.category_affinity(leaf, top)
                if affinity > 0:
                    top_scores[top] += affinity

        # Contextual biases only apply to categories that have allowed leaves.
        if getattr(state, "recent_notebook", None) and len(state.recent_notebook) >= 5:
            if "RESEARCH" in top_scores:
                top_scores["RESEARCH"] *= 1.25
            if "PONDER" in top_scores:
                top_scores["PONDER"] *= 0.85

        if not getattr(state, "in_commons", False):
            if "RIFF" in top_scores:
                top_scores["RIFF"] *= 1.10

        top_total = sum(top_scores.values())
        if top_total <= 0:
            raise ValueError("all action leaves are masked; no legal action remains")
        top_dist = {top: score / top_total for top, score in top_scores.items()}
        sub_dist: dict[str, dict[str, float]] = {}
        for top, _leaves in categories.items():
            leaves = self._allowed_leaves(top)
            if not leaves:
                continue
            leaf_scores: dict[str, float] = {}
            for leaf in leaves:
                affinity = self.vocab.category_affinity(leaf, top)
                leaf_scores[leaf] = affinity if affinity > 0 else 1.0
            leaf_total = sum(leaf_scores.values())
            sub_dist[top] = {leaf: score / leaf_total for leaf, score in leaf_scores.items()}
        return ActionDistribution(
            top_dist=top_dist,
            sub_dist=sub_dist,
            leaf_category_weights=self.vocab.leaf_category_weights,
        )


def sample(dist: ActionDistribution, rng: random.Random) -> tuple[str, str, int]:
    sample_seed = rng.getrandbits(64)
    local_rng = random.Random(sample_seed)
    top_actions = list(dist.top_dist.keys())
    top_weights = list(dist.top_dist.values())
    top_action = local_rng.choices(top_actions, weights=top_weights, k=1)[0]
    sub_actions = list(dist.sub_dist[top_action].keys())
    sub_weights = list(dist.sub_dist[top_action].values())
    sub_action = local_rng.choices(sub_actions, weights=sub_weights, k=1)[0]
    return top_action, sub_action, sample_seed
