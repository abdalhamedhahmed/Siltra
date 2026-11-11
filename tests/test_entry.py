from PySide6.QtWidgets import QApplication
import sys
from slitra.slitra_window import MainWindow
from slitra.slitra_controller import SlitraController

app = QApplication.instance() or QApplication(sys.argv)
from slitra.slitra_window import MainWindow
from slitra.slitra_controller import SlitraController
w = MainWindow()
c = SlitraController(w)
print('coils_edit text:', repr(w.left.coils_edit.text()))
print('num_coils:', w.left._count())
w.deleteLater()