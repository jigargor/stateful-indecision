from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from core.canonical_json import canonical_hash, canonical_json


def test_nested_keys_are_sorted() -> None:
    payload = {"z": {"b": 2, "a": 1}, "a": [3, {"d": 4, "c": 5}]}
    encoded = canonical_json(payload).decode("utf-8")
    assert encoded == '{"a":[3,{"c":5,"d":4}],"z":{"a":1,"b":2}}'


def test_equivalent_dict_orders_match() -> None:
    left = {"b": 2, "a": 1, "nested": {"y": True, "x": None}}
    right = {"nested": {"x": None, "y": True}, "a": 1, "b": 2}
    assert canonical_json(left) == canonical_json(right)


def test_supported_scalar_types_encode() -> None:
    payload = {"none": None, "bool": True, "int": 7, "float": 1.25, "str": "ok", "list": [1, "a"]}
    encoded = canonical_json(payload).decode("utf-8")
    assert '"none":null' in encoded
    assert '"bool":true' in encoded
    assert '"float":1.25' in encoded


def test_rejects_datetime_and_uuid() -> None:
    with pytest.raises(TypeError):
        canonical_json({"value": datetime.now(UTC)})
    with pytest.raises(TypeError):
        canonical_json({"value": uuid4()})


def test_canonical_hash_hex_length() -> None:
    digest = canonical_hash({"a": 1, "b": 2})
    assert len(digest) == 64
    int(digest, 16)
