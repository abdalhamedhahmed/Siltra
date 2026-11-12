#!/usr/bin/env python
"""Test script to verify the calculation fix"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtWidgets import QApplication
from slitra_window import MainWindow
from slitra_controller import SlitraController
import time


def test_calculation_complete():
    app = QApplication.instance() or QApplication(sys.argv)

    window = MainWindow()
    controller = SlitraController(window)

    # Set reference test case values
    window.left.coils_edit.setText("3")
    window.left._on_count("3")

    window.left.width_edit.setText("1260")

    # Wait for coil weights to be created, then set values
    app.processEvents()

    if len(window.left.weights) >= 3:
        window.left.weights[0] = 10000
        window.left.weights[1] = 10000
        window.left.weights[2] = 12000
        window.left.refresh()

    window.left.smin_edit.setText("2")
    window.left.smax_edit.setText("5")
    window.left.every.setChecked(True)

    window.left.sizes_box.setCurrentText("3")
    window.left._relayout_sizes()

    # Wait for size entries to be created, then set values
    app.processEvents()

    if len(window.left.size_edits) >= 3:
        window.left.size_edits[0].setText("111")
        window.left.size_edits[1].setText("225")
        window.left.size_edits[2].setText("79")

    print("Starting calculation...")
    start_time = time.time()

    # Start calculation
    window.calculate_requested.emit()

    # Wait for calculation to complete (with timeout)
    timeout = 30  # 30 seconds max
    elapsed = 0
    while controller.is_calculating and elapsed < timeout:
        app.processEvents()  # Keep UI responsive
        time.sleep(0.1)
        elapsed += 0.1

        # Print status every second
        if int(elapsed) % 1 == 0 and elapsed > 0:
            print(f"  [{elapsed:.1f}s] Status: {window.statusline.left.text()}")

    end_time = time.time()
    calculation_time = end_time - start_time

    print(f"\nCalculation finished after {calculation_time:.2f} seconds")
    print(f"Final status: {window.statusline.left.text()}")
    print(f"Results table row count: {window.right.table.results.shown}")

    if window.right.table.results.shown > 0:
        print("\nResults data:")
        for row in range(min(3, window.right.table.results.shown)):  # Show first 3 rows
            print(f"  Row {row+1}:", end="")
            for col in range(window.right.table.model().columnCount()):
                model = window.right.table.model()
                item = model.index(row, col)
                header = model.headerData(col, 1)  # Qt.Horizontal
                if item.isValid() and header is not None:
                    print(f" {header}:{item.data()}", end="")
            print()

        # Check if we have the expected best combination
        first_item = window.right.table.model().index(0, 0)  # Formula column
        if first_item.isValid() and "F1" in first_item.data():
            print("\n[PASS] Best combination correctly marked as Formula F1")
        else:
            print("\n[FAIL] Best combination not marked correctly")

    else:
        print("[FAIL] No results found in table")

    # Check stat cards have non-zero values where expected
    used_width = window.right.cards[0].value.text()
    scrap_mm = window.right.cards[1].value.text()
    scrap_per_coil = window.right.cards[2].value.text()
    scrap_total = window.right.cards[3].value.text()

    print(f"\nStat card values:")
    print(f"  Used width: {used_width} mm")
    print(f"  Scrap: {scrap_mm} mm")
    print(f"  Scrap per coil: {scrap_per_coil} kg")
    print(f"  Scrap total: {scrap_total} kg")

    # Clean up
    window.deleteLater()

    # Return success if we got results and calculation completed
    success = (window.right.table.results.shown > 0 and
               not controller.is_calculating and
               calculation_time < timeout)

    return success


if __name__ == "__main__":
    try:
        success = test_calculation_complete()
        if success:
            print("\n[PASS] Calculation fix test completed successfully!")
            sys.exit(0)
        else:
            print("\n[FAIL] Calculation fix test failed!")
            sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] Error during test: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)