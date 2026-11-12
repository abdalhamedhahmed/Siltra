#!/usr/bin/env python
"""
UI Checks script for Phase A audit.
Runs at window sizes 1366x696, 1920x1008 and real screen size.
Checks: startup, CASE W, and 7-size 3-coil case.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from PySide6.QtWidgets import QApplication, QWidget, QLabel, QCheckBox, QPushButton
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QFontInfo
from PySide6.QtTest import QTest
import json

from slitra_window import MainWindow, apply_light_palette, SCRAP_RED, SIZE_COLORS
from slitra_controller import SlitraController


class UIChecks:
    def __init__(self):
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.window = None
        self.results = []
        self.screenshots_dir = os.path.join(os.path.dirname(__file__), 'screenshots')
        os.makedirs(self.screenshots_dir, exist_ok=True)

    def get_screen_info(self):
        """Print real screen info"""
        screen = self.app.primaryScreen()
        size = screen.size()
        avail = screen.availableGeometry()
        dpr = screen.devicePixelRatio()
        print(f"\n=== SCREEN INFO ===")
        print(f"Screen size: {size.width()}x{size.height()}")
        print(f"Available geometry: {avail.width()}x{avail.height()}")
        print(f"Device pixel ratio: {dpr}")
        return size, avail, dpr

    def run_checks_at_size(self, width, height, label):
        """Run all checks at a specific window size"""
        print(f"\n{'='*60}")
        print(f"CHECKS AT {label} ({width}x{height})")
        print(f"{'='*60}")

        if self.window:
            self.window.close()

        self.window = MainWindow()
        # Create and connect controller so Calculate button works
        self.controller = SlitraController(self.window)
        self.window.resize(width, height)
        self.window.show()
        self.app.processEvents()

        # Wait for window to be ready
        QTimer.singleShot(100, lambda: None)
        self.app.processEvents()

        checks = {}

        # 1. Check all buttons exist, visible, fully inside window
        checks['buttons'] = self.check_buttons()

        # 2. Check no widget extends past window, no sibling overlap
        checks['layout'] = self.check_layout()

        # 3. Check text visibility
        checks['text_visibility'] = self.check_text_visibility()

        # 4. Check startup state (generic columns only)
        checks['startup'] = self.check_startup_state()

        # Save screenshot
        screenshot_path = os.path.join(self.screenshots_dir, f"check_{label}_startup.png")
        self.window.grab().save(screenshot_path)
        print(f"Screenshot: {screenshot_path}")

        # 4. Run CASE W
        checks['case_w'] = self.run_case_w()
        screenshot_path = os.path.join(self.screenshots_dir, f"check_{label}_case_w.png")
        self.window.grab().save(screenshot_path)
        print(f"Screenshot: {screenshot_path}")

        # 5. Run 7-size 3-coil case
        checks['case_7size_3coil'] = self.run_case_7size_3coil()
        screenshot_path = os.path.join(self.screenshots_dir, f"check_{label}_case_7size_3coil.png")
        self.window.grab().save(screenshot_path)
        print(f"Screenshot: {screenshot_path}")

        return checks

    def check_buttons(self):
        """Check all required buttons exist and are visible"""
        # Check topbar buttons
        required_topbar = ['Calculate', 'Cancel', 'Clear', 'Export PDF', 'Export Excel', 'Save Preset', 'Load Preset', 'View Log']

        results = {}
        topbar_buttons = self.window.topbar.buttons

        for btn_name in required_topbar:
            if btn_name in topbar_buttons:
                btn = topbar_buttons[btn_name]
                visible = btn.isVisible()
                geo = btn.geometry()
                win_geo = self.window.geometry()
                inside = (geo.x() >= 0 and geo.y() >= 0 and
                          geo.right() <= win_geo.width() and
                          geo.bottom() <= win_geo.height())
                results[btn_name] = {'visible': visible, 'inside': inside, 'geometry': (geo.x(), geo.y(), geo.width(), geo.height())}
                if not visible or not inside:
                    print(f"  [WARN] {btn_name}: visible={visible}, inside={inside}, geo={geo}")
            else:
                results[btn_name] = {'visible': False, 'inside': False, 'error': 'Not found'}
                print(f"  [FAIL] {btn_name}: NOT FOUND")

        # Check Order & Limits button in TopBar
        if "Order & Limits..." in self.window.topbar.buttons:
            btn = self.window.topbar.buttons["Order & Limits..."]
            visible = btn.isVisible()
            geo = btn.geometry()
            win_geo = self.window.geometry()
            inside = (geo.x() >= 0 and geo.y() >= 0 and
                      geo.right() <= win_geo.width() and
                      geo.bottom() <= win_geo.height())
            results['Order & Limits'] = {'visible': visible, 'inside': inside, 'geometry': (geo.x(), geo.y(), geo.width(), geo.height())}
            if not visible or not inside:
                print(f"  [WARN] Order & Limits: visible={visible}, inside={inside}, geo={geo}")
        else:
            results['Order & Limits'] = {'visible': False, 'inside': False, 'error': 'Not found'}
            print(f"  [FAIL] Order & Limits: NOT FOUND")

        return results

    def check_layout(self):
        """Check no widget extends past window, no sibling overlap"""
        violations = []
        win_rect = self.window.rect()

        # Get all visible widgets
        all_widgets = []
        def collect_widgets(widget):
            if widget.isVisible() and widget != self.window:
                all_widgets.append(widget)
            for child in widget.findChildren(QWidget):
                if child.isVisible():
                    all_widgets.append(child)

        collect_widgets(self.window)

        # Check each widget is inside window
        for w in all_widgets:
            geo = w.geometry()
            if not win_rect.contains(geo):
                violations.append(f"Widget {w.objectName() or w.__class__.__name__} extends past window: {geo} vs {win_rect}")

        # Check sibling overlap (widgets with same parent)
        parents = {}
        for w in all_widgets:
            parent = w.parent()
            if parent:
                if parent not in parents:
                    parents[parent] = []
                parents[parent].append(w)

        for parent, children in parents.items():
            if len(children) > 1:
                for i, w1 in enumerate(children):
                    for w2 in children[i+1:]:
                        if w1.geometry().intersects(w2.geometry()):
                            violations.append(f"Overlap: {w1.objectName() or w1.__class__.__name__} vs {w2.objectName() or w2.__class__.__name__} in {parent}")

        if violations:
            print(f"  [WARN] Layout violations ({len(violations)}):")
            for v in violations[:10]:  # Show first 10
                print(f"    {v}")
        else:
            print("  [OK] No layout violations")

        return {'violations': violations, 'count': len(violations)}

    def check_text_visibility(self):
        """Check text visibility for all labels, checkboxes, buttons, comboboxes, and line edits.
        Grabs each widget and counts pixels whose brightness differs from the most common color by more than 40.
        Returns count of widgets with fewer than 5 such pixels (must be 0)."""
        print("\n  [CHECK] Text visibility...")

        # Find all relevant widgets
        target_types = (QLabel, QCheckBox, QPushButton)
        # Also check QComboBox and QLineEdit
        from PySide6.QtWidgets import QComboBox, QLineEdit
        target_types = target_types + (QComboBox, QLineEdit)

        invisible_count = 0
        checked_count = 0

        def collect_widgets(widget):
            widgets = []
            if widget.isVisible():
                widgets.append(widget)
            for child in widget.findChildren(QWidget):
                if child.isVisible():
                    widgets.append(child)
            return widgets

        all_widgets = collect_widgets(self.window)

        for w in all_widgets:
            if not isinstance(w, target_types):
                continue

            # Skip widgets with skip_text_check property
            if w.property("skip_text_check"):
                continue

            # Get text - different for different widget types
            text = ""
            if isinstance(w, (QLabel, QCheckBox, QPushButton)):
                text = w.text()
            elif isinstance(w, QComboBox):
                text = w.currentText()
            elif isinstance(w, QLineEdit):
                text = w.text()

            if not text:
                continue

            checked_count += 1

            # Grab widget pixmap
            try:
                pixmap = w.grab()
                if pixmap.isNull() or pixmap.width() == 0 or pixmap.height() == 0:
                    continue

                # Convert to image for pixel analysis
                image = pixmap.toImage()
                if image.isNull():
                    continue

                # Count pixels
                width = image.width()
                height = image.height()
                if width * height < 100:  # Too small to be meaningful
                    continue

                # Sample pixels (every 2nd pixel for speed)
                colors = []
                for y in range(0, height, 2):
                    for x in range(0, width, 2):
                        color = image.pixelColor(x, y)
                        # Calculate brightness (luminance)
                        brightness = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
                        colors.append(int(brightness))

                if not colors:
                    continue

                # Find most common color
                from collections import Counter
                color_counts = Counter(colors)
                most_common_color = color_counts.most_common(1)[0][0]

                # Count pixels that differ by more than 40 from most common
                distinct_pixels = sum(1 for c in colors if abs(c - most_common_color) > 40)

                if distinct_pixels < 5:
                    invisible_count += 1
                    print(f"    [INVISIBLE] {w.__class__.__name__} '{text[:50]}' - distinct pixels: {distinct_pixels}")
            except Exception as e:
                print(f"    [ERROR] Checking {w.__class__.__name__} '{text[:50]}': {e}")

        print(f"  Checked {checked_count} widgets with text")
        print(f"  Invisible (< 5 distinct pixels): {invisible_count}")

        return {'checked': checked_count, 'invisible': invisible_count, 'passed': invisible_count == 0}

    def check_startup_state(self):
        """Check Results table shows only generic columns at startup"""
        table = self.window.right.table
        headers = []
        for col in range(table.columnCount()):
            header_item = table.horizontalHeaderItem(col)
            if header_item:
                # Normalize header text (replace newlines with spaces)
                headers.append(header_item.text().replace('\n', ' '))

        expected = ["Rank", "Used width", "Scrap mm", "Scrap %", "Total strips"]

        match = headers == expected
        if match:
            print("  [OK] Startup state: Results table shows only generic columns")
        else:
            print(f"  [FAIL] Startup state mismatch:")
            print(f"    Expected: {expected}")
            print(f"    Got: {headers}")

        return {'match': match, 'headers': headers, 'expected': expected}

    def set_case_w_inputs(self):
        """Set inputs for CASE W"""
        # 3 coils, width 1290, average 10000 kg, sizes 111+250+79, scrap 0-30, every size at least once
        self.window.left.coils_edit.setText("3")
        self.app.processEvents()

        # Wait for coil weight fields to appear
        QTest.qWait(100)
        self.app.processEvents()

        # Set coil weights (3 coils, 10000 each = 30000 total)
        # Use the dialog to set weights
        self.window.left.apply_weights([10000.0, 10000.0, 10000.0])

        self.window.left.width_edit.setText("1290")

        self.window.left.sizes_box.setCurrentText("3")
        QTest.qWait(100)
        self.app.processEvents()

        # Set strip sizes: 111, 250, 79
        if len(self.window.left.size_edits) >= 3:
            self.window.left.size_edits[0].setText("111")
            self.window.left.size_edits[1].setText("250")
            self.window.left.size_edits[2].setText("79")

        self.window.left.smin_edit.setText("0")
        self.window.left.smax_edit.setText("30")
        self.window.left.every.setChecked(True)

        self.app.processEvents()

    def run_case_w(self):
        """Run CASE W and verify results"""
        self.set_case_w_inputs()

        # Click Calculate
        QTest.mouseClick(self.window.topbar.buttons["Calculate"], Qt.LeftButton)
        self.app.processEvents()

        # Wait for calculation to complete
        max_wait = 30000  # 30 seconds
        waited = 0
        while (hasattr(self.controller, 'calc_thread') and
               self.controller.calc_thread is not None and
               self.controller.calc_thread.isRunning() and
               waited < max_wait):
            QTest.qWait(100)
            waited += 100
            self.app.processEvents()

        if waited >= max_wait:
            print("  [FAIL] CASE W: Calculation timeout")
            return {'success': False, 'error': 'timeout'}

        # Wait for UI to update (show_results is called via signal)
        QTest.qWait(500)
        self.app.processEvents()

        # Check results
        table = self.window.right.table
        if table.rowCount() == 0:
            print("  [FAIL] CASE W: No results in table")
            return {'success': False, 'error': 'no results'}

        # Verify CASE W expected result: 2x111 + 3x250 + 4x79 = 1288, scrap 2 mm, 0.16%, scrap weight 15.50 kg per coil and 46.51 kg total
        best_row = 0  # First row should be best

        # Get the combination data
        if hasattr(self.controller, 'filtered_combinations') and self.controller.filtered_combinations:
            combo = self.controller.filtered_combinations[0]
            print(f"  Best combo: {combo['qs']} -> width={combo['total_width']:.0f}, scrap={combo['scrap_mm']:.1f}mm, scrap%={combo['scrap_pct']:.2f}%")

            # Check expected values
            expected_qs = [2, 3, 4]  # 2x111, 3x250, 4x79
            actual_qs = combo['qs']
            qs_match = actual_qs == expected_qs
            scrap_match = abs(combo['scrap_mm'] - 2) < 0.5
            pct_match = abs(combo['scrap_pct'] - 0.16) < 0.02

            # Check weight values
            details = combo.get('details', {})
            scrap_per_coil = 0
            scrap_total = 0
            if isinstance(details, dict) and details.get('details'):
                scrap_per_coil = details.get('scrap_weight_per_coil', 0)
                scrap_total = details.get('scrap_weight_total', 0)
                weight_per_coil_match = abs(scrap_per_coil - 15.50) < 0.1
                weight_total_match = abs(scrap_total - 46.51) < 0.1
            else:
                weight_per_coil_match = False
                weight_total_match = False

            all_match = qs_match and scrap_match and pct_match and weight_per_coil_match and weight_total_match

            if all_match:
                print("  [OK] CASE W: All values match expected")
            else:
                print(f"  [FAIL] CASE W: Mismatch - qs={actual_qs} (exp {expected_qs}), scrap={combo['scrap_mm']:.1f} (exp 2), pct={combo['scrap_pct']:.2f} (exp 0.16), scrap/coil={scrap_per_coil:.2f} (exp 15.50), scrap/total={scrap_total:.2f} (exp 46.51)")

            return {
                'success': all_match,
                'qs': actual_qs,
                'scrap_mm': combo['scrap_mm'],
                'scrap_pct': combo['scrap_pct'],
                'scrap_per_coil': scrap_per_coil,
                'scrap_total': scrap_total,
            }

        return {'success': False, 'error': 'no filtered combinations'}

    def set_case_7size_3coil_inputs(self):
        """Set inputs for 7-size 3-coil case"""
        self.window.left.coils_edit.setText("3")
        self.app.processEvents()
        QTest.qWait(100)
        self.app.processEvents()

        self.window.left.apply_weights([10000.0, 10000.0, 10000.0])

        self.window.left.width_edit.setText("1250")

        self.window.left.sizes_box.setCurrentText("7")
        QTest.qWait(100)
        self.app.processEvents()

        # Set 7 strip sizes
        sizes = [111, 250, 79, 150, 200, 300, 50]
        for i, entry in enumerate(self.window.left.size_edits):
            if i < len(sizes):
                entry.setText(str(sizes[i]))

        self.window.left.smin_edit.setText("0")
        self.window.left.smax_edit.setText("30")
        self.window.left.every.setChecked(True)

        self.app.processEvents()

    def run_case_7size_3coil(self):
        """Run 7-size 3-coil case"""
        self.set_case_7size_3coil_inputs()

        # Click Calculate
        QTest.mouseClick(self.window.topbar.buttons["Calculate"], Qt.LeftButton)
        self.app.processEvents()

        # Wait for calculation
        max_wait = 30000
        waited = 0
        while (hasattr(self.controller, 'calc_thread') and
               self.controller.calc_thread is not None and
               self.controller.calc_thread.isRunning() and
               waited < max_wait):
            QTest.qWait(100)
            waited += 100
            self.app.processEvents()

        if waited >= max_wait:
            print("  [FAIL] 7-size 3-coil: Calculation timeout")
            return {'success': False, 'error': 'timeout'}

        table = self.window.right.table
        if table.rowCount() == 0:
            print("  [FAIL] 7-size 3-coil: No results")
            return {'success': False, 'error': 'no results'}

        combo = self.controller.filtered_combinations[0] if hasattr(self.controller, 'filtered_combinations') and self.controller.filtered_combinations else None
        if combo:
            print(f"  Best combo: {combo['qs']} -> width={combo['total_width']:.0f}, scrap={combo['scrap_mm']:.1f}mm, scrap%={combo['scrap_pct']:.2f}%")
            return {'success': True, 'qs': combo['qs'], 'scrap_mm': combo['scrap_mm'], 'scrap_pct': combo['scrap_pct']}

        return {'success': False, 'error': 'no combo'}

    def audit_colors_and_fonts(self):
        """Audit color and font implementation"""
        print("\n=== COLOR & FONT AUDIT ===")

        # Check strip colors (from slitra_window)
        print(f"\nStrip colors (SIZE_COLORS):")
        for i, c in enumerate(SIZE_COLORS):
            print(f"  [{i}] {c}")

        # Check scrap color
        print(f"Scrap color: {SCRAP_RED}")

        # Check if Inter fonts exist
        font_files = ['Inter-Regular.ttf', 'Inter-Medium.ttf', 'Inter-SemiBold.ttf']
        for f in font_files:
            path = os.path.join(os.path.dirname(__file__), '..', f)
            exists = os.path.exists(path)
            print(f"Font {f}: {'[OK] EXISTS' if exists else '[FAIL] MISSING'}")

        # Check what font family is actually used on main widgets
        if self.window:
            # Check a few key widgets
            widgets_to_check = [
                ('results_table', self.window.right.table),
                ('strip_table', self.window.right.strip_table),
                ('weight_check_label', self.window.right.badge),
            ]

            print("\nActual font on widgets:")
            for name, widget in widgets_to_check:
                font = widget.font()
                info = QFontInfo(font)
                print(f"  {name}: family='{info.family()}', size={info.pointSize()}, weight={info.weight()}")

        return {
            'strip_colors': SIZE_COLORS,
            'scrap_color': SCRAP_RED,
            'inter_fonts_exist': all(os.path.exists(os.path.join(os.path.dirname(__file__), '..', f)) for f in font_files)
        }

    def audit_legend_and_strip_table(self):
        """Audit how legend and strip width table render colors"""
        print("\n=== LEGEND & STRIP TABLE COLOR AUDIT ===")

        if not hasattr(self.controller, 'filtered_combinations') or not self.controller.filtered_combinations:
            print("  No combinations loaded - run a calculation first")
            return {}

        combo = self.controller.filtered_combinations[0]

        # Check legend_widget (Legend class) - custom painted widget
        print("\nLegend widget (Legend):")
        if hasattr(self.window.right, 'legend') and self.window.right.legend.items:
            items = self.window.right.legend.items
            print(f"  Items: {len(items)} items")
            for color, text in items:
                print(f"    {text}: {color.name()}")
        else:
            print("  No items set on legend_widget")

        # Check weight_details_table (Strip width table) - stores color in UserRole
        print("\nWeight details table (Strip width table) items:")
        table = self.window.right.strip_table
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item:
                color = item.data(Qt.UserRole)
                print(f"  Row {row}: text='{item.text()}', UserRole color={color.name() if color else 'None'}")

        # Check strip_bar (StripBar class) - custom painted widget
        print("\nStrip bar (StripBar) items:")
        if hasattr(self.window.right, 'bar') and self.window.right.bar.vm:
            vm = self.window.right.bar.vm
            print(f"  VM: sizes={vm.get('sizes')}, qty={vm.get('qty')}, scrap={vm.get('scrap')}")
        else:
            print("  No VM set on strip_bar")

        return {}

    def audit_weight_badge(self):
        """Audit the weight check badge"""
        print("\n=== WEIGHT BADGE AUDIT ===")

        label = self.window.right.badge
        print(f"Weight check label state: '{label.state}'")
        print(f"Alignment: {label.alignment()}")
        print(f"Geometry: {label.geometry()}")

        # Check if it's a wide bar (spans full width) or compact
        geo = label.geometry()
        if geo.width() > 200:
            print(f"  [WARN] Wide bar detected (width={geo.width()}) - should be compact badge")
        else:
            print(f"  [OK] Compact badge (width={geo.width()})")

        return {'state': label.state, 'width': geo.width(), 'height': geo.height()}

    def audit_section_accents(self):
        """Check for red vertical accent bars on section titles"""
        print("\n=== SECTION ACCENT AUDIT ===")

        sections = [
            'Input Parameters',
            'Results',
            'Selected Combination',
        ]

        for title in sections:
            # Find the SectionTitle widget with this text
            found = False
            for child in self.window.findChildren(QWidget):
                # SectionTitle is a custom widget with a bar and label
                if hasattr(child, 'objectName') and child.objectName() == 'Panel':
                    # Check children of panels
                    for grandchild in child.findChildren(QLabel):
                        if grandchild.text() == title:
                            found = True
                            print(f"  Found '{title}': geometry={grandchild.geometry()}, style={grandchild.styleSheet()}")
                            break
                    if found:
                        break
                # Also check SectionTitle widgets directly
                if hasattr(child, 'title') and isinstance(getattr(child, 'title', None), QLabel):
                    if child.title.text() == title:
                        found = True
                        print(f"  Found '{title}' in SectionTitle: geometry={child.title.geometry()}")
                        break
            if not found:
                # Try finding directly by text
                for child in self.window.findChildren(QLabel):
                    if child.text() == title:
                        found = True
                        print(f"  Found '{title}': geometry={child.geometry()}, style={child.styleSheet()}")
                        break
            if not found:
                print(f"  [FAIL] '{title}' label not found")

        return {}

    def run_all(self):
        """Run all checks"""
        print("="*60)
        print("PHASE A: AUDIT AND CHECK SCRIPT")
        print("="*60)

        # 1. Git status
        print("\n=== GIT STATUS ===")
        os.system("git status")
        os.system("git log --oneline -5")

        # 2. Screen info
        self.get_screen_info()

        # 3. Run checks at different sizes
        screen = self.app.primaryScreen()
        real_size = screen.size()

        sizes = [
            (1366, 696, "1366x696"),
            (1920, 1008, "1920x1008"),
            (real_size.width(), real_size.height(), f"real_{real_size.width()}x{real_size.height()}"),
        ]

        all_results = {}
        for w, h, label in sizes:
            # Ensure window fits on screen
            if w <= real_size.width() and h <= real_size.height():
                all_results[label] = self.run_checks_at_size(w, h, label)
            else:
                print(f"\nSkipping {label} - larger than screen")

        # 4. Audit colors and fonts
        all_results['color_font_audit'] = self.audit_colors_and_fonts()

        # 5. Audit legend and strip table colors
        all_results['legend_strip_audit'] = self.audit_legend_and_strip_table()

        # 6. Audit weight badge
        all_results['weight_badge_audit'] = self.audit_weight_badge()

        # 7. Audit section accents
        all_results['section_accents_audit'] = self.audit_section_accents()

        # 8. Run regression cases
        print("\n=== REGRESSION CASES ===")
        all_results['regression'] = self.run_regression_cases()

        # Save results
        output_path = os.path.join(self.screenshots_dir, 'ui_checks_results.json')
        with open(output_path, 'w') as f:
            # Convert non-serializable objects
            def serialize(obj):
                if hasattr(obj, '__dict__'):
                    return str(obj)
                return obj

            json.dump(all_results, f, indent=2, default=serialize)

        print(f"\nResults saved to: {output_path}")

        if self.window:
            self.window.close()

        return all_results

    def run_regression_cases(self):
        """Run the four regression cases"""
        cases = [
            ("CASE_M", 1, 1250, [10000], [111, 250], 0, 30, True),
            ("CASE_B", 3, 1260, [10000, 10000, 10000], [111, 225, 79], 2, 5, True),
            ("CASE_S", 2, 1260, [10000, 10000], [111, 250, 79], 0, 30, True),
            ("CASE_W", 3, 1290, [10000, 10000, 10000], [111, 250, 79], 0, 30, True),
        ]

        results = {}

        for name, num_coils, coil_width, coil_weights, strip_sizes, min_scrap, max_scrap, at_least_once in cases:
            print(f"\n  Running {name}...")

            # Set inputs
            self.window.left.coils_edit.setText(str(num_coils))
            self.app.processEvents()
            QTest.qWait(100)

            self.window.left.apply_weights(coil_weights)

            self.window.left.width_edit.setText(str(coil_width))
            self.window.left.sizes_box.setCurrentText(str(len(strip_sizes)))
            QTest.qWait(100)
            self.app.processEvents()

            for i, entry in enumerate(self.window.left.size_edits):
                if i < len(strip_sizes):
                    entry.setText(str(strip_sizes[i]))

            self.window.left.smin_edit.setText(str(min_scrap))
            self.window.left.smax_edit.setText(str(max_scrap))
            self.window.left.every.setChecked(at_least_once)

            self.app.processEvents()

            # Click Calculate
            QTest.mouseClick(self.window.topbar.buttons["Calculate"], Qt.LeftButton)
            self.app.processEvents()

            # Wait for calculation
            max_wait = 30000
            waited = 0
            while (hasattr(self.controller, 'calc_thread') and
                   self.controller.calc_thread is not None and
                   self.controller.calc_thread.isRunning() and
                   waited < max_wait):
                QTest.qWait(100)
                waited += 100
                self.app.processEvents()

            if waited >= max_wait:
                results[name] = {'success': False, 'error': 'timeout'}
                continue

            combo = self.controller.filtered_combinations[0] if hasattr(self.controller, 'filtered_combinations') and self.controller.filtered_combinations else None
            if combo:
                results[name] = {
                    'success': True,
                    'qs': combo['qs'],
                    'total_width': combo['total_width'],
                    'scrap_mm': combo['scrap_mm'],
                    'scrap_pct': combo['scrap_pct'],
                    'total_strips': combo['total_strips'],
                }
                print(f"    qs={combo['qs']}, width={combo['total_width']:.0f}, scrap={combo['scrap_mm']:.1f}mm, pct={combo['scrap_pct']:.2f}%, strips={combo['total_strips']}")
            else:
                results[name] = {'success': False, 'error': 'no results'}

        return results


def main():
    checks = UIChecks()
    results = checks.run_all()

    print("\n" + "="*60)
    print("PHASE A COMPLETE")
    print("="*60)

    # Print summary
    for size_label, data in results.items():
        if isinstance(data, dict) and 'buttons' in data:
            print(f"\n{size_label}:")
            print(f"  Buttons: {sum(1 for v in data['buttons'].values() if v.get('visible', False))}/{len(data['buttons'])} visible")
            print(f"  Layout violations: {data['layout']['count']}")
            print(f"  Startup match: {data['startup']['match']}")
            print(f"  CASE W: {'[OK]' if data.get('case_w', {}).get('success') else '[FAIL]'}")
            print(f"  7-size 3-coil: {'[OK]' if data.get('case_7size_3coil', {}).get('success') else '[FAIL]'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())