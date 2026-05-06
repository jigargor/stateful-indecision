# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses Semantic Versioning.

## [Unreleased]

### Changed
- Hardened run-config enforcement: hash mismatches now fail fast during config loading.
- Added known-event payload validation before append on chain write paths.
- Enforced explicit `prompt_progression` / `verifier_mode` / `reward_mode` value validation.
- Defaulted run-config tool allowlist to an explicit empty list when omitted.
- Updated run-config hard-stop target from `0.9.9` to `1.0.0`.

### Added
- Agent-path firewall checks in state building, constitution, and artifact write flows.
- CI workflow for tests, chain verification, and run-config hash checks.
- Release engineering artifacts: `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`.

## [1.0.0] - 2026-05-06

### Added
- v1.0.0 package baseline for the ledger-first single-agent runtime.
