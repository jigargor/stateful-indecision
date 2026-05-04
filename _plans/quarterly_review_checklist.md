# Quarterly Auton Alignment Review

Run this review at least once per quarter.

## Inputs

- `_plans/auton_and_agent_layers.md`
- `README.md`
- `AGENTS.md`
- `run_config*.json`
- `schemas/generated/*.schema.json`

## Checklist

- [ ] Re-validate paper-version pin and note if a new Auton revision exists.
- [ ] Reconcile completed vs pending action items in `_plans/auton_and_agent_layers.md`.
- [ ] Archive completed wave notes into a dated review summary.
- [ ] Confirm run-config fields and hash checks remain current.
- [ ] Re-export schema artifacts and confirm they match runtime payloads.
- [ ] Re-run baseline validation commands:
  - [ ] `uv run pytest -q`
  - [ ] `python -m tools.verify_chains --ecosystem alpha`
  - [ ] `python -m tools.verify_chains --ecosystem beta`
  - [ ] `python -m tools.check_run_config_hashes --base-dir .`

## Review Outcome

- Date:
- Reviewer:
- Major changes:
- Risks:
- Next quarter priorities:
