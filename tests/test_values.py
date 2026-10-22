"""The tagged JSON codec must round-trip every value type exactly."""

import json
import math

import pytest

from owlgo.values import UnsupportedValue, decode, encode, encode_or_repr

# Values that must survive encode -> JSON text -> decode unchanged, including their types.
ROUND_TRIP_VALUES = [
    None,
    True,
    0,
    -5,
    2**100,
    1.5,
    float("inf"),
    float("-inf"),
    "text",
    "$looks-like-a-tag",
    [1, [2, 3]],
    (1,),
    (1, [2, (3, 4)]),
    {3, 1, 2},
    frozenset({"a", "b"}),
    {"a": 1, "b": [2]},
    {1: "one", 2: "two"},
    {"$tuple": "not a tag"},
    {(1, 2): [3]},
    complex(1, -2),
]


@pytest.mark.parametrize("value", ROUND_TRIP_VALUES, ids=repr)
def test_round_trip_keeps_value_and_type(value):
    # Going through real JSON text proves the encoding is JSON-safe.
    restored = decode(json.loads(json.dumps(encode(value))))
    assert restored == value
    assert type(restored) is type(value)


def test_nan_round_trips():
    # nan != nan, so it needs its own check.
    assert math.isnan(decode(json.loads(json.dumps(encode(float("nan"))))))


def test_tuple_and_list_stay_different():
    # The whole point of the codec: (1, 2) and [1, 2] are different answers in Python.
    assert decode(encode((1, 2))) != decode(encode([1, 2]))


def test_sets_encode_in_a_stable_order():
    assert encode({3, 1, 2}) == {"$set": [1, 2, 3]}


def test_unsupported_values_raise():
    with pytest.raises(UnsupportedValue):
        encode(b"bytes")


def test_encode_or_repr_falls_back_for_big_or_strange_values():
    assert encode_or_repr([1, 2]) == [1, 2]
    assert "$repr" in encode_or_repr(list(range(10_000)))
    assert encode_or_repr(b"x") == {"$repr": "b'x'"}


def test_repr_values_cannot_be_decoded():
    with pytest.raises(UnsupportedValue):
        decode({"$repr": "something"})
