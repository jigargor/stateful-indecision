from __future__ import annotations

import json

import pytest

from core.verifier import verify_chain
from core.writer import ChainWriter
from forums.base import ForumView
from forums.commons import Commons, CommonsView
from forums.roundtable import Roundtable, RoundRobinViolation
from forums.townhall import Townhall, TownhallViolation


class TestForumBaseDualWrite:
    def test_dual_write_produces_matching_event_ids(self, tmp_path) -> None:
        forum_path = tmp_path / "forum.jsonl"
        public_path = tmp_path / "public.jsonl"
        forum_writer = ChainWriter(forum_path)
        public_writer = ChainWriter(public_path)

        commons = Commons(forum_writer, public_writer, "alpha")
        event_id = commons.utter("agent-001", "hello world", None)

        forum_lines = forum_path.read_text(encoding="utf-8").splitlines()
        public_lines = public_path.read_text(encoding="utf-8").splitlines()

        assert len(forum_lines) == 1
        assert len(public_lines) == 1

        forum_event = json.loads(forum_lines[0])
        public_event = json.loads(public_lines[0])

        assert forum_event["event_id"] == public_event["event_id"]
        assert forum_event["event_id"] == event_id

    def test_dual_write_chains_independently(self, tmp_path) -> None:
        forum_path = tmp_path / "forum.jsonl"
        public_path = tmp_path / "public.jsonl"
        forum_writer = ChainWriter(forum_path)
        public_writer = ChainWriter(public_path)

        public_writer.append("other.event", {"x": 1}, ecosystem_id="alpha", agent_id="sys")

        commons = Commons(forum_writer, public_writer, "alpha")
        commons.utter("agent-001", "test", None)

        forum_lines = forum_path.read_text(encoding="utf-8").splitlines()
        public_lines = public_path.read_text(encoding="utf-8").splitlines()

        forum_first = json.loads(forum_lines[0])
        public_second = json.loads(public_lines[1])

        assert forum_first["prev_hash"] == "0" * 64
        assert public_second["prev_hash"] != "0" * 64

        assert verify_chain(forum_path).valid is True
        assert verify_chain(public_path).valid is True


class TestCommonsRefactored:
    def test_visit_returns_commons_view(self, tmp_path) -> None:
        forum_path = tmp_path / "commons.jsonl"
        public_path = tmp_path / "public.jsonl"
        commons = Commons(ChainWriter(forum_path), ChainWriter(public_path), "alpha")

        view = commons.visit("agent-001", "snap-1")

        assert isinstance(view, CommonsView)
        assert view.agent_ids_present == ["agent-001"]
        assert view.utterances == []

    def test_utter_returns_event_id(self, tmp_path) -> None:
        forum_path = tmp_path / "commons.jsonl"
        public_path = tmp_path / "public.jsonl"
        commons = Commons(ChainWriter(forum_path), ChainWriter(public_path), "alpha")

        event_id = commons.utter("agent-001", "hello", None)
        assert isinstance(event_id, str) and len(event_id) > 0

    def test_leave_writes_left_event(self, tmp_path) -> None:
        forum_path = tmp_path / "commons.jsonl"
        public_path = tmp_path / "public.jsonl"
        commons = Commons(ChainWriter(forum_path), ChainWriter(public_path), "alpha")

        commons.leave("agent-001", duration_steps=3)

        lines = forum_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["event_type"] == "commons.left"
        assert event["payload"]["duration_steps"] == 3

    def test_full_visit_utter_leave_cycle(self, tmp_path) -> None:
        forum_path = tmp_path / "commons.jsonl"
        public_path = tmp_path / "public.jsonl"
        commons = Commons(ChainWriter(forum_path), ChainWriter(public_path), "alpha")

        commons.visit("agent-001", "snap-1")
        commons.utter("agent-001", "first message", None)
        commons.leave("agent-001", duration_steps=1)

        assert verify_chain(forum_path).valid is True
        assert verify_chain(public_path).valid is True

        view = commons.visit("agent-002", "snap-2")
        assert len(view.utterances) == 1
        assert view.utterances[0]["payload"]["text"] == "first message"


class TestRoundtable:
    def _make_roundtable(self, tmp_path, participants=None):
        rt_path = tmp_path / "roundtable.jsonl"
        pub_path = tmp_path / "public.jsonl"
        participants = participants or ["agent-001", "agent-002", "agent-003"]
        rt = Roundtable(
            ChainWriter(rt_path), ChainWriter(pub_path), "alpha", participants=participants
        )
        return rt, rt_path, pub_path

    def test_convene(self, tmp_path) -> None:
        rt, rt_path, _ = self._make_roundtable(tmp_path)
        event_id = rt.convene("agent-001", "research update")
        assert isinstance(event_id, str)

        lines = rt_path.read_text(encoding="utf-8").splitlines()
        event = json.loads(lines[0])
        assert event["event_type"] == "roundtable.convened"
        assert event["payload"]["topic"] == "research update"

    def test_round_robin_enforcement(self, tmp_path) -> None:
        rt, _, _ = self._make_roundtable(tmp_path)
        rt.convene("agent-001", "test")

        rt.speak("agent-001", "first contribution")
        with pytest.raises(RoundRobinViolation):
            rt.speak("agent-001", "second contribution before round completes")

    def test_round_robin_allows_different_agents(self, tmp_path) -> None:
        rt, _, _ = self._make_roundtable(tmp_path)
        rt.convene("agent-001", "test")

        rt.speak("agent-001", "from agent 1")
        rt.speak("agent-002", "from agent 2")
        rt.speak("agent-003", "from agent 3")

    def test_complete_round_resets_tracking(self, tmp_path) -> None:
        rt, rt_path, _ = self._make_roundtable(tmp_path)
        rt.convene("agent-001", "test")

        rt.speak("agent-001", "round 1 contribution")
        rt.complete_round()
        rt.speak("agent-001", "round 2 contribution")

        assert verify_chain(rt_path).valid is True

    def test_non_participant_cannot_speak(self, tmp_path) -> None:
        rt, _, _ = self._make_roundtable(tmp_path)
        rt.convene("agent-001", "test")

        with pytest.raises(RoundRobinViolation):
            rt.speak("outsider-agent", "intruding")

    def test_adjourn(self, tmp_path) -> None:
        rt, rt_path, pub_path = self._make_roundtable(tmp_path)
        rt.convene("agent-001", "test")
        rt.speak("agent-001", "something")
        rt.complete_round()
        rt.adjourn("agent-001")

        assert verify_chain(rt_path).valid is True
        assert verify_chain(pub_path).valid is True

        lines = rt_path.read_text(encoding="utf-8").splitlines()
        last_event = json.loads(lines[-1])
        assert last_event["event_type"] == "roundtable.adjourned"


class TestTownhall:
    def _make_townhall(self, tmp_path):
        th_path = tmp_path / "townhall.jsonl"
        pub_path = tmp_path / "public.jsonl"
        th = Townhall(ChainWriter(th_path), ChainWriter(pub_path), "alpha")
        return th, th_path, pub_path

    def test_convene(self, tmp_path) -> None:
        th, th_path, _ = self._make_townhall(tmp_path)
        event_id = th.convene("speaker-001", "quarterly update")
        assert isinstance(event_id, str)

        lines = th_path.read_text(encoding="utf-8").splitlines()
        event = json.loads(lines[0])
        assert event["event_type"] == "townhall.convened"
        assert event["payload"]["topic"] == "quarterly update"

    def test_broadcast_only_by_speaker(self, tmp_path) -> None:
        th, _, _ = self._make_townhall(tmp_path)
        th.convene("speaker-001", "topic")

        th.broadcast("speaker-001", "announcement")

        with pytest.raises(TownhallViolation):
            th.broadcast("agent-002", "unauthorized broadcast")

    def test_one_response_per_agent(self, tmp_path) -> None:
        th, _, _ = self._make_townhall(tmp_path)
        th.convene("speaker-001", "topic")
        th.broadcast("speaker-001", "hello everyone")

        th.respond("agent-002", "my response", None)
        with pytest.raises(TownhallViolation):
            th.respond("agent-002", "second response attempt", None)

    def test_multiple_agents_can_respond(self, tmp_path) -> None:
        th, _, _ = self._make_townhall(tmp_path)
        th.convene("speaker-001", "topic")
        th.broadcast("speaker-001", "announcement")

        th.respond("agent-002", "response from 2")
        th.respond("agent-003", "response from 3")
        th.respond("agent-004", "response from 4")

    def test_adjourn_only_by_speaker(self, tmp_path) -> None:
        th, _, _ = self._make_townhall(tmp_path)
        th.convene("speaker-001", "topic")

        with pytest.raises(TownhallViolation):
            th.adjourn("agent-002")

        th.adjourn("speaker-001")

    def test_full_session_chain_verification(self, tmp_path) -> None:
        th, th_path, pub_path = self._make_townhall(tmp_path)
        th.convene("speaker-001", "findings")
        th.broadcast("speaker-001", "Here are my findings...")
        th.respond("agent-002", "Interesting, tell me more")
        th.respond("agent-003", "I disagree because...")
        th.adjourn("speaker-001")

        assert verify_chain(th_path).valid is True
        assert verify_chain(pub_path).valid is True

        lines = th_path.read_text(encoding="utf-8").splitlines()
        event_types = [json.loads(l)["event_type"] for l in lines]
        assert event_types == [
            "townhall.convened",
            "townhall.broadcast",
            "townhall.response",
            "townhall.response",
            "townhall.adjourned",
        ]
