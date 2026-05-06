# Notebook export — ecosystem `beta`

- **Generated:** 2026-05-06T08:36:51.328395+00:00
- **N-gram size:** 18 (character n-grams on alphanumeric-only fold)
- **Corpus pool chars:** 13667
- **Executed raw pool chars:** 1500152 (included: True)

## How to read `novelty_estimate`

This is **one minus** the fraction of notebook character n-grams that also appear in the combined source pool (corpus markdown + optional `raw_output`). High values mean the notebook **phrasing** is less often byte-for-byte recoverable from that pool — not that claims are empirically novel or correct.

## Per-agent rollups

- **beta-agent-1:** entries=59, chars=1275747, weighted_novelty≈0.7852, mean_overlap≈0.3002
- **beta-agent-2:** entries=68, chars=1037257, weighted_novelty≈0.75, mean_overlap≈0.2568
- **beta-agent-3:** entries=25, chars=247103, weighted_novelty≈0.8128, mean_overlap≈0.2361
