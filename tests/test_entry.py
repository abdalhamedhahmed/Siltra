from PySide6.QtWidgets import QApplication
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from slitra_window import MainWindow
from slitra_controller import SlitraController

app = QApplication.instance() or QApplication(sys.argv)
w = MainWindow()
c = SlitraController(w)
print('coils_edit text:', repr(w.left.coils_edit.text()))
print('num_coils:', w.left._count())
w.deleteLater()
