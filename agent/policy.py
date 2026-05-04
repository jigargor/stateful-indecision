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
        _ = state
        categories = self.vocab.categories
        top_actions = sorted(categories.keys())
        top_prob = 1.0 / len(top_actions)
        top_dist = {top: top_prob for top in top_actions}
        sub_dist: dict[str, dict[str, float]] = {}
        for top, leaves in categories.items():
            leaf_prob = 1.0 / len(leaves)
            sub_dist[top] = {leaf: leaf_prob for leaf in leaves}
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
