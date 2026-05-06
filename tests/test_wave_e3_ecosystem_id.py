"""Wave E3 — Ecosystem ID generalization tests.

Covers: grammar validation, reserved-word rejection, backward compatibility,
path resolution, firewall safety, run-lock isolation, and S3 sync compatibility
for arbitrary grammar-legal ecosystem IDs.
"""
from __future__ import annotations

import pytest

from infra.storage import (
    EcosystemStorage,
    FirewallError,
    _ECOSYSTEM_ID_RE,
    _RESERVED_ECOSYSTEM_IDS,
    validate_ecosystem_id,
)


# ---------------------------------------------------------------------------
# A) Grammar validation — valid IDs accepted
# ---------------------------------------------------------------------------


class TestValidEcosystemIds:
    @pytest.mark.parametrize(
        "eco_id",
        [
            "alpha",
            "beta",
            "prod",
            "sandbox-01",
            "my-project",
            "a",
            "my_ecosystem_2",
            "a" + "b" * 62,  # 63 chars — max length
        ],
    )
    def test_valid_ids_accepted(self, eco_id: str) -> None:
        assert validate_ecosystem_id(eco_id) == eco_id

    def test_whitespace_is_stripped(self) -> None:
        assert validate_ecosystem_id("  alpha  ") == "alpha"


# ---------------------------------------------------------------------------
# B) Grammar validation — invalid IDs rejected
# ---------------------------------------------------------------------------


class TestInvalidEcosystemIds:
    @pytest.mark.parametrize(
        "eco_id,reason",
        [
            ("", "empty string"),
            ("0bad", "starts with digit"),
            ("-bad", "starts with hyphen"),
            ("_bad", "starts with underscore"),
            ("Alpha", "contains uppercase"),
            ("UPPER", "all uppercase"),
            ("a.b", "contains dot"),
            ("a/b", "contains slash"),
            ("a\\b", "contains backslash"),
            ("a" + "b" * 63, "64 chars — exceeds max"),
            ("../escape", "path traversal"),
            ("a b", "contains space"),
            ("a\x00b", "contains null byte"),
        ],
    )
    def test_invalid_ids_rejected(self, eco_id: str, reason: str) -> None:
        with pytest.raises(ValueError):
            validate_ecosystem_id(eco_id)


# ---------------------------------------------------------------------------
# C) Reserved word rejection
# ---------------------------------------------------------------------------


class TestReservedIds:
    @pytest.mark.parametrize(
        "eco_id",
        sorted(_RESERVED_ECOSYSTEM_IDS),
    )
    def test_reserved_ids_rejected(self, eco_id: str) -> None:
        with pytest.raises(ValueError, match="reserved word"):
            validate_ecosystem_id(eco_id)

    def test_reserved_set_contains_expected(self) -> None:
        for word in ("agents", "corpora", "evaluation", "tmp", "test", "none", "null", "default"):
            assert word in _RESERVED_ECOSYSTEM_IDS

    def test_reserved_set_includes_known_dangerous_names(self) -> None:
        required = {"agents", "corpora", "evaluation", "public", "commons", "roundtable", "townhall"}
        assert required.issubset(_RESERVED_ECOSYSTEM_IDS)


# ---------------------------------------------------------------------------
# D) Boundary tests
# ---------------------------------------------------------------------------


class TestBoundaryIds:
    def test_single_char_min_length(self) -> None:
        assert validate_ecosystem_id("a") == "a"

    def test_max_length_63(self) -> None:
        eco_id = "a" + "b" * 62
        assert len(eco_id) == 63
        assert validate_ecosystem_id(eco_id) == eco_id

    def test_64_chars_rejected(self) -> None:
        eco_id = "a" + "b" * 63
        assert len(eco_id) == 64
        with pytest.raises(ValueError):
            validate_ecosystem_id(eco_id)


# ---------------------------------------------------------------------------
# E) Backward compatibility — alpha/beta work identically
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_alpha_storage_creates_correctly(self, tmp_path) -> None:
        storage = EcosystemStorage("alpha", tmp_path)
        assert storage.ecosystem_id == "alpha"
        assert storage.ecosystem_dir == (tmp_path / "ecosystems" / "alpha").resolve()
        assert storage.ecosystem_dir.is_dir()

    def test_beta_storage_creates_correctly(self, tmp_path) -> None:
        storage = EcosystemStorage("beta", tmp_path)
        assert storage.ecosystem_id == "beta"
        assert storage.ecosystem_dir == (tmp_path / "ecosystems" / "beta").resolve()
        assert storage.ecosystem_dir.is_dir()

    def test_alpha_agent_dir(self, tmp_path) -> None:
        storage = EcosystemStorage("alpha", tmp_path)
        path = storage.agent_dir("agent-001")
        expected = (tmp_path / "ecosystems" / "alpha" / "agents" / "agent-001").resolve()
        assert path == expected

    def test_beta_run_lock(self, tmp_path) -> None:
        storage = EcosystemStorage("beta", tmp_path)
        with storage.acquire_run_lock("agent-001"):
            assert (storage.ecosystem_dir / ".run.lock.agent-001").exists()
        assert not (storage.ecosystem_dir / ".run.lock.agent-001").exists()


# ---------------------------------------------------------------------------
# F) New-grammar ID storage operations
# ---------------------------------------------------------------------------


class TestNewGrammarStorage:
    @pytest.mark.parametrize(
        "eco_id",
        ["prod", "sandbox-01", "my-ecosystem-2", "dev"],
    )
    def test_storage_creation(self, tmp_path, eco_id: str) -> None:
        storage = EcosystemStorage(eco_id, tmp_path)
        assert storage.ecosystem_id == eco_id
        assert storage.ecosystem_dir.is_dir()
        assert (storage.ecosystem_dir / "agents").is_dir()

    def test_public_ledger_path(self, tmp_path) -> None:
        storage = EcosystemStorage("prod", tmp_path)
        path = storage.public_ledger()
        assert path == (tmp_path / "ecosystems" / "prod" / "public.jsonl").resolve()

    def test_evaluation_ledger_path(self, tmp_path) -> None:
        storage = EcosystemStorage("sandbox-01", tmp_path)
        path = storage.evaluation_ledger()
        assert path == (tmp_path / "ecosystems" / "sandbox-01" / "evaluation.jsonl").resolve()

    def test_commons_ledger_path(self, tmp_path) -> None:
        storage = EcosystemStorage("my-project", tmp_path)
        path = storage.commons_ledger()
        assert path == (tmp_path / "ecosystems" / "my-project" / "commons.jsonl").resolve()

    def test_agent_dir_resolution(self, tmp_path) -> None:
        storage = EcosystemStorage("prod", tmp_path)
        path = storage.agent_dir("agent-001")
        expected = (tmp_path / "ecosystems" / "prod" / "agents" / "agent-001").resolve()
        assert path == expected
        assert path.is_dir()

    def test_agent_constitution(self, tmp_path) -> None:
        storage = EcosystemStorage("prod", tmp_path)
        path = storage.agent_constitution("agent-001")
        assert path.name == "constitution.md"
        assert "ecosystems/prod/agents/agent-001" in str(path)

    def test_agent_notebook(self, tmp_path) -> None:
        storage = EcosystemStorage("prod", tmp_path)
        path = storage.agent_notebook("agent-001")
        assert path.name == "notebook.jsonl"
        assert "ecosystems/prod/agents/agent-001" in str(path)

    def test_agent_research_dir(self, tmp_path) -> None:
        storage = EcosystemStorage("prod", tmp_path)
        path = storage.agent_research_dir("agent-001")
        assert path.name == "research"
        assert path.is_dir()

    def test_corpus_dir(self, tmp_path) -> None:
        storage = EcosystemStorage("prod", tmp_path)
        path = storage.corpus_dir()
        assert path == (tmp_path / "corpora" / "prod").resolve()
        assert path.is_dir()

    def test_roundtable_ledger(self, tmp_path) -> None:
        storage = EcosystemStorage("sandbox-01", tmp_path)
        path = storage.roundtable_ledger()
        assert path.name == "roundtable.jsonl"

    def test_townhall_ledger(self, tmp_path) -> None:
        storage = EcosystemStorage("sandbox-01", tmp_path)
        path = storage.townhall_ledger()
        assert path.name == "townhall.jsonl"

    def test_syncable_ledger_paths(self, tmp_path) -> None:
        storage = EcosystemStorage("prod", tmp_path)
        paths = storage.syncable_ledger_paths()
        assert len(paths) == 5
        names = {p.name for p in paths}
        assert names == {
            "public.jsonl",
            "evaluation.jsonl",
            "commons.jsonl",
            "roundtable.jsonl",
            "townhall.jsonl",
        }

    def test_blocked_for_agent_unchanged(self) -> None:
        assert EcosystemStorage.blocked_for_agent() == {"evaluation.jsonl"}


