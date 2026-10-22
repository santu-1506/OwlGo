"""Tagged JSON encoding for Python values used in tests.

JSON only has lists, objects, strings, numbers, booleans and null. Tests from
datasets like MBPP+ use tuples, sets, dicts with int keys, inf and complex
numbers, and the difference matters: (1, 2) != [1, 2] in Python.

So values that JSON can't hold are stored with a one-key tag, for example:
    (1, 2)        -> {"$tuple": [1, 2]}
    {3, 1}        -> {"$set": [1, 3]}
    float("inf")  -> {"$float": "inf"}

This file is copied into the sandbox next to the harness, so it must only use
the standard library and must not import anything from the owlgo package.
"""

import json
import math

# Every tag this codec knows. A JSON object with exactly one of these keys is a tagged value.
TAGS = {"$tuple", "$set", "$frozenset", "$dict", "$float", "$complex", "$repr"}


class UnsupportedValue(TypeError):
    """Raised for values with no faithful JSON encoding (bytes, numpy arrays, custom objects)."""


def encode(value):
    """Turn a Python value into something json.dumps can write, without losing its type."""
    # None, bool and str are already valid JSON. (bool is checked before int below,
    # because bool is a subclass of int.)
    if value is None or isinstance(value, (bool, str)):
        return value
    # Python ints of any size are valid JSON numbers.
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        # Normal floats stay as they are; JSON has no inf or nan, so those get a tag.
        if math.isfinite(value):
            return value
        return {"$float": repr(value)}  # "inf", "-inf" or "nan"
    if isinstance(value, complex):
        return {"$complex": [encode(value.real), encode(value.imag)]}
    if isinstance(value, list):
        return [encode(item) for item in value]
    if isinstance(value, tuple):
        return {"$tuple": [encode(item) for item in value]}
    if isinstance(value, (set, frozenset)):
        # Sets have no order. Sort the encoded items so the same set always gives the same JSON.
        items = sorted((encode(item) for item in value), key=_sort_key)
        return {"$frozenset" if isinstance(value, frozenset) else "$set": items}
    if isinstance(value, dict):
        # A plain JSON object works only if every key is a string that can't be mistaken for a tag.
        if all(isinstance(key, str) and not key.startswith("$") for key in value):
            return {key: encode(item) for key, item in value.items()}
        # Otherwise store [key, value] pairs, which keeps int keys, tuple keys and so on.
        return {"$dict": [[encode(key), encode(item)] for key, item in value.items()]}
    raise UnsupportedValue(f"cannot encode a value of type {type(value).__name__}")


def decode(data):
    """Turn encoded JSON data back into the original Python value."""
    if isinstance(data, list):
        return [decode(item) for item in data]
    if isinstance(data, dict):
        # A one-key object whose key is a known tag is a tagged value.
        if len(data) == 1:
            ((tag, payload),) = data.items()
            if tag in TAGS:
                return _decode_tag(tag, payload)
        # Anything else is a plain dict with string keys.
        return {key: decode(item) for key, item in data.items()}
    # Strings, numbers, booleans and None need no conversion.
    return data


def encode_or_repr(value, max_chars=2000):
    """Encode a value for showing in results, falling back to a short repr.

    Used for outputs produced by user code, which can be huge or of a type the
    codec doesn't support. A {"$repr": ...} value is for display only.
    """
    try:
        encoded = encode(value)
        # Keep the real value only if it is small enough to show.
        if len(json.dumps(encoded)) <= max_chars:
            return encoded
    except UnsupportedValue:
        pass
    # Too big or unsupported: keep a truncated repr so a human can still see it.
    text = repr(value)
    return {"$repr": text if len(text) <= 500 else text[:500] + "..."}


def _decode_tag(tag, payload):
    """Decode one tagged value. Called only by decode()."""
    if tag == "$tuple":
        return tuple(decode(item) for item in payload)
    if tag == "$set":
        return {decode(item) for item in payload}
    if tag == "$frozenset":
        return frozenset(decode(item) for item in payload)
    if tag == "$dict":
        return {decode(key): decode(item) for key, item in payload}
    if tag == "$float":
        return float(payload)
    if tag == "$complex":
        return complex(decode(payload[0]), decode(payload[1]))
    # "$repr" only describes a value for humans; the original can't be rebuilt from it.
    raise UnsupportedValue("a $repr value is for display only and cannot be decoded")


def _sort_key(encoded_item):
    """Stable sort key for encoded set items of any type."""
    return json.dumps(encoded_item, sort_keys=True)
