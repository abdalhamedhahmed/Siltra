#!/usr/bin/env python3
"""
Real Launch Harness - runs the app exactly as the user does using subprocess
"""
import sys
import os
import subprocess
import time

def run_real_app_via_subprocess():
    """Run the real app as a separate process and analyze it with PIL"""

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Launch the app as a subprocess with offscreen platform
    print("=== LAUNCHING REAL APP (python ui_qt.py) with offscreen ===")
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'

    test_script = r'''
import sys
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication, QPalette

# Add src to path so 'slitra' package imports work
sys.path.insert(0, r"{project_root}/src")
os.chdir(r"{project_root}")

# Import and run the actual app's main logic
from slitra_controller import create_app_and_window

# Override the exec to capture state after window creation
original_exec = QApplication.exec

captured = False

def hooked_exec(self):
    global captured
    if not captured:
        captured = True
        app = QApplication.instance()
        print("=== AFTER WINDOW CREATED ===")
        print("Style: " + app.style().objectName())
        if hasattr(QGuiApplication, 'styleHints'):
            hints = QGuiApplication.styleHints()
            if hasattr(hints, 'colorScheme'):
                cs = hints.colorScheme()
                scheme_str = "Dark" if cs == 2 else "Light" if cs == 1 else str(cs)
                print("ColorScheme: " + scheme_str)
        print("Stylesheet length: " + str(len(app.styleSheet())))
        print("Stylesheet preview: " + app.styleSheet()[:500])

        pal = app.palette()
        for role_name, role in [
            ('Window', QPalette.ColorRole.Window),
            ('WindowText', QPalette.ColorRole.WindowText),
            ('Base', QPalette.ColorRole.Base),
            ('Text', QPalette.ColorRole.Text),
            ('Button', QPalette.ColorRole.Button),
            ('ButtonText', QPalette.ColorRole.ButtonText),
            ('Highlight', QPalette.ColorRole.Highlight),
            ('HighlightedText', QPalette.ColorRole.HighlightedText),
        ]:
            color = pal.color(role)
            print("  " + role_name + ": #" + "{:02x}{:02x}{:02x}".format(color.red(), color.green(), color.blue()))

        # Find main window
        for w in app.topLevelWidgets():
            if w.isVisible():
                print("Main window: " + w.__class__.__name__)
                w.show()
                break

        # Now check widget palettes
        from PySide6.QtWidgets import QLabel, QLineEdit, QComboBox, QCheckBox
        main_window = None
        for w in app.topLevelWidgets():
            if w.isVisible() and w.__class__.__name__ in ('MainWindow', 'CoilSlittingCalculator'):
                main_window = w
                break

        if main_window:
            def get_palette_roles(widget, name):
                pal = widget.palette()
                roles = {}
                for role_name, role in [
                    ('Window', QPalette.ColorRole.Window),
                    ('WindowText', QPalette.ColorRole.WindowText),
                    ('Base', QPalette.ColorRole.Base),
                    ('Text', QPalette.ColorRole.Text),
                    ('Button', QPalette.ColorRole.Button),
                    ('ButtonText', QPalette.ColorRole.ButtonText),
                    ('Highlight', QPalette.ColorRole.Highlight),
                    ('HighlightedText', QPalette.ColorRole.HighlightedText),
                ]:
                    color = pal.color(role)
                    roles[role_name] = "#" + "{:02x}{:02x}{:02x}".format(color.red(), color.green(), color.blue())
                stylesheet = widget.styleSheet()
                ancestors = []
                w2 = widget
                while w2:
                    if w2.styleSheet():
                        ancestors.append(w2.__class__.__name__ + ": " + w2.styleSheet()[:200])
                    w2 = w2.parent()
                return {
                    'palette': roles,
                    'stylesheet': stylesheet[:500] if stylesheet else '',
                    'ancestors_with_stylesheet': ancestors[:5]
                }

            # Find key widgets
            coil_width_label = None
            coil_width_edit = None
            num_coils_combo = None
            at_least_once_checkbox = None

            for child in main_window.findChildren(QLabel):
                if "Coil width" in child.text() and "mm" in child.text():
                    coil_width_label = child
                    break

            for child in main_window.findChildren(QLineEdit):
                if child.width() >= 90 and child.width() <= 110:
                    parent = child.parent()
                    while parent:
                        for lbl in parent.findChildren(QLabel):
                            if "Coil width" in lbl.text():
                                coil_width_edit = child
                                break
                        if coil_width_edit:
                            break
                        parent = parent.parent()
                    if coil_width_edit:
                        break

            for child in main_window.findChildren(QComboBox):
                if "coils" in child.objectName().lower() or child.count() >= 3:
                    num_coils_combo = child
                    break

            for child in main_window.findChildren(QCheckBox):
                if "least one" in child.text() or "each size" in child.text():
                    at_least_once_checkbox = child
                    break

            print("=== WIDGET PALETTES ===")
            widgets_to_check = [
                ("Coil width label", coil_width_label),
                ("Coil width edit", coil_width_edit),
                ("Num coils combo", num_coils_combo),
                ("Checkbox", at_least_once_checkbox),
            ]

            for name, widget in widgets_to_check:
                if widget:
                    info = get_palette_roles(widget, name)
                    print("\n" + name + ":")
                    print("  Palette: " + str(info['palette']))
                    if info['stylesheet']:
                        print("  StyleSheet: " + info['stylesheet'])
                    if info['ancestors_with_stylesheet']:
                        print("  Ancestors with stylesheet:")
                        for a in info['ancestors_with_stylesheet']:
                            print("    " + a)

        app.quit()
        return 0
    return original_exec(self)

QApplication.exec = staticmethod(hooked_exec)

# Run the actual main BUT we need to prevent it from creating its own QApplication
# Let's just call the window creation directly
from slitra_window import MainWindow as SlitraWindow
from PySide6.QtGui import QFont

# Create window directly (ui_qt.main creates QApplication internally)
window = SlitraWindow()
window.showMaximized()

# The hooked_exec will be called when we call app.exec()
app.exec()
'''

    # Write temp script
    temp_script = os.path.join(project_root, "temp_check_palette.py")
    with open(temp_script, 'w') as f:
        f.write(test_script)

    try:
        proc = subprocess.Popen(
            [sys.executable, "temp_check_palette.py"],
            cwd=project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = proc.communicate(timeout=60)
        print("STDOUT:")
        print(stdout.decode())
        if stderr:
            print("STDERR:")
            print(stderr.decode())
    finally:
        if os.path.exists(temp_script):
            os.unlink(temp_script)

    return {}


if __name__ == "__main__":
    run_real_app_via_subprocess()