# ---------------------------------------------------------------------------
# G) Firewall and path safety — new-grammar IDs
# ---------------------------------------------------------------------------


class TestFirewallNewGrammar:
    def test_resolve_stays_within_ecosystem(self, tmp_path) -> None:
        storage = EcosystemStorage("my-eco", tmp_path)
        path = storage.resolve("public.jsonl")
        assert str(path).startswith(str(storage.ecosystem_dir))

    def test_path_traversal_blocked(self, tmp_path) -> None:
        storage = EcosystemStorage("my-eco", tmp_path)
        with pytest.raises(FirewallError):
            storage.resolve("../../etc/passwd")

    def test_cross_ecosystem_escape_blocked(self, tmp_path) -> None:
        EcosystemStorage("eco-a", tmp_path)
        storage_b = EcosystemStorage("eco-b", tmp_path)
        with pytest.raises(FirewallError):
            storage_b.resolve("../eco-a/public.jsonl")

    def test_no_path_overlap_between_ecosystems(self, tmp_path) -> None:
        s1 = EcosystemStorage("alpha", tmp_path)
        s2 = EcosystemStorage("alpha-copy", tmp_path)
        assert s1.ecosystem_dir != s2.ecosystem_dir
        with pytest.raises(FirewallError):
            s1.resolve("../alpha-copy/public.jsonl")

    def test_corpus_dir_within_base(self, tmp_path) -> None:
        storage = EcosystemStorage("prod", tmp_path)
        corpus = storage.corpus_dir()
        assert str(corpus).startswith(str(tmp_path.resolve()))

    def test_invalid_agent_id_blocked_new_ecosystem(self, tmp_path) -> None:
        storage = EcosystemStorage("prod", tmp_path)
        with pytest.raises(FirewallError):
            storage.agent_dir("../agent-002")


# ---------------------------------------------------------------------------
# H) Run-lock isolation — new-grammar IDs
# ---------------------------------------------------------------------------


class TestRunLockIsolation:
    def test_lock_per_ecosystem(self, tmp_path) -> None:
        s1 = EcosystemStorage("eco-a", tmp_path)
        s2 = EcosystemStorage("eco-b", tmp_path)

        with s1.acquire_run_lock("agent-1"):
            lock1 = s1.ecosystem_dir / ".run.lock.agent-1"
            assert lock1.exists()
            with s2.acquire_run_lock("agent-1"):
                lock2 = s2.ecosystem_dir / ".run.lock.agent-1"
                assert lock2.exists()
                assert lock1 != lock2

    def test_lock_no_collision_similar_names(self, tmp_path) -> None:
        s1 = EcosystemStorage("foo", tmp_path)
        s2 = EcosystemStorage("foo-bar", tmp_path)

        with s1.acquire_run_lock("agent-1"):
            with s2.acquire_run_lock("agent-1"):
                l1 = s1.ecosystem_dir / ".run.lock.agent-1"
                l2 = s2.ecosystem_dir / ".run.lock.agent-1"
                assert l1.exists()
                assert l2.exists()
                assert l1 != l2

    def test_lock_cleanup(self, tmp_path) -> None:
        storage = EcosystemStorage("prod", tmp_path)
        with storage.acquire_run_lock("agent-x"):
            assert (storage.ecosystem_dir / ".run.lock.agent-x").exists()
        assert not (storage.ecosystem_dir / ".run.lock.agent-x").exists()


