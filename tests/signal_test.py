#!/usr/bin/env python
"""Test to verify signal connections"""

import sys
import time
from PySide6.QtWidgets import QApplication
from slitra.slitra_window import MainWindow
from slitra.slitra_controller import SlitraController


def test_signal_connections():
    app = QApplication.instance() or QApplication(sys.argv)

    window = MainWindow()
    controller = SlitraController(window)

    # Set up debug handlers
    def debug_progress(count):
        print(f"[SIGNAL] Progress: {count}")

    def debug_result(result):
        print(f"[SIGNAL] Result received: {len(result)} combinations")

    def debug_error(error):
        print(f"[SIGNAL] Error: {error}")

    def debug_finished():
        print("[SIGNAL] Finished signal received")

    # Set reference test case values using new architecture
    window.left.coils_edit.setText("3")
    window.left._on_count("3")

    window.left.width_edit.setText("1260")

    # Wait for coil weights to be created, then set values
    app.processEvents()

    if len(window.left.weights) >= 3:
        # Apply weights via dialog - just set them directly for testing
        window.left.weights = [10000, 10000, 12000]
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

    print("=== Starting calculation with signal debug ===")

    # Start calculation - this will create calc_thread
    window.calculate_requested.emit()

    # Give it a moment to create the thread
    app.processEvents()
    time.sleep(0.1)

    # Now connect debug handlers to the calc_thread
    if controller.calc_thread:
        # Disconnect existing connections first
        try:
            controller.calc_worker.progress.disconnect()
            controller.calc_worker.finished.disconnect()
            controller.calc_worker.error.disconnect()
        except:
            pass  # Ignore if not connected

        controller.calc_worker.progress.connect(debug_progress)
        controller.calc_worker.finished.connect(debug_result)
        controller.calc_worker.error.connect(debug_error)
        controller.calc_worker.finished.connect(debug_finished)
        print("[DEBUG] Connected signal handlers to calc_worker")
    else:
        print("[DEBUG] calc_thread not found after calculate()")

    # Wait for calculation to complete
    timeout = 10  # 10 seconds max
    start_time = time.time()
    while time.time() - start_time < timeout:
        app.processEvents()
        time.sleep(0.1)

        # Check if we've gotten results
        if len(controller.all_combinations) > 0:
            print(f"[UI] Found {len(controller.all_combinations)} combinations in controller.all_combinations")
            break

    print(f"[UI] Final state:")
    print(f"  Status label: '{window.statusline.left.text()}'")
    print(f"  Results table rows: {window.right.table.results.shown}")
    print(f"  All combinations: {len(controller.all_combinations)}")
    print(f"  Filtered combinations: {len(controller.filtered_combinations)}")

    # Clean up
    window.deleteLater()


if __name__ == "__main__":
    try:
        test_signal_connections()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()