#!/usr/bin/env python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtWidgets import QApplication
from slitra_window import MainWindow
from slitra_controller import SlitraController


def test_coil_weights():
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    controller = SlitraController(window)

    # Initially, coils_edit is empty (0), weights list is empty
    assert window.left._count() == 0, "Initial coils should be 0: got {}".format(window.left._count())
    assert len(window.left.weights) == 0, "Should have 0 coil weight entries initially, got {}".format(len(window.left.weights))

    # Change to 2 coils
    window.left.coils_edit.setText("2")
    window.left._on_count("2")
    assert len(window.left.weights) == 2, "Should have 2 coil weight entries"

    # Check default values - weights are None initially (not "0")
    assert window.left.weights[0] is None or window.left.weights[0] == 0
    assert window.left.weights[1] is None or window.left.weights[1] == 0

    # Change to 1 coil - weights list becomes empty, single weight held in _single
    window.left.coils_edit.setText("1")
    window.left._on_count("1")
    assert len(window.left.weights) == 0, "Should have 0 weights list entries (1 coil uses _single)"
    assert window.left._single is None or window.left._single == 0

    window.deleteLater()
    print("[PASS] Coil weight fields test passed")
    return True


if __name__ == "__main__":
    try:
        test_coil_weights()
        print("\n[PASS] All coil weight tests passed!")
    except Exception as e:
        print(f"\n[FAIL] Error during coil weight test: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)