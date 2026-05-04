from __future__ import annotations

from pathlib import Path

from schemas.events import ActionVocabulary


def test_action_vocabulary_shape() -> None:
    vocab = ActionVocabulary.load(Path("seeds/action_vocabulary.json"))
    assert vocab.version == "0.2.0"
    assert len(vocab.categories) == 6

    leaves = vocab.all_leaves
    assert len(leaves) == 24
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


def test_primary_category_matches_listing() -> None:
    """The primary (highest-weight) category for each leaf should match
    the category it's listed under, confirming the listing is a 'best fit'."""
    vocab = ActionVocabulary.load(Path("seeds/action_vocabulary.json"))
    listing_category = {}
    for cat, leaves in vocab.categories.items():
        for leaf in leaves:
            listing_category[leaf] = cat

    mismatches = []
    for leaf in vocab.all_leaves:
        primary = vocab.primary_category(leaf)
        listed = listing_category[leaf]
        if primary != listed:
            mismatches.append(f"{leaf}: primary={primary}, listed={listed}")

    assert not mismatches, f"primary category != listing category:\n" + "\n".join(mismatches)
