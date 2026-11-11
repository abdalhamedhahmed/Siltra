#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
slitra_controller.py - Controller for Slitra v4.1.1 (ZAT AL-EMAD FACTORY)

This module contains ALL calculation, export, and business logic.
The window (slitra_window.py) is a pure UI - it emits signals and displays view models.
The controller connects to the window's signals and drives the application.

Architecture:
- slitra_window.py: Pure UI, emits signals (calculate_requested, params_changed, etc.)
- slitra_controller.py: All logic, connects to window signals, builds view models
- coil_slitting_calc.py: Core calculation engine (find_all_combinations, etc.)
- reports.py: PDF/Excel export (build_report_data, export_pdf, export_excel)
- app_info.py: Application metadata
"""

import sys
import os
import json
import threading
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal, Slot, QThread, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from PySide6.QtGui import QGuiApplication

# Local imports
from slitra.app_info import (
    APP_NAME, FACTORY_NAME, APP_VERSION,
    DEFAULT_MIN_SCRAP, DEFAULT_MAX_SCRAP, DEFAULT_AT_LEAST_ONCE
)
from slitra import core
from slitra import reports
from slitra import view_models
from slitra.state import MemoryStore


class CalculationWorker(QObject):
    """Worker thread for long-running combination search."""
    progress = Signal(int)  # combinations found so far
    finished = Signal(list, bool, int)  # results, stopped_early, total_combinations
    error = Signal(str)

    def __init__(self, params: Dict[str, Any]):
        super().__init__()
        self.params = params
        self.cancel_flag = threading.Event()

    def run(self):
        results = []
        stopped_early = False
        try:
            # Use unbounded version - finds ALL combinations (no 1M cap)
            results, stopped_early = core.find_all_combinations(
                coil_width=self.params['width'],
                strip_sizes=self.params['sizes'],
                min_scrap_mm=self.params['smin'],
                max_scrap_mm=self.params['smax'],
                at_least_once=self.params['every'],
                progress_callback=self.progress.emit,
                cancel_flag=self.cancel_flag
            )
        except Exception as e:
            self.error.emit(str(e))
        finally:
            # Always emit finished so the UI can recover from cancellation
            self.finished.emit(results, stopped_early, len(results))

    def cancel(self):
        self.cancel_flag.set()
        # When cancelling, we still need to emit finished so the UI can recover
        # The results will be whatever was computed before cancellation
        # stopped_early will be True if cancelled mid-search


class SlitraController(QObject):
    """Main controller - connects window signals to business logic."""

    def __init__(self, window):
        super().__init__()
        self.window = window

        # State
        self.current_params = {}
        self.all_combinations = []  # raw results from core
        self.filtered_combinations = []  # after applying any filters
        self.current_vm = None  # current view model
        self.selected_index = 0  # which combination is selected in table
        self.calc_thread = None
        self.calc_worker = None
        self.is_calculating = False
        self.memory = MemoryStore()

        # Settings
        self.settings_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'settings.json'
        )
        self.load_settings()

        # Connect window signals
        self._connect_signals()

        # Track user's row selection in the results table for exports
        self.window.right.table.rowChosen.connect(self.on_row_chosen)

        # Inject memory store into results panel
        self.window.right.set_memory_store(self.memory)

        # Connect history restore and suggestion signals
        self.window.right.inputsRestore.connect(self.on_inputs_restore)
        self.window.right.suggestion.connect(self.on_suggestion)

        # Initial state
        self.window.show_empty()
        self.window.set_status("Ready")

    def _connect_signals(self):
        """Connect all window signals to controller slots."""
        # Main actions
        self.window.calculate_requested.connect(self.on_calculate)
        self.window.clear_requested.connect(self.on_clear)
        self.window.cancel_requested.connect(self.on_cancel)
        self.window.export_pdf_requested.connect(self.on_export_pdf)
        self.window.export_excel_requested.connect(self.on_export_excel)
        self.window.save_preset_requested.connect(self.on_save_preset)
        self.window.load_preset_requested.connect(self.on_load_preset)
        self.window.view_log_requested.connect(self.on_view_log)

        # Live parameter updates
        self.window.params_changed.connect(self.on_params_changed)

    # ============================================================
    # SIGNAL HANDLERS
    # ============================================================

    @Slot(dict)
    def on_params_changed(self, params: Dict[str, Any]):
        """Handle live parameter changes from input panel."""
        self.current_params = params
        # Could auto-calculate here, but per requirements we only calculate on button press

    @Slot()
    def on_calculate(self):
        """Calculate combinations for current parameters."""
        if self.is_calculating:
            return

        # Always read fresh params from the UI (current_params may be stale
        # if the user hasn't triggered editingFinished on every field yet)
        params = self.window.left.get_all_params()
        self.current_params = params

        # Validate required fields
        if not self._validate_params(params):
            return

        self.is_calculating = True
        self.window.set_status("Calculating...")

        # Start calculation in worker thread
        self.calc_worker = CalculationWorker(params)
        self.calc_thread = QThread()
        self.calc_worker.moveToThread(self.calc_thread)

        self.calc_worker.progress.connect(self.on_calc_progress)
        self.calc_worker.finished.connect(self.on_calc_finished)
        self.calc_worker.error.connect(self.on_calc_error)
        self.calc_thread.started.connect(self.calc_worker.run)
        self.calc_thread.finished.connect(self.calc_thread.deleteLater)

        self.calc_thread.start()

    @Slot(int)
    def on_calc_progress(self, count: int):
        """Update progress during calculation."""
        self.window.set_status(f"Calculating... {count:,} combinations found")

    @Slot(list, bool, int)
    def on_calc_finished(self, results: list, stopped_early: bool, total_combinations: int):
        """Handle calculation completion."""
        self.is_calculating = False
        self.calc_thread.quit()
        self.calc_thread.wait()
        self.calc_thread = None
        self.calc_worker = None

        if not results:
            self.window.set_status("No valid combinations found for these parameters")
            self.window.show_empty()
            self.window.right.apply(None, self.current_params)
            return

        self.all_combinations = results
        self.filtered_combinations = results[:]  # no additional filtering for now
        self.selected_index = 0

        # Build view model from Formula F1 (best combination)
        self.current_vm = self._build_view_model(self.filtered_combinations[0], 0)
        self.window.show_results(self.current_vm)

        status = f"Showing all {len(self.all_combinations):,} combinations"
        self.window.set_status(status)

    @Slot(str)
    def on_calc_error(self, error: str):
        """Handle calculation error."""
        self.is_calculating = False
        if self.calc_thread:
            self.calc_thread.quit()
            self.calc_thread.wait()
            self.calc_thread = None
        self.window.set_status(f"Error: {error}")
        QMessageBox.critical(self.window, "Calculation Error", error)

    @Slot()
    def on_clear(self):
        """Clear all inputs and results."""
        self.window.left.set_state(None)
        self.window.show_empty()
        self.current_params = {}
        self.all_combinations = []
        self.filtered_combinations = []
        self.current_vm = None
        self.selected_index = 0
        self.window.set_status("Cleared")

    @Slot()
    def on_cancel(self):
        """Cancel current calculation."""
        if self.calc_worker:
            self.calc_worker.cancel()
            self.window.set_status("Cancelling...")

    @Slot()
    def on_export_pdf(self):
        """Export current results to PDF."""
        if not self.current_vm:
            QMessageBox.warning(self.window, "No Data", "No calculation results to export")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self.window, "Export PDF", f"{APP_NAME}_CuttingPlan.pdf", "PDF Files (*.pdf)"
        )
        if not filepath:
            return

        self.window.set_status("Exporting PDF...")
        QApplication.processEvents()

        try:
            report_data = self._build_report_data(self.selected_index)

            success = reports.export_pdf(report_data, filepath, version=APP_VERSION)
            if success:
                self.window.set_status(f"PDF exported: {os.path.basename(filepath)}")
                QMessageBox.information(self.window, "Export Complete", f"PDF saved to:\n{filepath}")
            else:
                self.window.set_status("PDF export failed")
                QMessageBox.warning(self.window, "Export Failed", "Failed to generate PDF")
        except Exception as e:
            self.window.set_status(f"Export error: {e}")
            QMessageBox.critical(self.window, "Export Error", str(e))

    @Slot()
    def on_export_excel(self):
        """Export current results to Excel."""
        if not self.current_vm:
            QMessageBox.warning(self.window, "No Data", "No calculation results to export")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self.window, "Export Excel", f"{APP_NAME}_CuttingPlan.xlsx", "Excel Files (*.xlsx)"
        )
        if not filepath:
            return

        self.window.set_status("Exporting Excel...")
        QApplication.processEvents()

        try:
            report_data = self._build_report_data(self.selected_index)

            success = reports.export_excel(report_data, filepath, version=APP_VERSION)
            if success:
                self.window.set_status(f"Excel exported: {os.path.basename(filepath)}")
                QMessageBox.information(self.window, "Export Complete", f"Excel saved to:\n{filepath}")
            else:
                self.window.set_status("Excel export failed")
                QMessageBox.warning(self.window, "Export Failed", "Failed to generate Excel")
        except Exception as e:
            self.window.set_status(f"Export error: {e}")
            QMessageBox.critical(self.window, "Export Error", str(e))

    @Slot()
    def on_save_preset(self):
        """Save current parameters as a preset."""
        params = self.current_params or self.window.left.get_all_params()
        if not params.get('sizes'):
            QMessageBox.warning(self.window, "No Data", "No strip sizes to save")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self.window, "Save Preset", f"{APP_NAME}_preset.json", "JSON Files (*.json)"
        )
        if not filepath:
            return

        try:
            preset = {
                'version': APP_VERSION,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'params': params,
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(preset, f, indent=2)
            self.window.set_status(f"Preset saved: {os.path.basename(filepath)}")
        except Exception as e:
            QMessageBox.critical(self.window, "Save Error", str(e))

    @Slot()
    def on_load_preset(self):
        """Load parameters from a preset file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self.window, "Load Preset", "", "JSON Files (*.json)"
        )
        if not filepath:
            return

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                preset = json.load(f)

            params = preset.get('params', {})
            if not params:
                raise ValueError("Invalid preset file")

            # Apply to input panel (ignore any order_mode fields silently)
            self.window.left.set_state(params)
            self.current_params = params
            self.window.set_status(f"Preset loaded: {os.path.basename(filepath)}")
        except Exception as e:
            QMessageBox.critical(self.window, "Load Error", str(e))

    @Slot(int)
    def on_row_chosen(self, view_row: int):
        """Update selected_index when user clicks a different row in the results table."""
        if 0 <= view_row < len(self.filtered_combinations):
            self.selected_index = view_row

    @Slot(dict)
    def on_inputs_restore(self, cfg: dict):
        """Restore input panel state from a history entry (no search needed)."""
        self.window.left.set_state(cfg)
        self.current_params = cfg
        self.window.set_status("History restored")

    @Slot(str, int)
    def on_suggestion(self, key: str, value: int):
        """Apply a one-click suggestion from explain_no_plan (set scrap min/max)."""
        params = self.window.left.get_all_params()
        if key == "scrap_max":
            self.window.left.smax_edit.setText(str(value))
        elif key == "scrap_min":
            self.window.left.smin_edit.setText(str(value))
        self.current_params = params
        self.window.set_status("Suggestion applied: %s -> %d mm. Press Calculate." % (key, value))

    @Slot()
    def on_view_log(self):
        """Show calculation log / debug info."""
        if not self.all_combinations:
            QMessageBox.information(self.window, "Log", "No calculations performed yet")
            return

        f1 = self.all_combinations[0] if self.all_combinations else None
        scrap_str = f"{f1['scrap_mm']:.1f} mm ({f1['scrap_pct']:.2f}%)" if f1 else 'N/A'
        log_text = f"""{APP_NAME} v{APP_VERSION} - Calculation Log
Factory: {FACTORY_NAME}
Time: {time.strftime('%Y-%m-%d %H:%M:%S')}

Parameters:
  Coil width: {self.current_params.get('width', 0)} mm
  Strip sizes: {self.current_params.get('sizes', [])}
  Number of coils: {self.current_params.get('coils', 1)}
  Scrap range: {self.current_params.get('smin', 0)} - {self.current_params.get('smax', 30)} mm
  At least once: {self.current_params.get('every', True)}
  Coil weights: {self.current_params.get('weights', [])}

Results:
  Total combinations found: {len(self.all_combinations):,}
  Showing: {len(self.filtered_combinations):,}
  Selected index: {self.selected_index} (Formula F{self.selected_index + 1})

Formula F1 (best combination):
  Quantities: {f1['qs'] if f1 else 'N/A'}
  Scrap: {scrap_str}
  Total strips: {f1['total_strips'] if f1 else 'N/A'}
"""
        QMessageBox.information(self.window, "Calculation Log", log_text)

    # ============================================================
    # HELPER METHODS
    # ============================================================

    def _validate_params(self, params: Dict[str, Any]) -> bool:
        """Validate calculation parameters."""
        if not params.get('sizes'):
            QMessageBox.warning(self.window, "Missing Input", "Please enter at least one strip size")
            return False

        if params.get('width', 0) <= 0:
            QMessageBox.warning(self.window, "Missing Input", "Please enter a valid coil width")
            return False

        if params.get('avg', 0) <= 0:
            QMessageBox.warning(self.window, "Missing Input", "Please enter a valid average coil weight")
            return False

        weights = params.get('weights', [])
        coils = params.get('coils', 1)
        if len(weights) < coils:
            QMessageBox.warning(self.window, "Missing Input", f"Please enter weights for all {coils} coils")
            return False

        if any(w <= 0 for w in weights[:coils]):
            QMessageBox.warning(self.window, "Invalid Input", "All coil weights must be positive")
            return False

        if params.get('smax', 30) < params.get('smin', 0):
            QMessageBox.warning(self.window, "Invalid Input", "Max scrap must be >= min scrap")
            return False

        return True

    def _build_view_model(self, combo: Dict[str, Any], index: int) -> Dict[str, Any]:
        """Build a view model dict from a combination result for the window."""
        params = self.current_params
        qs = combo['qs']
        sizes = params['sizes']
        coil_width = params['width']
        scrap = combo['scrap_mm']
        total_width = combo['total_width']
        avg_weight = params['avg']
        num_coils = params['coils']
        weights = params['weights'][:num_coils]

        # Build all rows from ALL combinations (no limit)
        rows = []
        for c in self.filtered_combinations:
            rows.append((c['scrap_mm'], tuple(c['qs'])))

        # Use plan_vm for the selected combination details
        vm = view_models.plan_vm({
            'width': coil_width,
            'sizes': sizes,
            'avg': avg_weight,
            'coils': num_coils,
        }, scrap, qs)

        # Add the additional fields the window expects
        vm.update({
            'rows': rows,
            'total': len(self.all_combinations),
            'cfg': {
                'width': coil_width,
                'sizes': sizes,
                'avg': avg_weight,
                'coils': num_coils,
                'weights': self.current_params.get('weights', []),
                'smin': self.current_params.get('smin', 0),
                'smax': self.current_params.get('smax', 30),
                'every': self.current_params.get('every', True),
            },
            'details': None,  # Not used by new window
        })
        return vm

    def _build_report_data(self, selected_index: int) -> Dict[str, Any]:
        """Build report data for PDF/Excel export."""
        if not self.filtered_combinations:
            return {}

        selected = self.filtered_combinations[selected_index]
        params = self.current_params

        # Build coil_weights list
        num_coils = params.get('coils', 1)
        weights = params.get('weights', [])
        if len(weights) >= num_coils:
            coil_weights = weights[:num_coils]
        else:
            avg = params.get('avg', 10000)
            coil_weights = [avg] * num_coils

        # Calculate detail weights using core (returns dict with 'details' key and 'scrap_weight_total')
        details_result = core.calculate_combination_details(
            tuple(selected['qs']),
            params['width'],
            sum(coil_weights),
            num_coils,
            params['sizes']
        )

        # Build result dict matching what build_report_data expects
        result = {
            'all_combinations': self.all_combinations,
            'filtered_combinations': self.filtered_combinations,
            'total_combinations': len(self.all_combinations),
            'stopped_early': False,  # we'd need to track this from worker
        }

        # Add the selected combination with all required fields for reports.build_report_data
        # build_report_data reads from filtered_combinations at selected_index
        # We need to add the extra fields to the selected combination in filtered_combinations
        selected_for_report = {
            **selected,
            'coil_width': params['width'],
            'num_coils': num_coils,
            'strip_sizes': params['sizes'],
            'min_scrap': params['smin'],
            'max_scrap': params['smax'],
            'at_least_once': params['every'],
            'total_coil_weight': sum(coil_weights),
            'coil_weights': coil_weights,
            'details': details_result,
        }
        # Replace the selected entry in filtered_combinations for report generation
        filtered_for_report = self.filtered_combinations[:]
        filtered_for_report[selected_index] = selected_for_report
        result['filtered_combinations'] = filtered_for_report

        return reports.build_report_data(result, selected_index, {
            'coil_width': params['width'],
            'num_coils': num_coils,
            'strip_sizes': params['sizes'],
            'min_scrap': params['smin'],
            'max_scrap': params['smax'],
            'at_least_once': params['every'],
            'total_coil_weight': sum(coil_weights),
            'coil_weights': coil_weights,
        })

    def load_settings(self):
        """Load application settings from JSON file."""
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                # Apply any saved window state, recent files, etc.
            except Exception:
                pass

    def save_settings(self):
        """Save application settings to JSON file."""
        settings = {
            'version': APP_VERSION,
            # Add any persistent settings here
        }
        try:
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2)
        except Exception:
            pass


def create_app_and_window():
    """Factory function to create QApplication, window, and controller."""
    from .slitra_window import MainWindow, apply_light_palette

    app = QApplication(sys.argv)
    apply_light_palette(app)

    window = MainWindow()
    controller = SlitraController(window)

    return app, window, controller


def main():
    """Main entry point for the full application."""
    app, window, controller = create_app_and_window()
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())