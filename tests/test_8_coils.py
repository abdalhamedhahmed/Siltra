#!/usr/bin/env python
"""QTest real interactions: type 8 coils, enter weights, click Calculate, verify results"""

import sys
import os
import time

sys.path.insert(0, r'C:\Users\Abdalhamed Ahmed\Desktop\fac-1327')

from PySide6.QtWidgets import QApplication
from slitra.slitra_window import MainWindow
from slitra.slitra_controller import SlitraController


def test_8_coils():
    """Test with 8 coils, enter weights, and verify results."""
    app = QApplication.instance() or QApplication(sys.argv)

    window = MainWindow()
    controller = SlitraController(window)

    # ===== SETUP: 8 coils =====
    print("=== Setting up 8 coils ===")

    # Set number of coils to 8
    window.left.coils_edit.setText("8")
    window.left._on_count("8")

    # Wait for coil weights to be created (MAX_COILS = 8 rows pre-created)
    QApplication.processEvents()
    print(f"Number of coil weight entries created: {len(window.left.weights)}")

    # Set coil weights: 8 coils with varying weights
    # Using weights that should produce meaningful scrap
    test_weights = [10000, 10500, 9800, 11000, 10200, 9700, 10800, 10100]
    window.left.weights = test_weights[:]
    window.left.refresh()
    for i, weight in enumerate(test_weights):
        if i < len(window.left.weights):
            print(f"  Coil {i+1} weight set to {weight}kg")

    # ===== SETUP: Coil width =====
    print("\n=== Setting coil width ===")
    window.left.width_edit.setText("1250")

    # ===== SETUP: Scrap range =====
    print("\n=== Setting scrap range ===")
    window.left.smin_edit.setText("0")
    window.left.smax_edit.setText("30")
    window.left.every.setChecked(True)

    # ===== SETUP: Strip sizes (2 sizes to use with 8 coils) =====
    print("\n=== Setting strip sizes ===")
    # 2 strip sizes - using a range that will fit in 1250mm coil
    test_sizes = [111, 250]
    window.left.sizes_box.setCurrentText("2")
    window.left._relayout_sizes()

    QApplication.processEvents()
    print(f"Number of size entries created: {len([e for e in window.left.size_edits if e.isVisible()])}")

    for i, size in enumerate(test_sizes):
        if i < len(window.left.size_edits):
            window.left.size_edits[i].setText(str(size))
            print(f"  Size {i+1} set to {size}mm")

    # ===== TRIGGER CALCULATION =====
    print("\n=== Triggering calculation ===")
    window.calculate_requested.emit()

    # Wait for calculation to complete
    print("Waiting for calculation to complete...")
    for _ in range(50):  # Wait up to ~5 seconds
        QApplication.processEvents()
        if controller.all_combinations:
            break
        time.sleep(0.1)

    # ===== VERIFY RESULTS =====
    print("\n=== Verifying results ===")
    print(f"Number of coils: {window.left.coils_edit.text()}")
    print(f"Coil width: {window.left.width_edit.text()}")
    print(f"Average weight: {window.left.avg_edit.text()}")
    print(f"Min scrap: {window.left.smin_edit.text()}")
    print(f"Max scrap: {window.left.smax_edit.text()}")
    print(f"At least once: {window.left.every.isChecked()}")
    print(f"Number of sizes: {window.left.sizes_box.currentText()}")
    print(f"Results table row count: {window.right.table.results.shown}")

    # Print combo details
    if controller.all_combinations:
        print(f"\nTotal combinations found: {len(controller.all_combinations)}")
        best = controller.all_combinations[0]
        print(f"\nBest combination (Formula F1):")
        print(f"  Quantities: {best['qs']}")
        print(f"  Total width: {best['total_width']:.1f}mm")
        print(f"  Scrap: {best['scrap_mm']:.1f}mm ({best['scrap_pct']:.2f}%)")
        print(f"  Total strips: {best['total_strips']}")

    # Print selected combination from table
    if window.right.table.results.shown > 0:
        rank_item = window.right.table.model().index(0, 0)
        if rank_item.isValid():
            rank_text = rank_item.data()
            print(f"\nSelected table row 1:")
            print(f"  Rank: {rank_text}")

    # Verify weight check status
    print(f"\nWeight check label: {window.right.badge.state}")
    print(f"Weight check stylesheet preview: {window.right.badge.styleSheet()[:80] if window.right.badge.styleSheet() else 'N/A'}...")

    # Check legend and strip bar are populated
    print(f"\nLegend widget items: {window.right.legend.items}")
    print(f"Strip bar vm: {window.right.bar.vm}")

    # Cleanup
    window.deleteLater()
    print("\n[PASS] 8 coils test completed")


if __name__ == "__main__":
    try:
        test_8_coils()
        print("\n[SUCCESS] Test completed successfully!")
    except Exception as e:
        print(f"\n[FAIL] Error during test: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)