# ---------------------------------------------------------------------------
# I) S3 sync compatibility — new-grammar IDs
# ---------------------------------------------------------------------------


class TestS3SyncNewGrammar:
    def test_sync_state_round_trip_new_id(self, tmp_path) -> None:
        from infra.s3_sync import LedgerCursor, SyncState, load_state, save_state

        state_path = tmp_path / "state.json"
        state = SyncState(
            ecosystem_id="prod",
            cursors={
                "public.jsonl": LedgerCursor(
                    rel_path="public.jsonl",
                    uploaded_through_byte_offset=512,
                    uploaded_through_record_hash="d" * 64,
                    last_event_id="evt-42",
                    s3_key="ecosystems/prod/public.jsonl",
                ),
            },
        )
        save_state(state_path, state)
        loaded = load_state(state_path)
        assert loaded.ecosystem_id == "prod"
        assert loaded.cursors["public.jsonl"].uploaded_through_byte_offset == 512

    def test_ecosystem_s3_prefix(self) -> None:
        from infra.s3_sync import S3SyncConfig, _ecosystem_s3_prefix

        cfg = S3SyncConfig(bucket="test-bucket", prefix="my-prefix")
        assert _ecosystem_s3_prefix(cfg, "prod") == "my-prefix/ecosystems/prod"
        assert _ecosystem_s3_prefix(cfg, "sandbox-01") == "my-prefix/ecosystems/sandbox-01"

    def test_ecosystem_s3_prefix_no_collision(self) -> None:
        from infra.s3_sync import S3SyncConfig, _ecosystem_s3_prefix

        cfg = S3SyncConfig(bucket="test-bucket")
        p1 = _ecosystem_s3_prefix(cfg, "alpha")
        p2 = _ecosystem_s3_prefix(cfg, "alpha-copy")
        assert p1 != p2
        assert not p1.startswith(p2)
        assert not p2.startswith(p1 + "/")

    def test_sync_state_file_naming(self, tmp_path) -> None:
        from infra.s3_sync import SyncState, save_state

        for eco_id in ("prod", "sandbox-01", "my-project"):
            path = tmp_path / f"{eco_id}.json"
            save_state(path, SyncState(ecosystem_id=eco_id))
            assert path.exists()

    def test_syncable_ledger_paths_within_firewall(self, tmp_path) -> None:
        storage = EcosystemStorage("prod", tmp_path)
        eco_dir = str(storage.ecosystem_dir)
        for p in storage.syncable_ledger_paths():
            assert str(p).startswith(eco_dir)


# ---------------------------------------------------------------------------
# J) Regex pattern sanity
# ---------------------------------------------------------------------------


class TestRegexPattern:
    def test_regex_rejects_path_separators(self) -> None:
        assert not _ECOSYSTEM_ID_RE.match("a/b")
        assert not _ECOSYSTEM_ID_RE.match("a\\b")

    def test_regex_rejects_dots(self) -> None:
        assert not _ECOSYSTEM_ID_RE.match("..")
        assert not _ECOSYSTEM_ID_RE.match(".")
        assert not _ECOSYSTEM_ID_RE.match("a.b")

    def test_regex_rejects_empty(self) -> None:
        assert not _ECOSYSTEM_ID_RE.match("")

    def test_regex_accepts_hyphens_underscores(self) -> None:
        assert _ECOSYSTEM_ID_RE.match("a-b")
        assert _ECOSYSTEM_ID_RE.match("a_b")
        assert _ECOSYSTEM_ID_RE.match("a-b-c_d")
