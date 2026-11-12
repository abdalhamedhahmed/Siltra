#!/usr/bin/env python3
"""
Real Launch Parity Audit - Compares old window (ui_qt.py --old) vs new window (ui_qt.py --new)
using QTest for real interactions. Runs each in separate subprocess.
"""
import sys
import os
import subprocess

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)

def run_audit_for_window(window_type, output_file):
    """Run parity audit for a specific window type in a subprocess"""
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'

    test_script = f'''
import sys
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

sys.path.insert(0, r"{project_root}")
os.chdir(r"{project_root}")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtGui import QGuiApplication, QPalette, QPixmap

# Add src to path so 'slitra' package imports work
sys.path.insert(0, r"{project_root}/src")
os.chdir(r"{project_root}")

print("=== PARITY AUDIT: {window_type} ===")

# Import from the new app entry point (ui_qt.py was removed during refactor)
from slitra_controller import create_app_and_window

original_exec = QApplication.exec
captured = False

def hooked_exec():
    global captured
    if not captured:
        captured = True
        app = QApplication.instance()
        print(f'Main window class: ' + app.activeWindow().__class__.__name__ if app.activeWindow() else 'None')
        print('Style: ' + app.style().objectName())
        if hasattr(QGuiApplication, 'styleHints'):
            hints = QGuiApplication.styleHints()
            if hasattr(hints, 'colorScheme'):
                cs = hints.colorScheme()
                scheme_str = 'Dark' if cs == 2 else 'Light' if cs == 1 else str(cs)
                print('ColorScheme: ' + scheme_str)

        # Find main window
        main_window = None
        for w in app.topLevelWidgets():
            if w.isVisible() and w.__class__.__name__ in ('MainWindow', 'CoilSlittingCalculator'):
                main_window = w
                break

        if not main_window:
            print("ERROR: No main window found")
            app.quit()
            return 0

        print(f"Testing {{main_window.__class__.__name__}}")

        # 1. Check header buttons exist
        print("\\n--- HEADER BUTTONS ---")
        header_buttons = ['Calculate', 'Cancel', 'Clear', 'Export PDF', 'Export Excel',
                          'Save Preset', 'Load Preset', 'View Log', 'Order & Limits...']

        for btn_name in header_buttons:
            btn = find_button(main_window, btn_name)
            if btn:
                print(f"  {{btn_name}}: FOUND (enabled={{btn.isEnabled()}})")
                connections = get_connections(btn)
                print(f"    Connected slots: {{connections}}")
            else:
                print(f"  {{btn_name}}: MISSING")

        # 2. Test Calculate button click
        print("\\n--- CALCULATE BUTTON TEST ---")
        calc_btn = find_button(main_window, 'Calculate')
        if calc_btn:
            print(f"  Calculate button enabled: {{calc_btn.isEnabled()}}")
            try:
                QTest.mouseClick(calc_btn, Qt.LeftButton)
                app.processEvents()
                print("  Clicked Calculate - checking status...")
                status = get_status_text(main_window)
                print(f"  Status after click: {{status}}")
            except Exception as e:
                print(f"  ERROR clicking Calculate: {{e}}")

        # 3. Test Clear button
        print("\\n--- CLEAR BUTTON TEST ---")
        clear_btn = find_button(main_window, 'Clear')
        if clear_btn:
            try:
                QTest.mouseClick(clear_btn, Qt.LeftButton)
                app.processEvents()
                print("  Clicked Clear")
                status = get_status_text(main_window)
                print(f"  Status after click: {{status}}")
            except Exception as e:
                print(f"  ERROR clicking Clear: {{e}}")

        # 4. Test input panel
        print("\\n--- INPUT PANEL TEST ---")
        test_input_panel(main_window, app)

        # 5. Test Order & Limits
        print("\\n--- ORDER & LIMITS TEST ---")
        order_btn = find_button(main_window, 'Order & Limits...')
        if order_btn:
            print(f"  Order button enabled: {{order_btn.isEnabled()}}")
            try:
                QTest.mouseClick(order_btn, Qt.LeftButton)
                app.processEvents()
                modal = QApplication.activeModalWidget()
                if modal:
                    print(f"  Modal opened: {{modal.__class__.__name__}}, size: {{modal.size()}}")
                    modal.close()
                else:
                    print("  No modal dialog opened")
            except Exception as e:
                print(f"  ERROR clicking Order: {{e}}")
        else:
            print("  Order & Limits button: MISSING")

        # 6. Logo test
        print("\\n--- LOGO TEST ---")
        test_logo(main_window)

        # 7. Window icon
        print(f"\\n--- WINDOW ICON ---")
        icon = main_window.windowIcon()
        if not icon.isNull():
            print(f"  Window icon: SET ({{icon.availableSizes()}})")
        else:
            print("  Window icon: NOT SET")

        app.quit()
        return 0
    return original_exec()

QApplication.exec = staticmethod(hooked_exec)

def find_button(window, text):
    from PySide6.QtWidgets import QPushButton
    for btn in window.findChildren(QPushButton):
        if btn.text() == text or text in btn.text() or btn.toolTip() == text:
            return btn
    return None

def get_connections(btn):
    try:
        receivers = btn.receivers(btn.clicked)
        return f"{{receivers}} receiver(s)"
    except:
        return "unknown"

def get_status_text(window):
    if hasattr(window, 'statusline'):
        return window.statusline.left.text()
    elif hasattr(window, 'set_status'):
        return "N/A (method exists)"
    from PySide6.QtWidgets import QLabel
    for lbl in window.findChildren(QLabel):
        if 'ready' in lbl.text().lower() or 'calculat' in lbl.text().lower() or 'found' in lbl.text().lower():
            return lbl.text()
    return "NOT FOUND"

def test_input_panel(window, app):
    from PySide6.QtWidgets import QLineEdit, QComboBox, QCheckBox, QSpinBox

    coils_combo = None
    for cb in window.findChildren(QComboBox):
        if 'coil' in cb.objectName().lower() or 'count' in cb.objectName().lower() or cb.count() >= 2:
            coils_combo = cb
            break

    if coils_combo:
        print(f"  Coils combo: found (count={{coils_combo.count()}})")
        print(f"  Current index: {{coils_combo.currentIndex()}}")
    else:
        print("  Coils combo: NOT FOUND")

    width_edit = None
    for le in window.findChildren(QLineEdit):
        if 'width' in le.objectName().lower() or le.width() >= 90:
            parent = le.parent()
            while parent:
                from PySide6.QtWidgets import QLabel
                for lbl in parent.findChildren(QLabel):
                    if 'width' in lbl.text().lower() and 'coil' in lbl.text().lower():
                        width_edit = le
                        break
                if width_edit:
                    break
                parent = parent.parent()
            if width_edit:
                break

    if width_edit:
        print(f"  Coil width edit: found (text='{{width_edit.text()}}')")
        QTest.keyClicks(width_edit, "1290")
        app.processEvents()
        print(f"  After typing: '{{width_edit.text()}}'")
    else:
        print("  Coil width edit: NOT FOUND")

    size_edits = []
    for le in window.findChildren(QLineEdit):
        if 'size' in le.objectName().lower() or 'strip' in le.objectName().lower():
            size_edits.append(le)

    print(f"  Size edits found: {{len(size_edits)}}")
    for i, ed in enumerate(size_edits):
        print(f"    Size {{i+1}}: text='{{ed.text()}}'")

    avg_edit = None
    for le in window.findChildren(QLineEdit):
        if 'avg' in le.objectName().lower() or 'average' in le.objectName().lower():
            avg_edit = le
            break

    if avg_edit:
        print(f"  Avg weight edit: found (text='{{avg_edit.text()}}', readOnly={{avg_edit.isReadOnly()}})")
    else:
        from PySide6.QtWidgets import QLabel
        for lbl in window.findChildren(QLabel):
            if 'avg' in lbl.text().lower() or 'average' in lbl.text().lower():
                print(f"  Avg weight label found: '{{lbl.text()}}'")
                break

    fit_meter = None
    for lbl in window.findChildren(QLabel):
        if 'fit' in lbl.text().lower() or 'strip' in lbl.text().lower() or 'mm' in lbl.text():
            if '/' in lbl.text() or 'mm' in lbl.text():
                fit_meter = lbl
                break

    if fit_meter:
        print(f"  Fit meter label: '{{fit_meter.text()}}'")
    else:
        print("  Fit meter: NOT FOUND")

    for cb in window.findChildren(QCheckBox):
        if 'least' in cb.text().lower() or 'each' in cb.text().lower():
            print(f"  Checkbox: '{{cb.text()}}' checked={{cb.isChecked()}}")

def test_logo(window):
    from PySide6.QtWidgets import QLabel
    for lbl in window.findChildren(QLabel):
        if lbl.pixmap() and not lbl.pixmap().isNull():
            pm = lbl.pixmap()
            print(f"  Logo pixmap found: {{pm.width()}}x{{pm.height()}}, devicePixelRatio={{pm.devicePixelRatio()}}")
            return
    print("  No logo pixmap found on any QLabel")

# Set up argv and run via the new app entry point
sys.argv = ['slitra_controller.py', '{window_type}']
app, window, controller = create_app_and_window()
window.showMaximized()
app.exec()
'''

    temp_script = os.path.join(project_root, f"temp_audit_{window_type.replace(' ', '_').replace('--', '')}.py")
    with open(temp_script, 'w') as f:
        f.write(test_script)

    try:
        proc = subprocess.Popen(
            [sys.executable, temp_script],
            cwd=project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        stdout, _ = proc.communicate(timeout=120)
        output = stdout.decode()
        with open(output_file, 'w') as f:
            f.write(output)
        print(output)
        return output
    finally:
        if os.path.exists(temp_script):
            os.unlink(temp_script)

# Run for old window
print("="*60)
print("TESTING OLD WINDOW (--old)")
print("="*60)
run_audit_for_window("--old", "parity_old.txt")

print("\n" + "="*60)
print("TESTING NEW WINDOW (--new)")
print("="*60)
run_audit_for_window("--new", "parity_new.txt")

print("\n=== PARITY AUDIT COMPLETE ===")