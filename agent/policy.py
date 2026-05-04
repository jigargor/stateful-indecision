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
    def __init__(self, action_vocab: ActionVocabulary):
        self.vocab = action_vocab

    def propose(self, state) -> ActionDistribution:
        categories = self.vocab.categories
        top_scores: dict[str, float] = {top: 1.0 for top in sorted(categories.keys())}
        for top, leaves in categories.items():
            for leaf in leaves:
                affinity = self.vocab.category_affinity(leaf, top)
                if affinity > 0:
                    top_scores[top] += affinity

        # If the working notebook context is saturated, prefer outward research.
        if getattr(state, "recent_notebook", None) and len(state.recent_notebook) >= 5:
            top_scores["RESEARCH"] = top_scores.get("RESEARCH", 1.0) * 1.25
            top_scores["PONDER"] = top_scores.get("PONDER", 1.0) * 0.85

        # If the agent is not already in commons, bias slightly toward social discovery.
        if not getattr(state, "in_commons", False):
            top_scores["RIFF"] = top_scores.get("RIFF", 1.0) * 1.10

        top_total = sum(top_scores.values())
        top_dist = {top: score / top_total for top, score in top_scores.items()}
        sub_dist: dict[str, dict[str, float]] = {}
        for top, leaves in categories.items():
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
