"""
Coil Slitting Calculation Engine - Core Logic
Extracted from coil_slitting_app.py and coil_slitting_calc.py
Contains all non-UI business logic: calculations, search, export, presets, logs, settings
"""

from decimal import Decimal, ROUND_HALF_UP
import math
from typing import List, Dict, Any, Optional, Tuple, Callable
import threading
import time
import json
import os
import csv
from datetime import datetime


# ============================================================
# CONSTANTS
# ============================================================
MAX_COMBINATIONS_LIMIT = 1_000_000
DEFAULT_PAGE_SIZE = 500

# ============================================================
# CALCULATION FUNCTIONS (from coil_slitting_calc.py)
# ============================================================

def find_all_combinations(
    coil_width: float,
    strip_sizes: List[float],
    min_scrap_mm: float = 0.0,
    max_scrap_mm: float = 10.0,
    at_least_once: bool = True,
    progress_callback: Optional[Callable] = None,
    cancel_flag: Optional[threading.Event] = None,
    count_only: bool = False
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Find all valid combinations of strip quantities that fit within the coil width
    and meet the scrap range requirement (min to max scrap in mm).

    Uses iterative search with pruning, sizes sorted largest-to-smallest internally,
    integer math for speed, and direct computation of the last size's valid range.

    Args:
        coil_width: Width of the coil in mm
        strip_sizes: List of strip widths in mm (1 to 7 sizes)
        min_scrap_mm: Minimum allowed scrap in mm (default 0.0)
        max_scrap_mm: Maximum allowed scrap in mm (default 10.0)
        at_least_once: If True, each size must appear at least once
        progress_callback: Optional callback(combinations_found) for progress updates
        cancel_flag: Optional threading.Event to cancel the search
        count_only: If True, only count combinations without storing them (for large result sets)

    Returns:
        Tuple of (list of combination dicts, stopped_early_flag)
        Each dict has: qs (original order), total_width, scrap_mm, scrap_pct, total_strips, rank, is_best
        If count_only=True, returns (empty_list, stopped_early_flag) and progress_callback gets count
    """
    n = len(strip_sizes)
    if n == 0:
        return [], False

    # Convert to integer mm for exact arithmetic (scale by 100 to preserve 0.01mm precision)
    SCALE = 100
    cw_int = int(round(coil_width * SCALE))
    sizes_int = [int(round(s * SCALE)) for s in strip_sizes]

    max_scrap_int = int(round(max_scrap_mm * SCALE))
    min_scrap_int = int(round(min_scrap_mm * SCALE))
    min_width_used_int = cw_int - max_scrap_int
    max_width_used_int = cw_int - min_scrap_int
    min_q = 1 if at_least_once else 0

    # Sort sizes largest-to-smallest for earlier pruning, keep original index mapping
    indexed = list(enumerate(sizes_int))
    indexed.sort(key=lambda x: x[1], reverse=True)
    sorted_indices = [idx for idx, _ in indexed]
    sorted_sizes = [sz for _, sz in indexed]
    # Map sorted position -> original position
    orig_pos_of_sorted = [0] * n
    for sorted_pos, orig_idx in enumerate(sorted_indices):
        orig_pos_of_sorted[sorted_pos] = orig_idx

    results = []  # list of tuples: (qs_original_order, total_width_int, scrap_mm_int, total_strips)
    stopped_early = False
    combo_count = 0
    last_progress_update = 0

    def search():
        nonlocal stopped_early, combo_count, last_progress_update
        # Stack frames: (i, current_width_int, qs_sorted_list)
        stack = [(0, 0, [])]

        while stack:
            if cancel_flag and cancel_flag.is_set():
                stopped_early = True
                return
            if combo_count >= MAX_COMBINATIONS_LIMIT:
                stopped_early = True
                return

            i, cur_w, cur_qs = stack.pop()

            if i == n - 1:
                # Last size: compute valid range directly
                w = sorted_sizes[i]
                w_remain = cw_int - cur_w
                # Need: min_width_used_int <= cur_w + q*w <= max_width_used_int
                # So: ceil((min_width_used_int - cur_w)/w) <= q <= floor((max_width_used_int - cur_w)/w)
                min_needed = max(0, min_width_used_int - cur_w)
                max_allowed = max_width_used_int - cur_w

                hi_q = max_allowed // w if w > 0 else 0
                lo_q = (min_needed + w - 1) // w if w > 0 else min_q
                lo_q = max(lo_q, min_q)

                if hi_q >= lo_q:
                    for q in range(lo_q, hi_q + 1):
                        full_qs_sorted = cur_qs + [q]
                        # Map back to original order
                        qs_orig = [0] * n
                        for sp, q_val in enumerate(full_qs_sorted):
                            qs_orig[orig_pos_of_sorted[sp]] = q_val

                        total_w = sum(sz * q for sz, q in zip(sizes_int, qs_orig))
                        scrap_mm_int = cw_int - total_w
                        total_strips = sum(qs_orig)

                        combo_count += 1

                        if not count_only:
                            results.append((list(qs_orig), total_w, scrap_mm_int, total_strips))

                        # Batch progress updates (every 5000 combinations)
                        if progress_callback and combo_count - last_progress_update >= 5000:
                            progress_callback(combo_count)
                            last_progress_update = combo_count

                        if combo_count >= MAX_COMBINATIONS_LIMIT:
                            stopped_early = True
                            return
                continue

            # Not the last size: iterate quantities with pruning
            w = sorted_sizes[i]
            # Minimum width needed for remaining sizes
            rest_min = sum(sorted_sizes[j] for j in range(i + 1, n)) * min_q

            q = min_q
            while cur_w + q * w + rest_min <= cw_int:
                # Also check if even max possible remaining can reach min_width_used
                # Max possible from this point: cur_w + q*w + sum(remaining * max_q)
                # But we don't know max_q for remaining, so we just check lower bound
                # The upper bound is handled by the while condition (can't exceed coil_width)
                stack.append((i + 1, cur_w + q * w, cur_qs + [q]))
                q += 1

    search()

    # If count_only, return empty list with the count in progress_callback
    if count_only:
        return [], stopped_early

    # Enrich results with calculated fields
    enriched = []
    for qs, total_w_int, scrap_mm_int, total_strips in results:
        total_w = total_w_int / SCALE
        scrap_mm = scrap_mm_int / SCALE
        scrap_pct = (scrap_mm / coil_width) * 100 if coil_width > 0 else 0
        enriched.append({
            'qs': qs,
            'total_width': total_w,
            'scrap_mm': scrap_mm,
            'scrap_pct': scrap_pct,
            'total_strips': total_strips
        })

    # Sort by least scrap first, then fewer total strips
    enriched.sort(key=lambda x: (x['scrap_mm'], x['total_strips']))

    # Add rank and is_best flag
    for i, item in enumerate(enriched):
        item['rank'] = i + 1
        item['is_best'] = (i == 0)

    return enriched, stopped_early


def get_lowest_possible_scrap(
    coil_width: float,
    strip_sizes: List[float],
    at_least_once: bool = True
) -> Optional[float]:
    """
    Find the lowest possible scrap percentage achievable with the given sizes.
    Uses bitset DP (Python int as bitset) for O(N * W/word_size) speed.
    """
    n = len(strip_sizes)
    if n == 0:
        return None

    min_q = 1 if at_least_once else 0
    base_width = sum(s * min_q for s in strip_sizes)
    if base_width > coil_width:
        return None

    # Scale to integer mm with precision (100 = 0.01mm)
    SCALE = 100
    cw_int = int(round(coil_width * SCALE))
    base_int = int(round(base_width * SCALE))

    # Use Python int as bitset: bit i = width i*SCALE is reachable
    # Start with base_width
    reachable = 1 << base_int

    # Mask to coil_width limit (keeps int bounded during fixpoint iteration)
    mask = (1 << (cw_int + 1)) - 1

    for w in strip_sizes:
        int_w = int(round(w * SCALE))
        if int_w == 0:
            continue
        # Shift and OR to fixpoint: reachable |= reachable << int_w
        # Iterate until no new widths appear, so each size can be used
        # unlimited times (unbounded knapsack). Mask each step to keep the
        # int bounded at coil_width bits.
        prev = 0
        while reachable != prev:
            prev = reachable
            reachable |= reachable << int_w
            reachable &= mask

    # Find highest set bit <= cw_int
    # reachable.bit_length() - 1 gives highest set bit
    best = reachable.bit_length() - 1
    if best < 0:
        return None

    scrap_mm = (cw_int - best) / SCALE
    return (scrap_mm / coil_width) * 100.0


def calculate_combination_details(
    qs: tuple,
    coil_width: float,
    total_coil_weight: float,
    num_coils: int,
    strip_sizes: List[float]
) -> Dict[str, Any]:
    """
    Calculate detailed weight information for a specific combination.
    Uses Decimal for precision to avoid floating-point errors.
    """
    try:
        tw = Decimal(str(total_coil_weight))
    except (ValueError, TypeError):
        tw = Decimal('0.0')

    try:
        cw_dec = Decimal(str(coil_width))
    except (ValueError, TypeError):
        cw_dec = Decimal('1.0')

    weight_per_coil = tw / Decimal(str(num_coils)) if num_coils > 0 else Decimal('0.0')

    details = []
    total_w_used = 0
    for w, q in zip(strip_sizes, qs):
        w_dec = Decimal(str(w))
        weight_one_strip = weight_per_coil * (w_dec / cw_dec)
        total_weight_all_coils = weight_one_strip * Decimal(str(q)) * Decimal(str(num_coils))

        details.append({
            'size': w,
            'q_per_coil': q,
            'q_total': q * num_coils,
            'weight_one': float(weight_one_strip.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            'weight_total': float(total_weight_all_coils.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        })
        total_w_used += w * q

    scrap_width = coil_width - total_w_used
    scrap_width_dec = Decimal(str(scrap_width))
    scrap_weight_per_coil = weight_per_coil * (scrap_width_dec / cw_dec)
    scrap_weight_total = scrap_weight_per_coil * Decimal(str(num_coils))

    return {
        'details': details,
        'scrap_width': scrap_width,
        'scrap_weight_per_coil': float(scrap_weight_per_coil.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
        'scrap_weight_total': float(scrap_weight_total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
        'total_w_used': total_w_used,
        'scrap_pct': (scrap_width / coil_width) * 100 if coil_width > 0 else 0
    }


def verify_weight_balance(
    total_coil_weight: float,
    num_coils: int,
    details_res: Dict[str, Any],
    coil_width: float
) -> Decimal:
    """
    Verify that total weight = strips weight + scrap weight.
    Returns the difference (should be ~0).
    """
    try:
        cw_dec = Decimal(str(coil_width))
        tot_weight_dec = Decimal(str(total_coil_weight))
    except (ValueError, TypeError):
        return Decimal('0.0')

    if cw_dec == 0:
        return tot_weight_dec

    strips_total_w = sum(Decimal(str(d['weight_total'])) for d in details_res['details'])
    used_weight = strips_total_w + Decimal(str(details_res['scrap_weight_total']))

    return tot_weight_dec - used_weight


# ============================================================
# PRESET MANAGEMENT
# ============================================================

PRESETS_FILE = "presets.json"

def load_presets() -> Dict[str, Any]:
    """Load presets from JSON file."""
    if os.path.exists(PRESETS_FILE):
        try:
            with open(PRESETS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_presets(presets: Dict[str, Any]) -> None:
    """Save presets to JSON file."""
    with open(PRESETS_FILE, 'w') as f:
        json.dump(presets, f, indent=2)

def add_preset(name: str, settings: Dict[str, Any]) -> None:
    """Add or update a preset."""
    presets = load_presets()
    presets[name] = settings
    save_presets(presets)

def get_preset(name: str) -> Optional[Dict[str, Any]]:
    """Get a preset by name."""
    presets = load_presets()
    return presets.get(name)

def delete_preset(name: str) -> bool:
    """Delete a preset by name."""
    presets = load_presets()
    if name in presets:
        del presets[name]
        save_presets(presets)
        return True
    return False


# ============================================================
# EXPORT FUNCTIONS (PDF and Excel)
# ============================================================

def export_to_csv(filepath: str, combinations: List[Dict[str, Any]],
                  coil_width: float, strip_sizes: List[float],
                  total_coil_weight: float, num_coils: int) -> bool:
    """
    Export combinations to CSV file.
    Returns True if successful, False otherwise.
    Optimized: batch calculate all weight details first.
    """
    try:
        # Pre-calculate weight details for ALL combinations in one pass
        details_list = []
        for combo in combinations:
            details = calculate_combination_details(
                tuple(combo['qs']), coil_width, total_coil_weight, num_coils, strip_sizes
            )
            details_list.append(details)

        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)

            # Header
            header = ['Formula', 'Total Width (mm)', 'Scrap (mm)', 'Scrap (%)', 'Total Strips']
            for i, size in enumerate(strip_sizes):
                header.append(f'Qty {size}mm')
            header.extend(['Weight per Coil (kg)', 'Total Weight (kg)', 'Scrap Weight per Coil (kg)', 'Scrap Weight Total (kg)'])
            writer.writerow(header)

            # Data rows
            for combo, details in zip(combinations, details_list):
                row = [
                    f"F{combo['rank']}",
                    f"{combo['total_width']:.2f}",
                    f"{combo['scrap_mm']:.2f}",
                    f"{combo['scrap_pct']:.2f}",
                    combo['total_strips']
                ]

                # Quantities
                for q in combo['qs']:
                    row.append(str(q))

                # Add weight information
                if details['details']:
                    first_detail = details['details'][0]
                    row.extend([
                        f"{first_detail['weight_one']:.2f}",
                        f"{first_detail['weight_total']:.2f}",
                        f"{details['scrap_weight_per_coil']:.2f}",
                        f"{details['scrap_weight_total']:.2f}"
                    ])
                else:
                    row.extend(['0.00', '0.00', '0.00', '0.00'])

                writer.writerow(row)

        return True
    except Exception as e:
        print(f"Error exporting to CSV: {e}")
        return False


def export_combinations_to_csv(filepath: str, combinations: List[Dict[str, Any]],
                              coil_width: float, strip_sizes: List[float],
                              total_coil_weight: float, num_coils: int) -> bool:
    """Alias for export_to_csv for compatibility."""
    return export_to_csv(filepath, combinations, coil_width, strip_sizes, total_coil_weight, num_coils)


# ============================================================
# LOGGING FUNCTIONALITY
# ============================================================

LOG_FILE = "coil_slitting_log.txt"

def log_message(message: str) -> None:
    """Log a message with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"

    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception:
        pass  # Fail silently for logging


def clear_log() -> None:
    """Clear the log file."""
    try:
        open(LOG_FILE, 'w').close()
    except Exception:
        pass


# ============================================================
# SETTINGS MANAGEMENT
# ============================================================

SETTINGS_FILE = "settings.json"

def load_settings() -> Dict[str, Any]:
    """Load settings from JSON file."""
    default_settings = {
        "geometry": "1200x800+100+100",
        "theme": "light",
        "last_coil_width": 1250.0,
        "last_strip_sizes": [111, 250],
        "last_min_scrap": 0.0,
        "last_max_scrap": 30.0,
        "last_at_least_once": True,
        "auto_calculate": True,
        "show_warnings": True,
        "decimal_places": 2
    }

    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                # Merge with defaults to ensure all keys exist
                for key, value in default_settings.items():
                    if key not in settings:
                        settings[key] = value
                return settings
        except Exception:
            return default_settings
    return default_settings

def save_settings(settings: Dict[str, Any]) -> None:
    """Save settings to JSON file."""
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

def update_setting(key: str, value: Any) -> None:
    """Update a single setting."""
    settings = load_settings()
    settings[key] = value
    save_settings(settings)

def get_setting(key: str, default: Any = None) -> Any:
    """Get a setting value."""
    settings = load_settings()
    return settings.get(key, default)


# ============================================================
# VALIDATION FUNCTIONS
# ============================================================

def validate_inputs(coil_width: float, strip_sizes: List[float],
                   min_scrap_mm: float, max_scrap_mm: float,
                   at_least_once: bool) -> Tuple[bool, str]:
    """
    Validate input parameters.
    Returns (is_valid, error_message).
    """
    if coil_width <= 0:
        return False, "Coil width must be greater than 0"

    if not strip_sizes or len(strip_sizes) == 0:
        return False, "At least one strip size must be specified"

    if len(strip_sizes) > 7:
        return False, "Maximum 7 strip sizes allowed"

    for size in strip_sizes:
        if size <= 0:
            return False, f"Strip size {size} must be greater than 0"
        if size > coil_width:
            return False, f"Strip size {size} must be less than coil width {coil_width}"

    if min_scrap_mm < 0:
        return False, "Minimum scrap cannot be negative"

    if max_scrap_mm < min_scrap_mm:
        return False, "Maximum scrap must be greater than or equal to minimum scrap"

    if max_scrap_mm >= coil_width:
        return False, "Maximum scrap must be less than coil width"

    return True, ""


# ============================================================
# STEP 2B OVER-LIMIT BEHAVIOR (Bounded Heap Algorithm)
# ============================================================

import heapq

def find_all_combinations_bounded(
    coil_width: float,
    strip_sizes: List[float],
    min_scrap_mm: float = 0.0,
    max_scrap_mm: float = 10.0,
    at_least_once: bool = True,
    progress_callback: Optional[Callable] = None,
    cancel_flag: Optional[threading.Event] = None,
    count_only: bool = False,
    max_rows: int = 10000
) -> Tuple[List[Dict[str, Any]], bool, int]:
    """
    Find combinations with bounded heap algorithm (STEP 2B).
    Keeps best MAX_ROWS rows and shows true total N.

    Returns:
        Tuple of (list of combination dicts, stopped_early_flag, total_combinations_found)
    """
    n = len(strip_sizes)
    if n == 0:
        return [], False, 0

    # Convert to integer mm for exact arithmetic (scale by 100 to preserve 0.01mm precision)
    SCALE = 100
    cw_int = int(round(coil_width * SCALE))
    sizes_int = [int(round(s * SCALE)) for s in strip_sizes]

    max_scrap_int = int(round(max_scrap_mm * SCALE))
    min_scrap_int = int(round(min_scrap_mm * SCALE))
    min_width_used_int = cw_int - max_scrap_int
    max_width_used_int = cw_int - min_scrap_int
    min_q = 1 if at_least_once else 0

    # Sort sizes largest-to-smallest for earlier pruning, keep original index mapping
    indexed = list(enumerate(sizes_int))
    indexed.sort(key=lambda x: x[1], reverse=True)
    sorted_indices = [idx for idx, _ in indexed]
    sorted_sizes = [sz for _, sz in indexed]
    # Map sorted position -> original position
    orig_pos_of_sorted = [0] * n
    for sorted_pos, orig_idx in enumerate(sorted_indices):
        orig_pos_of_sorted[sorted_pos] = orig_idx

    # Bounded heap: keep worst (highest scrap, then highest strips) at top
    # We store negative values because heapq is min-heap, but we want max-heap behavior
    # Use a counter to break ties when the first two elements are equal (Python 3.x compatible)
    heap = []  # Will store (-scrap_mm, -total_strips, counter, combination_data)
    stopped_early = False
    combo_count = 0
    total_combinations = 0
    counter = 0

    def search():
        nonlocal stopped_early, combo_count, total_combinations, counter
        # Stack frames: (i, current_width_int, qs_sorted_list)
        stack = [(0, 0, [])]

        while stack:
            if cancel_flag and cancel_flag.is_set():
                stopped_early = True
                return
            if combo_count >= MAX_COMBINATIONS_LIMIT:
                stopped_early = True
                return

            i, cur_w, cur_qs = stack.pop()

            if i == n - 1:
                # Last size: compute valid range directly
                w = sorted_sizes[i]
                w_remain = cw_int - cur_w
                # Need: min_width_used_int <= cur_w + q*w <= max_width_used_int
                # So: ceil((min_width_used_int - cur_w)/w) <= q <= floor((max_width_used_int - cur_w)/w)
                min_needed = max(0, min_width_used_int - cur_w)
                max_allowed = max_width_used_int - cur_w

                hi_q = max_allowed // w if w > 0 else 0
                lo_q = (min_needed + w - 1) // w if w > 0 else min_q
                lo_q = max(lo_q, min_q)

                if hi_q >= lo_q:
                    for q in range(lo_q, hi_q + 1):
                        full_qs_sorted = cur_qs + [q]
                        # Map back to original order
                        qs_orig = [0] * n
                        for sp, q_val in enumerate(full_qs_sorted):
                            qs_orig[orig_pos_of_sorted[sp]] = q_val

                        total_w = sum(sz * q for sz, q in zip(sizes_int, qs_orig))
                        scrap_mm_int = cw_int - total_w
                        total_strips = sum(qs_orig)

                        total_combinations += 1
                        combo_count += 1

                        if not count_only:
                            # Create combination dict
                            total_w = total_w / SCALE
                            scrap_mm = scrap_mm_int / SCALE
                            scrap_pct = (scrap_mm / coil_width) * 100 if coil_width > 0 else 0

                            combination = {
                                'qs': list(qs_orig),
                                'total_width': total_w,
                                'scrap_mm': scrap_mm,
                                'scrap_pct': scrap_pct,
                                'total_strips': total_strips
                            }

                            # Push to heap (negative for max-heap behavior)
                            # Include counter to ensure stable comparison in Python 3.x
                            heapq.heappush(heap, (-scrap_mm, -total_strips, counter, combination))
                            counter += 1

                            # Keep only best max_rows combinations
                            if len(heap) > max_rows:
                                heapq.heappop(heap)  # Remove worst combination (ignores counter in discard)

                        if progress_callback and combo_count % 1000 == 0:
                            progress_callback(combo_count)

                        if combo_count >= MAX_COMBINATIONS_LIMIT:
                            stopped_early = True
                            return
                continue

            # Not the last size: iterate quantities with pruning
            w = sorted_sizes[i]
            # Minimum width needed for remaining sizes
            rest_min = sum(sorted_sizes[j] for j in range(i + 1, n)) * min_q

            q = min_q
            while cur_w + q * w + rest_min <= cw_int:
                # Also check if even max possible remaining can reach min_width_used
                # Max possible from this point: cur_w + q*w + sum(remaining * max_q)
                # But we don't know max_q for remaining, so we just check lower bound
                # The upper bound is handled by the while condition (can't exceed coil_width)
                stack.append((i + 1, cur_w + q * w, cur_qs + [q]))
                q += 1

    search()

    # If count_only, return empty list with the count in progress_callback
    if count_only:
        return [], stopped_early, total_combinations

    # Extract results from heap and sort by scrap_mm (asc), then total_strips (asc)
    results = []
    while heap:
        neg_scrap_mm, neg_total_strips, counter_val, combination = heapq.heappop(heap)
        results.append(combination)

    # Sort by least scrap first, then fewer total strips (ascending)
    results.sort(key=lambda x: (x['scrap_mm'], x['total_strips']))

    # Add rank and is_best flag
    for i, item in enumerate(results):
        item['rank'] = i + 1
        item['is_best'] = (i == 0)

    return results, stopped_early, total_combinations


# ============================================================
# MAIN EXECUTION FUNCTIONS (for testing)
# ============================================================

if __name__ == "__main__":
    # Test the core functionality
    print("Testing core calculation engine...")

    # Test case A
    combos, stopped = find_all_combinations(
        coil_width=1250,
        strip_sizes=[111, 250],
        min_scrap_mm=0,
        max_scrap_mm=12.5,
        at_least_once=True
    )

    print(f"Test A: Found {len(combos)} combinations")
    if combos:
        best = combos[0]
        print(f"Best combination: {best['qs']} -> {best['total_width']:.1f}mm width, {best['scrap_mm']:.1f}mm scrap ({best['scrap_pct']:.2f}%)")

    # Test bounded version
    combos_bounded, stopped_bounded, total_found = find_all_combinations_bounded(
        coil_width=1250,
        strip_sizes=[111, 250],
        min_scrap_mm=0,
        max_scrap_mm=12.5,
        at_least_once=True,
        max_rows=5
    )

    print(f"Bounded test: Found {len(combos_bounded)} combinations (total possible: {total_found})")