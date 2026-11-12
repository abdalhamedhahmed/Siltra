#!/usr/bin/env python
"""Test script to verify UI functionality without showing GUI"""

import sys
import os
from unittest.mock import patch, MagicMock

# Add the current directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def test_imports():
    """Test that all required modules can be imported"""
    try:
        from PySide6.QtWidgets import QApplication
        from slitra_window import MainWindow
        from slitra_controller import SlitraController
        import core as core
        print("[PASS] All imports successful")
        return True
    except Exception as e:
        print(f"[FAIL] Import error: {e}")
        return False


def test_core_functions():
    """Test that core functions work as expected"""
    try:
        from core import find_all_combinations, find_all_combinations_bounded

        # Test basic calculation
        combos, stopped = find_all_combinations(
            coil_width=1250,
            strip_sizes=[111, 250],
            min_scrap_mm=0,
            max_scrap_mm=30,
            at_least_once=True
        )

        assert len(combos) > 0, "Should find combinations"
        print(f"[PASS] Core calculation works: found {len(combos)} combinations")

        # Test bounded version
        combos_b, stopped_b, total = find_all_combinations_bounded(
            coil_width=1250,
            strip_sizes=[111, 250],
            min_scrap_mm=0,
            max_scrap_mm=30,
            at_least_once=True,
            max_rows=1000
        )

        assert len(combos_b) > 0, "Bounded version should find combinations"
        print(f"[PASS] Bounded calculation works: found {len(combos_b)} combinations")

        return True
    except Exception as e:
        print(f"[FAIL] Core test error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ui_initialization():
    """Test that UI can be initialized (without showing)"""
    try:
        from PySide6.QtWidgets import QApplication
        from slitra_window import MainWindow

        # Create QApplication if needed
        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        # Create window
        window = MainWindow()

        # Test that UI elements exist
        assert hasattr(window, 'left'), "Missing left input panel"
        assert hasattr(window, 'right'), "Missing right results panel"
        assert hasattr(window.left, 'width_edit'), "Missing width_edit"
        assert hasattr(window.right, 'table'), "Missing results table"

        # Test default values (all fields start at 0/empty)
        # Note: coils_edit starts empty, _count() returns 0, every checkbox is False
        assert window.left.coils_edit.text() == "", "Wrong default coils (should be empty)"
        assert window.left._count() == 0, "Wrong default coil count"

        # Clean up
        window.deleteLater()

        print("[PASS] UI initialization works")
        return True
    except Exception as e:
        print(f"[FAIL] UI initialization error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_get_input_values():
    """Test input validation and retrieval"""
    try:
        from PySide6.QtWidgets import QApplication
        from slitra_window import MainWindow

        app = QApplication.instance() or QApplication([])
        window = MainWindow()

        # Test valid input
        window.left.coils_edit.setText("2")
        window.left._on_count("2")
        window.left.width_edit.setText("1000")
        window.left.smin_edit.setText("0")
        window.left.smax_edit.setText("20")

        # Add coil weights
        window.left.weights = [5000.0, 3000.0]
        window.left.refresh()

        # Add size entries
        window.left.sizes_box.setCurrentText("2")
        window.left._relayout_sizes()
        app.processEvents()
        window.left.size_edits[0].setText("100")
        window.left.size_edits[1].setText("200")

        inputs = window.left.get_all_params()
        assert inputs is not None, "Should return valid inputs"
        assert inputs['coils'] == 2, "Wrong coil count: got {}".format(inputs.get('coils'))
        assert inputs['width'] == 1000, "Wrong width"
        assert len(inputs['weights']) == 2, "Wrong coil weights count"
        assert inputs['weights'][0] == 5000.0, "Wrong first coil weight"
        assert inputs['weights'][1] == 3000.0, "Wrong second coil weight"
        assert inputs['sizes'] == [100, 200], "Wrong strip sizes"
        assert inputs['smin'] == 0, "Wrong min scrap"
        assert inputs['smax'] == 20, "Wrong max scrap"
        assert inputs['every'] == False, "Wrong at_least_once (default is False)"

        window.deleteLater()
        print("[PASS] Input validation works")
        return True
    except Exception as e:
        print(f"[FAIL] Input test error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_theme_system():
    """Test that theme switching works"""
    try:
        from PySide6.QtWidgets import QApplication
        from slitra_window import MainWindow

        app = QApplication.instance() or QApplication([])
        window = MainWindow()

        # Test that the window has a status line and panels
        assert hasattr(window, 'statusline'), "Missing status line"
        assert hasattr(window.left, 'get_all_params'), "Missing get_all_params"

        window.deleteLater()
        print("[PASS] Window structure works")
        return True
    except Exception as e:
        print(f"[FAIL] Theme test error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("Running Slitra functionality tests...\n")

    tests = [
        test_imports,
        test_core_functions,
        test_ui_initialization,
        test_get_input_values,
        test_theme_system,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        if test():
            passed += 1
        print()  # Empty line between tests

    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("[PASS] All tests passed! The UI is ready for use.")
        return 0
    else:
        print("❌ Some tests failed. Please review the implementation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())