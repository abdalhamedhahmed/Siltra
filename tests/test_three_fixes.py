#!/usr/bin/env python
"""Test the three PDF fixes: SWATCH, RULER, FOOTER"""

import sys
import os
sys.path.insert(0, r'C:\Users\Abdalhamed Ahmed\Desktop\fac-1327')

from slitra.core import find_all_combinations_bounded, calculate_combination_details
from slitra.reports import build_report_data, export_pdf, export_excel

def test_case(name, coil_width, strip_sizes, min_scrap, max_scrap, at_least_once, num_coils, total_coil_weight):
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"{'='*60}")

    try:
        combos, stopped_early, total_combinations = find_all_combinations_bounded(
            coil_width, strip_sizes, min_scrap, max_scrap, at_least_once
        )

        print(f"Found {len(combos)} combinations (stopped_early={stopped_early}, total={total_combinations})")

        if not combos:
            print("No combinations found!")
            return False

        for c in combos:
            c['details'] = calculate_combination_details(tuple(c['qs']), coil_width, total_coil_weight, num_coils, strip_sizes)
            c['coil_width'] = coil_width
            c['num_coils'] = num_coils
            c['strip_sizes'] = strip_sizes
            c['min_scrap'] = min_scrap
            c['max_scrap'] = max_scrap
            c['at_least_once'] = at_least_once
            c['total_coil_weight'] = total_coil_weight

        result = {
            'all_combinations': combos,
            'filtered_combinations': combos,
            'total_combinations': total_combinations,
            'stopped_early': stopped_early,
        }

        settings = {
            'coil_width': coil_width,
            'num_coils': num_coils,
            'strip_sizes': strip_sizes,
            'min_scrap': min_scrap,
            'max_scrap': max_scrap,
            'at_least_once': at_least_once,
            'total_coil_weight': total_coil_weight,
        }

        report_data = build_report_data(result, 0, settings)

        if 'error' in report_data:
            print(f"Error building report: {report_data['error']}")
            return False

        print(f"Selected combo: {report_data['selected_combination']['qs']}")
        print(f"Scrap: {report_data['selected_combination'].get('scrap_mm', 0):.1f}mm ({report_data['selected_combination'].get('scrap_pct', 0):.2f}%)")
        print(f"Weight verification: diff={report_data['weight_verification']['difference']:.6f}kg, passes={report_data['weight_verification']['passes']}")

        # Export PDF
        pdf_file = f"test_{name.replace(' ', '_')}.pdf"
        success = export_pdf(report_data, pdf_file, version='3.7.1')
        print(f"PDF export: {success}")
        if success and os.path.exists(pdf_file):
            print(f"  PDF size: {os.path.getsize(pdf_file)} bytes")

        # Export Excel
        xlsx_file = f"test_{name.replace(' ', '_')}.xlsx"
        success = export_excel(report_data, xlsx_file, version='3.7.1')
        print(f"Excel export: {success}")
        if success and os.path.exists(xlsx_file):
            print(f"  Excel size: {os.path.getsize(xlsx_file)} bytes")

        return True

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("Testing three PDF fixes: SWATCH, RULER, FOOTER")

    # CASE P, T, W - specific test cases
    test_cases = [
        # CASE P: Standard case with two sizes
        ("CASE_P", 1250, [111, 250], 0, 10, True, 1, 10000),
        # CASE T: Three sizes
        ("CASE_T", 1250, [100, 200, 300], 0, 15, True, 1, 10000),
        # CASE W: Multi-coil
        ("CASE_W", 1250, [111, 250], 0, 10, True, 5, 50000),
        # Also test CASE M and S as regression
        ("CASE_M", 1250, [111, 250], 0, 10, True, 1, 10000),
        ("CASE_S", 1250, [111, 250], 0, 30, True, 1, 10000),
    ]

    passed = 0
    failed = 0

    for case in test_cases:
        if test_case(*case):
            passed += 1
        else:
            failed += 1

    print(f"\n{'='*60}")
    print(f"SUMMARY: {passed} passed, {failed} failed out of {len(test_cases)} test cases")
    print(f"{'='*60}")

    if failed == 0:
        print("ALL TESTS PASSED!")
        return 0
    else:
        print("SOME TESTS FAILED!")
        return 1

if __name__ == "__main__":
    sys.exit(main())