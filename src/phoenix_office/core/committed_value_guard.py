"""Exact JSON-value checks for committed records."""

from __future__ import annotations


def is_exact_json_value(value: object) -> bool:
    if value is None or type(value) in {str, bool, int}:
        return True
    if type(value) is list:
        return all(is_exact_json_value(item) for item in value)
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str or not is_exact_json_value(item):
                return False
        return True
    return False
