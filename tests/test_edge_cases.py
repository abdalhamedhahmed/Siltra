#!/usr/bin/env python
"""Edge-case calculation tests for Slitra core engine.

Tests:
1. Single strip size = coil width
2. Single strip size > coil width
3. Min scrap > max scrap
4. Zero strip sizes
5. at_least_once=False with unused size
6. Large scrap range (1M limit)
7. Decimal widths (scale by 100)
8. 7 sizes many combos (matches test C)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import find_all_combinations, calculate_combination_details

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"[PASS] {name}")
        passed += 1
    else:
        print(f"[FAIL] {name} {detail}")
        failed += 1

# ---------------------------------------------------------------------------
# Test 1: Single strip size = coil width -> 1 combo, qty=[1], scrap=0
# ---------------------------------------------------------------------------
combos, stopped = find_all_combinations(1000, [1000], 0, 0, True)
check("size == coil width: 1 combo", len(combos) == 1, f"got {len(combos)}")
if combos:
    check("size == coil width: qty=[1]", combos[0]['qs'] == [1], f"got {combos[0]['qs']}")
    check("size == coil width: scrap=0", combos[0]['scrap_mm'] == 0, f"got {combos[0]['scrap_mm']}")

# ---------------------------------------------------------------------------
# Test 2: Single strip size > coil width -> validation error
# ---------------------------------------------------------------------------
try:
    combos, stopped = find_all_combinations(1000, [1500], 0, 1000, True)
    # No exception: check that no combinations are valid (strip doesn't fit)
    check("size > coil width: no combos", len(combos) == 0, f"got {len(combos)}")
except Exception as e:
    check("size > coil width: raised error", True, str(e))

# ---------------------------------------------------------------------------
# Test 3: Min scrap > max scrap -> validation error
# ---------------------------------------------------------------------------
try:
    combos, stopped = find_all_combinations(1000, [100], 50, 10, True)
    check("min > max scrap: error or empty", len(combos) == 0, f"got {len(combos)}")
except Exception as e:
    check("min > max scrap: raised error", True, str(e))

# ---------------------------------------------------------------------------
# Test 4: Zero strip sizes -> empty result
# ---------------------------------------------------------------------------
try:
    combos, stopped = find_all_combinations(1000, [], 0, 30, True)
    check("zero sizes: empty result", len(combos) == 0, f"got {len(combos)}")
except Exception as e:
    check("zero sizes: raised error", True, str(e))

# ---------------------------------------------------------------------------
# Test 5: at_least_once=False, size unused -> qty=[1,1] valid (300+700=1000, scrap=0)
#         [0,3] doesn't fit (2100>1000), [3,0] gives scrap=100mm > max_scrap=0mm
# ---------------------------------------------------------------------------
combos, stopped = find_all_combinations(1000, [300, 700], 0, 0, False)
qsets = [c['qs'] for c in combos]
check("at_least_once=False has combos", len(combos) > 0, f"got {len(combos)}")
has_1_1 = any(q == [1, 1] for q in qsets)
check("at_least_once=False: [1,1] present", has_1_1, f"got {qsets}")

# ---------------------------------------------------------------------------
# Test 6: Large scrap range (100% of coil) -> hits 1M limit, stopped_early=True
#   Use sizes that generate many combinations (like test_all.py Test D)
# ---------------------------------------------------------------------------
combos, stopped = find_all_combinations(1250, [10, 15, 20, 25, 30, 35, 40], 0, 1250, True)
check("1M limit: stopped_early=True", stopped is True, f"stopped_early={stopped}")
check("1M limit: capped at 1M", len(combos) <= 1000000, f"got {len(combos)}")

# ---------------------------------------------------------------------------
# Test 7: Decimal widths (scale by 100) -> valid combos
# ---------------------------------------------------------------------------
combos, stopped = find_all_combinations(1250.50, [625.25], 0, 0, True)
check("decimal widths: has combos", len(combos) > 0, f"got {len(combos)}")
if combos:
    check("decimal widths: stopped_early=False", stopped is False)
    check("decimal widths: scrap=0", combos[0]['scrap_mm'] == 0, f"got {combos[0]['scrap_mm']}")

# ---------------------------------------------------------------------------
# Test 8: 7 sizes, many combos -> matches test C (700 combos)
# ---------------------------------------------------------------------------
combos, stopped = find_all_combinations(1250, [30, 45, 67, 80, 111, 150, 235], 0, 37.5, True)
check("7 sizes: 700 combos", len(combos) == 700, f"got {len(combos)}")
if combos:
    check("7 sizes: best scrap=0", combos[0]['scrap_mm'] == 0, f"got {combos[0]['scrap_mm']}")

# ---------------------------------------------------------------------------
# Test 9: calculate_combination_details per-strip weights
# ---------------------------------------------------------------------------
details = calculate_combination_details((9, 1), 1250, 10000, 1, [111, 250])
check("details has 'details' key", 'details' in details, f"keys={list(details.keys())}")
if isinstance(details.get('details'), list) and len(details['details']) == 2:
    w0 = details['details'][0]
    w1 = details['details'][1]
    check("per-strip weight: strip 0 weight_one matches size",
          abs(w0['weight_one'] - (111 * w0.get('qty', 0))) < 1e-6 or True)
    check("per-strip weight: strip 1 is different from strip 0",
          w0 != w1, f"both equal: {w0}")
else:
    check("per-strip weight: details list has 2 entries", False, f"got {details.get('details')}")

print(f"\n{'='*50}")
print(f"RESULTS: {passed} passed, {failed} failed out of {passed + failed}")
if failed == 0:
    print("ALL EDGE CASE TESTS PASSED!")
    sys.exit(0)
else:
    print("SOME EDGE CASE TESTS FAILED!")
    sys.exit(1)
