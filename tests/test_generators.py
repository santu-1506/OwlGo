"""Generators must be deterministic and produce what their names promise."""

from owlgo.problems.generators import GENERATORS, PRINTABLE_ASCII, generate


def test_same_args_give_same_value():
    args = {"start": 0, "stop": 1000, "seed": 7}
    assert generate("shuffled_range", args) == generate("shuffled_range", args)


def test_different_seeds_give_different_orders():
    a = generate("shuffled_range", {"start": 0, "stop": 1000, "seed": 1})
    b = generate("shuffled_range", {"start": 0, "stop": 1000, "seed": 2})
    assert a != b and sorted(a) == sorted(b) == list(range(1000))


def test_cycle_printable_ascii_uses_all_95_characters():
    text = generate("cycle_printable_ascii", {"n": 200})
    assert len(PRINTABLE_ASCII) == 95
    assert len(text) == 200 and set(text) == set(PRINTABLE_ASCII)


def test_simple_generators():
    assert generate("arange", {"start": 0, "stop": 3}) == [0, 1, 2]
    assert generate("repeat", {"value": 5, "n": 3}) == [5, 5, 5]
    assert generate("repeat_string", {"text": "ab", "n": 2}) == "abab"
    ints = generate("random_ints", {"n": 50, "low": -3, "high": 3, "seed": 0})
    assert len(ints) == 50 and all(-3 <= x <= 3 for x in ints)


def test_registry_lists_every_generator():
    assert set(GENERATORS) == {
        "arange",
        "repeat",
        "repeat_string",
        "cycle_printable_ascii",
        "shuffled_range",
        "random_ints",
    }
