#!/usr/bin/env python
"""Unit tests for Phase B1-B2 material types and theoretical length in src/core.py.

Tests the MATERIAL_DENSITY / MATERIAL_TYPES / THICKNESS bounds constants and the
theoretical_length() and validate_coil_weights() functions added to core.py.
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import (  # noqa: E402
    MATERIAL_DENSITY,
    MATERIAL_TYPES,
    THICKNESS_MIN,
    THICKNESS_MAX,
    theoretical_length,
    validate_coil_weights,
)


def test_material_types_and_densities():
    """All six steel types exist, all with density 7.85 g/cm³."""
    assert MATERIAL_TYPES == ["HR", "CR", "GI", "GL", "PPCR", "CRBA"]
    for m in MATERIAL_TYPES:
        assert MATERIAL_DENSITY[m] == 7.85


def test_thickness_bounds():
    assert THICKNESS_MIN == 0.10
    assert THICKNESS_MAX == 12.00


def test_theoretical_length_basic():
    # weight=7850 kg, width=1000 mm, thickness=10 mm, density=7.85
    # length = 7850*1000 / (1000 * 10 * 7.85) = 100.0 m
    assert theoretical_length(7850.0, 1000.0, 10.0, "HR") == 100.0

    # length = 1000*1000 / (1250 * 2.0 * 7.85) = 1000000 / 19625 ≈ 50.955...
    length = theoretical_length(1000.0, 1250.0, 2.0, "CR")
    assert abs(length - 50.95541401273987) < 1e-9


def test_theoretical_length_all_materials():
    result = theoretical_length(785.0, 1000.0, 10.0, "HR")
    for m in MATERIAL_TYPES:
        assert abs(theoretical_length(785.0, 1000.0, 10.0, m) - result) < 1e-12


def test_theoretical_length_unknown_material_raises():
    for bad in ("XX", "hr", "CRBA ", "", None):
        try:
            theoretical_length(1000.0, 1000.0, 10.0, bad)
        except ValueError:
            continue
        else:
            raise AssertionError("expected ValueError for material %r" % (bad,))


def test_theoretical_length_nonfinite_or_nonpositive():
    # weight <= 0
    try:
        theoretical_length(0.0, 1000.0, 10.0, "HR")
        raise AssertionError("expected ValueError for weight=0")
    except ValueError:
        pass

    try:
        theoretical_length(-5.0, 1000.0, 10.0, "HR")
        raise AssertionError("expected ValueError for weight<0")
    except ValueError:
        pass

    # width <= 0
    try:
        theoretical_length(1000.0, 0.0, 10.0, "HR")
        raise AssertionError("expected ValueError for width=0")
    except ValueError:
        pass

    # thickness <= 0
    try:
        theoretical_length(1000.0, 1000.0, 0.0, "HR")
        raise AssertionError("expected ValueError for thickness=0")
    except ValueError:
        pass

    # non-finite
    try:
        theoretical_length(math.nan, 1000.0, 10.0, "HR")
        raise AssertionError("expected ValueError for weight=nan")
    except ValueError:
        pass

    try:
        theoretical_length(1000.0, math.inf, 10.0, "HR")
        raise AssertionError("expected ValueError for width=inf")
    except ValueError:
        pass

    try:
        theoretical_length(1000.0, 1000.0, -math.inf, "HR")
        raise AssertionError("expected ValueError for thickness=-inf")
    except ValueError:
        pass


def test_theoretical_length_thickness_out_of_range():
    try:
        theoretical_length(1000.0, 1000.0, 0.09, "HR")  # below 0.10
        raise AssertionError("expected ValueError for thickness<0.10")
    except ValueError:
        pass

    try:
        theoretical_length(1000.0, 1000.0, 12.01, "HR")  # above 12.00
        raise AssertionError("expected ValueError for thickness>12.00")
    except ValueError:
        pass

    # boundary values are OK
    assert theoretical_length(1000.0, 1000.0, 0.10, "HR") > 0
    assert theoretical_length(1000.0, 1000.0, 12.00, "HR") > 0


def test_validate_coil_weights_valid():
    ok, msg = validate_coil_weights([100.0, 250.5, 50.0])
    assert ok is True
    assert msg == ""

    ok, msg = validate_coil_weights([0.01])
    assert ok is True


def test_validate_coil_weights_empty():
    ok, msg = validate_coil_weights([])
    assert ok is False
    assert "coil weights" in msg.lower()


def test_validate_coil_weights_none_or_zero_or_negative():
    for bad in ([None], [0.0], [-5.0], [10.0, None], [10.0, float("nan")], [10.0, float("inf")]):
        ok, msg = validate_coil_weights(bad)
        assert ok is False, "expected invalid for %r" % (bad,)
        assert "Coil" in msg


if __name__ == "__main__":
    tests = [
        test_material_types_and_densities,
        test_thickness_bounds,
        test_theoretical_length_basic,
        test_theoretical_length_all_materials,
        test_theoretical_length_unknown_material_raises,
        test_theoretical_length_nonfinite_or_nonpositive,
        test_theoretical_length_thickness_out_of_range,
        test_validate_coil_weights_valid,
        test_validate_coil_weights_empty,
        test_validate_coil_weights_none_or_zero_or_negative,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print("[PASS] %s" % t.__name__)
        except Exception as e:
            failed += 1
            print("[FAIL] %s: %s" % (t.__name__, e))
    print("\n%d/%d tests passed" % (len(tests) - failed, len(tests)))
    sys.exit(1 if failed else 0)
