"""Seeded generators for large test inputs and outputs.

Stress tests need big inputs (a 50,000-character string, 100,000 numbers).
Storing those in the problem files would bloat them, so a test names a
generator instead:

    "generated_inputs": {
        "nums": {"fn": "shuffled_range", "args": {"start": 0, "stop": 100000, "seed": 7}}
    }

Every generator is deterministic: the same args always give the same value.
This file is copied into the sandbox next to the harness, so it must only use
the standard library.
"""

import random
import string

# The 95 printable ASCII characters: digits, letters, punctuation and the space.
PRINTABLE_ASCII = string.digits + string.ascii_letters + string.punctuation + " "


def arange(start, stop, step=1):
    """List of ints like range(): arange(0, 5) -> [0, 1, 2, 3, 4]."""
    return list(range(start, stop, step))


def repeat(value, n):
    """List with the same value n times. Use it with immutable values (ints, strings)."""
    return [value] * n


def repeat_string(text, n):
    """One string made of text repeated n times: repeat_string("ab", 3) -> "ababab"."""
    return text * n


def cycle_printable_ascii(n):
    """String of length n that cycles through all 95 printable ASCII characters."""
    full_cycles, remainder = divmod(n, len(PRINTABLE_ASCII))
    return PRINTABLE_ASCII * full_cycles + PRINTABLE_ASCII[:remainder]


def shuffled_range(start, stop, seed):
    """The ints start..stop-1 in a shuffled order that depends only on seed."""
    values = list(range(start, stop))
    # A private Random instance, so the global random state never affects the result.
    random.Random(seed).shuffle(values)
    return values


def random_ints(n, low, high, seed):
    """n ints drawn uniformly from low..high (inclusive), reproducible from seed."""
    rng = random.Random(seed)
    return [rng.randint(low, high) for _ in range(n)]


# Name -> function. Problem files may only use names listed here.
GENERATORS = {
    fn.__name__: fn
    for fn in (arange, repeat, repeat_string, cycle_printable_ascii, shuffled_range, random_ints)
}


def generate(fn, args):
    """Run the generator called fn with keyword args. Raises KeyError for unknown names."""
    return GENERATORS[fn](**args)
