from __future__ import annotations

from pathlib import Path

from schemas.events import ActionVocabulary


def test_action_vocabulary_shape() -> None:
    vocab = ActionVocabulary.load(Path("seeds/action_vocabulary.json"))
    assert vocab.version == "0.3.0"
    assert len(vocab.categories) == 6

    leaves = vocab.all_leaves
    assert len(leaves) == 26
    assert all(isinstance(leaf, str) and leaf for leaf in leaves)
    assert len(set(leaves)) == len(leaves), "duplicate leaves detected"


def test_leaf_category_weights_present() -> None:
    vocab = ActionVocabulary.load(Path("seeds/action_vocabulary.json"))
    leaves = set(vocab.all_leaves)
    weighted_leaves = set(vocab.leaf_category_weights.keys())
    assert weighted_leaves == leaves, f"mismatch: {leaves - weighted_leaves} missing weights"


def test_leaf_category_weights_sum_to_one() -> None:
    vocab = ActionVocabulary.load(Path("seeds/action_vocabulary.json"))
    for leaf, weights in vocab.leaf_category_weights.items():
        total = sum(weights.values())
        assert abs(total - 1.0) < 1e-6, f"{leaf} weights sum to {total}"


def test_leaf_category_weights_reference_valid_categories() -> None:
    vocab = ActionVocabulary.load(Path("seeds/action_vocabulary.json"))
    valid_categories = set(vocab.categories.keys())
    for leaf, weights in vocab.leaf_category_weights.items():
        for cat in weights:
            assert cat in valid_categories, f"{leaf} references unknown category {cat}"


KNOWN_CROSS_CATEGORY_LEAVES: dict[str, tuple[str, str]] = {
    "DEEP_PATTERN_RECOGNITION": ("PONDER", "RESEARCH"),
}
"""Leaves whose listing category intentionally differs from their highest-weight
(primary) category.  DEEP_PATTERN_RECOGNITION is listed under PONDER for
thematic grouping but carries RESEARCH 0.40 > PONDER 0.30 — a deliberate
cross-category bridge that Wave 0 formally reclassifies rather than patching."""


def test_primary_category_matches_listing() -> None:
    """The primary (highest-weight) category for each leaf should match
    the category it's listed under, except for formally reclassified
    cross-category leaves documented in KNOWN_CROSS_CATEGORY_LEAVES."""
    vocab = ActionVocabulary.load(Path("seeds/action_vocabulary.json"))
    listing_category = {}
    for cat, leaves in vocab.categories.items():
        for leaf in leaves:
            listing_category[leaf] = cat

    for leaf, (expected_listed, expected_primary) in KNOWN_CROSS_CATEGORY_LEAVES.items():
        primary = vocab.primary_category(leaf)
        listed = listing_category[leaf]
        assert listed == expected_listed, (
            f"{leaf}: expected listing under {expected_listed}, got {listed}"
        )
        assert primary == expected_primary, (
            f"{leaf}: expected primary {expected_primary}, got {primary}"
        )

    unexpected = []
    for leaf in vocab.all_leaves:
        if leaf in KNOWN_CROSS_CATEGORY_LEAVES:
            continue
        primary = vocab.primary_category(leaf)
        listed = listing_category[leaf]
        if primary != listed:
            unexpected.append(f"{leaf}: primary={primary}, listed={listed}")

    assert not unexpected, (
        "primary category != listing category (not in known cross-category set):\n"
        + "\n".join(unexpected)
    )


def test_ponder_leaf_weight_bounds() -> None:
    """PONDER leaves are intentionally diffuse: their home-category weights
    (0.40–0.45) are the lowest primary affinity of any category.  This is by
    design — reflective actions are meant to bleed into RESEARCH, PRACTICE,
    and INDULGE so that pondering enriches adjacent categories rather than
    forming an isolated cluster.

    DEEP_PATTERN_RECOGNITION is a known cross-category leaf: it is listed
    under PONDER for thematic grouping but its highest weight is RESEARCH
    (0.40 vs PONDER 0.30).  Wave 0 formally reclassifies this as an
    intentional bridge rather than correcting the weights, preserving
    runtime behavior.

    For standard PONDER leaves, future weight edits must stay above the
    documented floor (0.35) and keep PONDER as the primary category.
    """
    vocab = ActionVocabulary.load(Path("seeds/action_vocabulary.json"))
    ponder_leaves = vocab.categories["PONDER"]

    for leaf in ponder_leaves:
        weights = vocab.leaf_category_weights[leaf]
        primary = max(weights, key=weights.__getitem__)
        ponder_weight = weights.get("PONDER", 0.0)

        if leaf in KNOWN_CROSS_CATEGORY_LEAVES:
            expected_listed, expected_primary = KNOWN_CROSS_CATEGORY_LEAVES[leaf]
            assert primary == expected_primary, (
                f"{leaf}: expected cross-category primary {expected_primary}, got {primary}"
            )
            assert ponder_weight > 0.0, (
                f"{leaf}: still expected a non-zero PONDER weight as a listed member"
            )
            continue

        assert primary == "PONDER", (
            f"{leaf}: expected PONDER as primary category, got {primary}"
        )
        assert ponder_weight >= 0.35, (
            f"{leaf}: PONDER weight {ponder_weight} is below the design floor 0.35"
        )
