## Summary

- 

## Validation

- [ ] `uv run pytest -q`
- [ ] `python -m tools.verify_chains --ecosystem alpha`
- [ ] `python -m tools.verify_chains --ecosystem beta`
- [ ] `python -m tools.check_run_config_hashes --base-dir .`

## Checklist

- [ ] Updated `_plans/auton_and_agent_layers.md` §3 lookup table if file-path mappings changed
- [ ] Updated schema exports if payload models changed (`python -m tools.export_event_schemas`)
- [ ] Reviewed run-config hash sync impact on versioned configs

## Risks / Rollback

- Risks:
- Rollback plan:
