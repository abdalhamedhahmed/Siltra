#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
slitra_window.py - Slitra v4.1.1 main window (ZAT AL-EMAD FACTORY)

This is the PRODUCTION window. It contains only the UI layout and widgets.
All calculation, export, and business logic live in slitra_controller.py.
The controller connects to this window's signals and calls its display methods.

Run (needs PySide6):
    python slitra_window.py              opens maximized, empty startup state
    python slitra_window.py --check      layout self-check at 4 sizes x 2 states,
                                         saves screenshots to skeleton_screenshots/
"""
import argparse
import os
import re
import statistics
import sys
import time

from PySide6.QtCore import (QLocale, QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal,
                            QAbstractTableModel, QModelIndex)
from PySide6.QtGui import (QBrush, QColor, QDoubleValidator, QFont, QFontDatabase,
                           QFontMetrics, QGuiApplication, QIntValidator,
                           QPainter, QPainterPath, QPalette, QPen,
                           QPixmap, QShortcut, QKeySequence)
from PySide6.QtWidgets import (QAbstractItemDelegate, QAbstractItemView, QApplication, QCheckBox,
                               QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMainWindow,
                               QPushButton, QSizePolicy, QSpinBox, QStyledItemDelegate,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget, QScrollArea, QTableView, QMenu)
from array import array

# Make 'slitra' importable as a top-level package regardless of CWD,
# since the package lives at src/slitra/ but imports use 'from slitra import ...'.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------- import app info
from app_info import APP_NAME, FACTORY_NAME, APP_VERSION as VERSION, MAX_COILS, HISTORY_KEEP, HISTORY_MAX_BYTES

# ---------------------------------------------------------------- colors (fixed hex, light mode only)
RED = "#D32F2F"
INK = "#1F2933"
MUTED = "#5B6775"
LINE = "#D5DAE1"
WINDOW_BG = "#F2F4F7"
GREEN = "#2E7D32"
BAD = "#C62828"
GREY = "#6B7280"
SCRAP_RED = "#E24B4A"
BLUE = "#3E7CB1"
SIZE_COLORS = ["#EF9F27", "#85B7EB", "#97C459", "#AFA9EC", "#ED93B1", "#5DCAA5", "#F0997B"]


def size_color(index):
    """ONE shared color per strip-size POSITION (not width). Used by bar, legend and table."""
    return QColor(SIZE_COLORS[index % len(SIZE_COLORS)])


# ---------------------------------------------------------------- utilities for coil weights
READONLY_QSS = ("QLineEdit{background:#F2F4F7;border:1px solid %s;border-radius:3px;"
                "padding:0 4px;color:%s;}" % (LINE, INK))


def parse_weight(text):
    try:
        v = float(str(text).strip())
    except ValueError:
        return None
    return v if v > 0 else None


def fmt_weight(v):
    return ("%.3f" % v).rstrip("0").rstrip(".")


def parse_pasted_numbers(text):
    """Split pasted text (Excel column, a row, or a list) into number strings."""
    out = []
    for tok in re.split(r"[\s;]+", text.strip()):
        if not tok:
            continue
        if re.match(r"^\d{1,3}(,\d{3})+(\.\d+)?$", tok):      # 10,000 -> 10000
            out.append(tok.replace(",", ""))
        else:
            out.extend(p for p in tok.split(",") if p)
    return out


# ---------------------------------------------------------------- fonts
FONT_FAMILIES = ["Segoe UI", "Arial", "Sans Serif"]


def make_font(pt, weight=QFont.Weight.Normal):
    f = QFont()
    f.setFamilies(FONT_FAMILIES)
    f.setPointSizeF(pt)
    f.setWeight(weight)
    return f


def mk_label(text, pt=9.0, color=None, weight=QFont.Weight.Normal):
    lab = QLabel(text)
    lab.setFont(make_font(pt, weight))
    if color:
        lab.setStyleSheet("color:%s;" % color)
    return lab


# ---------------------------------------------------------------- navigation button style
NAV_QSS = ("QPushButton{background:#FFFFFF;color:%s;border:1px solid #AEB7C2;border-radius:4px;padding:0;}"
           "QPushButton:hover{background:#F2F4F7;}QPushButton:disabled{color:#B8C0CC;border-color:#DDE2E8;}" % INK)


from view_models import plan_vm, plan_text
from state import MemoryStore


class CompareDialog(QDialog):
    """Up to four combinations side by side: strip bars, every number, the difference to A, the best value tinted."""
    METRICS = [("Used width (mm)", "used", "int", +1), ("Scrap (mm)", "scrap", "int", -1),
               ("Scrap (%)", "pct", "f2", -1), ("Total strips per coil", "strips", "int", 0),
               ("Scrap per coil (kg)", "scrap_per", "f2", -1), ("Scrap total (kg)", "scrap_total", "f2", -1)]
    BETTER = "#E3F2E5"
    TAGS = "ABCD"

    def __init__(self, parent, entries, picks):
        """entries: list of (label, plan); picks: four entry indexes (None = nothing in that slot)."""
        super().__init__(parent)
        self.setWindowTitle("Compare Formulas")
        self.setModal(True)
        self.setStyleSheet("QDialog{background:%s;}" % WINDOW_BG)
        self.setMinimumSize(640, 480)
        self.resize(900, 680)
        self.entries = entries
        self.cleared = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(6)
        outer.addWidget(SectionTitle("Compare Formulas (up to 4)"))
        self.combos, self.bars = [], []
        for t in range(4):
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(mk_label(self.TAGS[t], 11, INK, QFont.Weight.DemiBold))
            combo = QComboBox()
            if t >= 2:
                combo.addItem("(none)")
            for label, _vm in entries:
                combo.addItem(label)
            combo.setFont(make_font(9))
            combo.setFixedHeight(26)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(20)
            row.addWidget(combo, 1)
            bar = StripBar()
            bar.setFixedHeight(24)
            self.combos.append(combo)
            self.bars.append(bar)
            outer.addLayout(row)
            outer.addWidget(bar)
        for t, pick in enumerate(picks[:4]):
            self.combos[t].setCurrentIndex((0 if pick is None else pick + 1) if t >= 2 else (pick or 0))
        self.verdict = mk_label("", 10, INK, QFont.Weight.DemiBold)
        self.verdict.setWordWrap(True)
        outer.addWidget(self.verdict)
        self.table = QTableWidget(0, 3)
        base_table(self.table, 28, 24)
        outer.addWidget(self.table, 1)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.swap_btn = QPushButton("Swap A / B")
        self.clear_btn = QPushButton("Clear memory")
        self.close_btn = QPushButton("Close")
        for b, qss in ((self.swap_btn, OUTLINE_QSS), (self.clear_btn, OUTLINE_QSS), (self.close_btn, PRIMARY_QSS)):
            b.setFixedHeight(32)
            b.setMinimumWidth(96)
            b.setFont(make_font(9, QFont.Weight.Medium))
            b.setStyleSheet(qss)
            b.setAutoDefault(False)
        btns.addWidget(self.swap_btn)
        btns.addWidget(self.clear_btn)
        btns.addStretch(1)
        btns.addWidget(self.close_btn)
        outer.addLayout(btns)
        for c in self.combos:
            c.currentIndexChanged.connect(self._refresh)
        self.swap_btn.clicked.connect(self._swap)
        self.clear_btn.clicked.connect(self._clear)
        self.close_btn.clicked.connect(self.accept)
        self._refresh()

    def _vm(self, t):
        i = self.combos[t].currentIndex()
        if t >= 2:
            return None if i == 0 else self.entries[i - 1][1]
        return self.entries[i][1]

    def _swap(self):
        a, b = self.combos[0].currentIndex(), self.combos[1].currentIndex()
        for c in self.combos[:2]:
            c.blockSignals(True)
        self.combos[0].setCurrentIndex(b)
        self.combos[1].setCurrentIndex(a)
        for c in self.combos[:2]:
            c.blockSignals(False)
        self._refresh()

    def _clear(self):
        self.cleared = True
        self.accept()

    @staticmethod
    def _fmt(v, kind):
        return "%d" % v if kind == "int" else "%.2f" % v

    @staticmethod
    def _delta(a, b, kind):
        d = b - a
        if (kind == "int" and d == 0) or (kind != "int" and abs(d) < 0.005):
            return ""
        return ("%+d" % d) if kind == "int" else ("%+.2f" % d)

    @staticmethod
    def _same(x, y):
        return x["sizes"] == y["sizes"] and x["qty"] == y["qty"] and x["width"] == y["width"]

    def _refresh(self):
        vms = [self._vm(t) for t in range(4)]
        shown = [t for t, v in enumerate(vms) if v is not None]
        for t in range(4):
            self.bars[t].setVisible(vms[t] is not None)
            self.bars[t].set_vm(vms[t])
        self.table.setColumnCount(1 + len(shown))
        self.table.setHorizontalHeaderLabels([""] + [self.TAGS[t] for t in shown])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(0, 200)
        rows = [(lab, [v[key] for v in (vms[t] for t in shown)], kind, d) for lab, key, kind, d in self.METRICS]
        per = [dict(zip(vms[t]["sizes"], vms[t]["qty"])) for t in shown]
        sizes = sorted(set().union(*[set(x) for x in per])) if per else []
        for sz in sizes:
            rows.append(("Qty of %d mm per coil" % sz, [x.get(sz, 0) for x in per], "int", 0))
        self.table.setRowCount(len(rows))
        bold = make_font(9, QFont.Weight.DemiBold)
        for r, (lab, vals, kind, d) in enumerate(rows):
            it = QTableWidgetItem(lab)
            it.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(r, 0, it)
            best = None
            if d and len(vals) > 1 and len(set(vals)) > 1:
                best = max(vals) if d > 0 else min(vals)
            for k, v in enumerate(vals):
                text = self._fmt(v, kind)
                if k > 0:
                    dl = self._delta(vals[0], v, kind)
                    text += ("  (%s)" % dl) if dl else ""
                cell = QTableWidgetItem(text)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                cell.setFlags(Qt.ItemFlag.ItemIsEnabled)
                if best is not None and v == best:
                    cell.setBackground(QBrush(QColor(self.BETTER)))
                    cell.setFont(bold)
                self.table.setItem(r, 1 + k, cell)
        if len(shown) < 2:
            self.verdict.setText("Pick at least two formulas to compare.")
        elif all(self._same(vms[shown[0]], vms[t]) for t in shown[1:]):
            self.verdict.setText("The formulas you picked are the same combination. Pick different ones.")
        else:
            tot = [vms[t]["scrap_total"] for t in shown]
            low = min(tot)
            winners = [self.TAGS[t] for t, x in zip(shown, tot) if abs(x - low) < 0.005]
            others = ["%s +%.2f kg" % (self.TAGS[t], x - low) for t, x in zip(shown, tot) if abs(x - low) >= 0.005]
            head = ("%s leaves the least scrap: %.2f kg in total (%.2f%%)." % (
                " and ".join(winners), low, vms[shown[tot.index(low)]]["pct"]))
            self.verdict.setText(head + ("   " + ",  ".join(others) if others else "   All leave the same scrap."))

    def values(self):
        """Every table row as a tuple of texts, for tests."""
        return [tuple(self.table.item(r, c).text() for c in range(self.table.columnCount())) for r in range(self.table.rowCount())]


# ---------------------------------------------------------------- virtual table model for results (no limit, compact arrays)
class ResultsModel(QAbstractTableModel):
    """Virtual table: holds ALL combinations in compact arrays (no limit), builds cell text on demand."""
    TAIL = ["Used\nwidth", "Scrap\nmm", "Scrap\n%", "Total\nstrips"]

    def __init__(self):
        super().__init__()
        self._bold = make_font(9, QFont.Weight.DemiBold)
        self._init_empty()

    def _init_empty(self):
        self.width = 0
        self.sizes = []
        self.n = 0
        self.qty = []                 # one array('i') per size, in rank order (least scrap first)
        self.scrap = array("i")
        self.strips = array("i")
        self.order = []               # display order: indexes into the arrays
        self.sort_col = None
        self.sort_desc = False
        self.pinned = set()           # original indexes pinned into memory
        self.visible = None           # original indexes that pass the filter (None = no filter)

    def clear(self):
        self.beginResetModel()
        self._init_empty()
        self.endResetModel()

    def load(self, width, sizes, rows):
        """rows: list of (scrap, qty tuple), already in rank order (least scrap first)."""
        self.beginResetModel()
        self.width = width
        self.sizes = list(sizes)
        self.qty = [array("i", [r[1][i] for r in rows]) for i in range(len(sizes))]
        self.scrap = array("d", [r[0] for r in rows])
        self.strips = array("i", [sum(r[1]) for r in rows])
        self.n = len(rows)
        self.order = list(range(self.n))
        self.sort_col = None
        self.sort_desc = False
        self.pinned = set()
        self.visible = None
        self.endResetModel()

    def load_arrays(self, width, sizes, qty, scrap, strips):
        """Restore a stored result without searching again (the arrays are shared, not copied)."""
        self.beginResetModel()
        self.width = width
        self.sizes = list(sizes)
        self.qty, self.scrap, self.strips = qty, scrap, strips
        self.n = len(scrap)
        self.order = list(range(self.n))
        self.sort_col = None
        self.sort_desc = False
        self.pinned = set()
        self.visible = None
        self.endResetModel()

    def snapshot(self):
        return dict(width=self.width, sizes=list(self.sizes), qty=self.qty, scrap=self.scrap,
                    strips=self.strips, n=self.n)

    @property
    def shown(self):
        return len(self.order)

    def _base(self):
        return self.visible if self.visible is not None else range(self.n)

    def matching(self, f):
        """Original indexes that pass the filter f, or None when f has no condition."""
        cand = None

        def narrow(arr, lo, hi):
            nonlocal cand
            if lo is None and hi is None:
                return
            rng = cand if cand is not None else range(self.n)
            if lo is not None and hi is not None:
                cand = [i for i in rng if lo <= arr[i] <= hi]
            elif lo is not None:
                cand = [i for i in rng if arr[i] >= lo]
            else:
                cand = [i for i in rng if arr[i] <= hi]

        for i, (lo, hi) in enumerate(f.get("qty", [])):
            if i < len(self.qty):
                narrow(self.qty[i], lo, hi)
        narrow(self.strips, *f.get("strips", (None, None)))
        narrow(self.scrap, *f.get("scrap", (None, None)))
        return cand

    def apply_filter(self, f):
        cand = self.matching(f)
        self.beginResetModel()
        self.visible = cand
        self.order = list(cand) if cand is not None else list(range(self.n))
        self.sort_col = None
        self.sort_desc = False
        self.endResetModel()
        return len(self.order)

    def clear_filter(self):
        return self.apply_filter({})

    def set_pinned(self, src, on):
        (self.pinned.add if on else self.pinned.discard)(src)
        if self.n:
            self.dataChanged.emit(self.index(0, 0), self.index(self.n - 1, 0))

    def plan_src(self, src):
        return self.scrap[src], tuple(a[src] for a in self.qty)

    # -- model interface
    def _ncols(self):
        return 1 + len(self.sizes) + 4 if self.sizes else 5

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self.shown

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self._ncols()

    def labels(self):
        return ["Formula"] + ["Qty\n%dmm" % s for s in self.sizes] + self.TAIL

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        labels = self.labels()
        if section >= len(labels):
            return None
        text = labels[section]
        if self.sort_col == section:
            text += " " + ("\\u25BC" if self.sort_desc else "\\u25B2")
        return text

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r = self.order[index.row()]
        c = index.column()
        k = len(self.sizes)
        if role == Qt.ItemDataRole.DisplayRole:
            if c == 0:
                txt = "F%d" % (r + 1)
                return ("★ " + txt) if r in self.pinned else txt
            if c <= k:
                return str(self.qty[c - 1][r])
            scrap = self.scrap[r]
            if c == k + 1:
                return str(self.width - scrap)
            if c == k + 2:
                return str(scrap)
            if c == k + 3:
                return "%.2f" % (scrap / self.width * 100)
            return str(self.strips[r])
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter
        if role == Qt.ItemDataRole.BackgroundRole and r == 0:
            return QBrush(QColor("#E3F2E5"))
        if role == Qt.ItemDataRole.FontRole and r == 0:
            return self._bold
        return None

    # -- sorting (click on a header)
    def sort_by(self, col):
        k = len(self.sizes)
        if self.n == 0 or col >= self._ncols():
            return
        if col == self.sort_col:
            desc = not self.sort_desc
        else:
            desc = (1 <= col <= k) or col in (k + 1, k + 4)     # first click: most / largest first
        if col == 0:
            order = list(range(self.n))
            if desc:
                order.reverse()
        else:
            if col <= k:
                arr, rev = self.qty[col - 1], desc
            elif col == k + 1:
                arr, rev = self.scrap, not desc                  # used width = coil width - scrap
            elif col in (k + 2, k + 3):
                arr, rev = self.scrap, desc
            else:
                arr, rev = self.strips, desc
            order = sorted(range(self.n), key=arr.__getitem__, reverse=rev)   # stable: ties keep rank order
        self.beginResetModel()
        self.order = order
        self.sort_col = col
        self.sort_desc = desc
        self.endResetModel()

    def sort_text(self):
        if self.sort_col is None or self.n == 0:
            return "formula number (least scrap first)"
        name = self.labels()[self.sort_col].replace("\n", " ")
        k = len(self.sizes)
        if self.sort_col == 0:
            return "formula number, %s" % ("last first" if self.sort_desc else "first")
        if self.sort_col in (k + 2, k + 3):
            return "%s, %s" % (name, "most first" if self.sort_desc else "least first")
        return "%s, %s" % (name, "most first" if self.sort_desc else "least first")

    def row_plan(self, view_row):
        src = self.order[view_row]
        return self.scrap[src], tuple(a[src] for a in self.qty), src + 1      # scrap, qty, original rank


class ResultsView(QTableView):
    rowChosen = Signal(int)

    def __init__(self):
        super().__init__()
        self.results = ResultsModel()
        self.setModel(self.results)
        base_table(self, 34, 24)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setMinimumHeight(34 + 5 * 24 + 2)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        hh = self.horizontalHeader()
        hh.setSectionsClickable(True)
        hh.setHighlightSections(False)
        hh.setToolTip("Click a column title to sort. Click again to reverse.")
        hh.sectionClicked.connect(self._header_clicked)
        self.results.modelReset.connect(self._stretch)
        self.notice = EmptyNotice()
        lay = QVBoxLayout(self.viewport())
        lay.setContentsMargins(24, 0, 24, 0)
        lay.addStretch(2)
        lay.addWidget(self.notice, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(3)
        self.notice.hide()
        self.selectionModel().currentRowChanged.connect(lambda cur, _p: self.rowChosen.emit(cur.row()) if cur.isValid() else None)
        self._stretch()

    def _stretch(self):
        hh = self.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(0, 92)

    def _header_clicked(self, col):
        big = self.results.n > 150000
        cur = self.currentIndex().row()
        src = self.results.order[cur] if 0 <= cur < len(self.results.order) else None
        if big:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.results.sort_by(col)
        finally:
            if big:
                QApplication.restoreOverrideCursor()
        if src is None:
            self.scrollToTop()
        else:
            self.select_row(self.results.order.index(src))        # the chosen formula stays chosen

    def select_row(self, view_row):
        n = self.results.n
        if n == 0:
            return
        view_row = max(0, min(n - 1, view_row))
        idx = self.results.index(view_row, 0)
        self.setCurrentIndex(idx)
        self.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter if view_row else QAbstractItemView.ScrollHint.PositionAtTop)
        self.rowChosen.emit(view_row)

    def keyPressEvent(self, e):
        key = e.key()
        n = self.results.n
        if n == 0:
            super().keyPressEvent(e)
            return
        curr = self.currentIndex().row()
        if key == Qt.Key.Key_Up:
            self.select_row(max(0, curr - 1))
        elif key == Qt.Key.Key_Down:
            self.select_row(min(n - 1, curr + 1))
        elif key == Qt.Key.Key_PageUp:
            self.select_row(max(0, curr - 10))
        elif key == Qt.Key.Key_PageDown:
            self.select_row(min(n - 1, curr + 10))
        elif key == Qt.Key.Key_Home:
            self.select_row(0)
        elif key == Qt.Key.Key_End:
            self.select_row(n - 1)
        else:
            super().keyPressEvent(e)


class EmptyNotice(QWidget):
    """Centered message in an empty Results table, with an optional one-click fix."""
    actionClicked = Signal(str, int)

    def __init__(self):
        super().__init__()
        self.setMinimumWidth(420)
        self.setMaximumWidth(560)
        self._key, self._value = "", 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.title = mk_label("", 10, INK, QFont.Weight.DemiBold)
        self.title.setWordWrap(True)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body = mk_label("", 9, MUTED)
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.button = QPushButton("")
        self.button.setFixedHeight(28)
        self.button.setMinimumWidth(190)
        self.button.setFont(make_font(9, QFont.Weight.Medium))
        self.button.setStyleSheet(PRIMARY_QSS)
        self.button.setAutoDefault(False)
        self.button.clicked.connect(lambda: self.actionClicked.emit(self._key, self._value))
        lay.addWidget(self.title)
        lay.addWidget(self.body)
        lay.addWidget(self.button, 0, Qt.AlignmentFlag.AlignHCenter)

    def show_info(self, title, body, button=None, key="", value=0):
        self.title.setText(title)
        self.body.setText(body)
        self._key, self._value = key, value
        self.button.setVisible(bool(button))
        self.button.setText(button or "")
        # wrapped labels do not report their real height to a plain layout: reserve it for the narrowest case
        w = self.minimumWidth()
        need = self.title.heightForWidth(w) + self.body.heightForWidth(w) + (28 + 6 if button else 0) + 6
        self.setMinimumHeight(need)
        self.show()


def explain_no_plan(cfg):
    """Why no combination was found, and the nearest setting that would give one."""
    width, sizes, smin, smax, every = cfg["width"], cfg["sizes"], cfg["smin"], cfg["smax"], cfg["every"]
    if smin > smax:
        return dict(title="The scrap range is the wrong way round",
                    body="The minimum scrap (%d mm) is larger than the maximum (%d mm)." % (smin, smax))
    mandatory = sum(sizes) if every else 0
    if every and mandatory > width:
        return dict(title="The sizes do not fit on the coil",
                    body="One strip of each size needs %d mm, but the coil is only %d mm wide. Remove a size, "
                         "use a wider coil, or turn off 'At least one of each size'." % (mandatory, width))
    mask = (1 << (width + 1)) - 1
    reach = (1 << mandatory) & mask if every else 1
    for sz in sizes:
        acc, cur = reach, reach
        while True:
            cur = (cur << sz) & mask
            if (acc | cur) == acc:
                break
            acc |= cur
        reach = acc
    scraps = [width - u for u in range(width + 1) if (reach >> u) & 1]
    above = [x for x in scraps if x > smax]
    below = [x for x in scraps if x < smin]
    if above:
        a = min(above)
        body = "No combination leaves between %d and %d mm of scrap. The smallest scrap above your range is %d mm." % (smin, smax, a)
        if below:
            body += " The closest below your range is %d mm." % max(below)
        return dict(title="No combination fits this scrap range", body=body,
                    button="Set scrap maximum to %d mm" % a, key="scrap_max", value=a)
    if below:
        b = max(below)
        return dict(title="Every combination leaves less scrap than your minimum",
                    body="No combination leaves between %d and %d mm. The closest below your minimum is %d mm." % (smin, smax, b),
                    button="Set scrap minimum to %d mm" % b, key="scrap_min", value=b)
    return dict(title="No combination found", body="Check the coil width and the strip sizes.")


class FilterDialog(QDialog):
    """Show only the combinations that match: at least / at most of each size, strips and scrap."""

    def __init__(self, parent, model, current):
        super().__init__(parent)
        self.setWindowTitle("Filter Results")
        self.setModal(True)
        self.setStyleSheet("QDialog{background:%s;}" % WINDOW_BG)
        self.setMinimumSize(430, 380)
        self.model = model
        self._result = None
        self._cleared = False
        sizes = model.sizes
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)
        outer.addWidget(SectionTitle("Filter Results"))
        hint = mk_label("Leave a box empty for no limit. Only combinations that match every box are shown.", 8.5, MUTED)
        hint.setWordWrap(True)
        outer.addWidget(hint)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(0, 1)
        for c, t in ((1, "At least"), (2, "At most")):
            grid.addWidget(mk_label(t, 8.5, MUTED, QFont.Weight.Medium), 0, c, Qt.AlignmentFlag.AlignCenter)
        self.edits = {}
        rows = [("qty%d" % i, "Strips of %d mm (per coil)" % sz) for i, sz in enumerate(sizes)]
        rows += [("strips", "Total strips (per coil)"), ("scrap", "Scrap (mm)")]
        cur = current or {}
        for r, (key, label) in enumerate(rows, start=1):
            grid.addWidget(mk_label(label), r, 0)
            lo_hi = []
            for c in (1, 2):
                ed = style_edit(QLineEdit(), 80)
                ed.setValidator(QIntValidator(0, 10000000, self))
                grid.addWidget(ed, r, c)
                lo_hi.append(ed)
            self.edits[key] = tuple(lo_hi)
            if key.startswith("qty"):
                v = cur.get("qty", [])[int(key[3:])] if len(cur.get("qty", [])) > int(key[3:]) else (None, None)
            else:
                v = cur.get(key, (None, None))
            for ed, val in zip(lo_hi, v):
                ed.setText("" if val is None else str(val))
            for ed in lo_hi:
                ed.textChanged.connect(self._changed)
        outer.addLayout(grid)
        self.preview = mk_label("", 10, INK, QFont.Weight.DemiBold)
        self.preview.setWordWrap(True)
        self.msg = ElidedLabel("")
        self.msg.set_color(BAD)
        outer.addWidget(self.preview)
        outer.addWidget(self.msg)
        outer.addStretch(1)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.clear_btn = QPushButton("Clear filter")
        self.cancel_btn = QPushButton("Cancel")
        self.apply_btn = QPushButton("Apply")
        for b, qss in ((self.clear_btn, OUTLINE_QSS), (self.cancel_btn, OUTLINE_QSS), (self.apply_btn, PRIMARY_QSS)):
            b.setFixedHeight(32)
            b.setMinimumWidth(92)
            b.setFont(make_font(9, QFont.Weight.Medium))
            b.setStyleSheet(qss)
            b.setAutoDefault(False)
        btns.addWidget(self.clear_btn)
        btns.addStretch(1)
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.apply_btn)
        outer.addLayout(btns)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._update_preview)
        self.clear_btn.clicked.connect(self._clear)
        self.cancel_btn.clicked.connect(self.reject)
        self.apply_btn.clicked.connect(self._apply)
        self._update_preview()

    @staticmethod
    def _num(ed):
        t = ed.text().strip()
        return int(t) if t.isdigit() else None

    def build(self):
        """The filter as a dict, or the text of the first mistake."""
        f = {"qty": []}
        for key, (lo_e, hi_e) in self.edits.items():
            lo, hi = self._num(lo_e), self._num(hi_e)
            if lo is not None and hi is not None and lo > hi:
                return None, "'At least' is larger than 'At most' in one row."
            if key.startswith("qty"):
                f["qty"].append((lo, hi))
            else:
                f[key] = (lo, hi)
        return f, ""

    def _changed(self, _t=None):
        self._timer.start()

    def _update_preview(self):
        f, err = self.build()
        n = self.model.n
        self.msg.set_full(err)
        if err:
            self.preview.setText("")
            return
        if n > 300000 and any(v != (None, None) for v in ([x for x in f["qty"]] + [f["strips"], f["scrap"]])):
            self.preview.setText("{:,} combinations. Press Apply to filter them.".format(n))
            self.preview.setStyleSheet("color:%s;" % INK)
            return
        cand = self.model.matching(f)
        m = n if cand is None else len(cand)
        self.preview.setText("Matches {:,} of {:,} combinations".format(m, n) if m else "No combination matches these limits.")
        self.preview.setStyleSheet("color:%s;" % (INK if m else BAD))

    def _clear(self):
        self._cleared = True
        self.accept()

    def _apply(self):
        f, err = self.build()
        if err:
            self.msg.set_full(err)
            return
        self._result = f
        self.accept()

    def filter(self):
        """None when the filter was cleared (or has no condition), else the filter dict."""
        if self._cleared or self._result is None:
            return None
        has = any(v != (None, None) for v in (self._result["qty"] + [self._result["strips"], self._result["scrap"]]))
        return self._result if has else None


class ResultsHistory:
    """The last few results, kept in memory so you can go back to them without searching again."""

    def __init__(self):
        self.items = []                      # newest first

    @staticmethod
    def bytes_of(e):
        return e["n"] * (len(e["sizes"]) + 2) * 4

    def total_bytes(self):
        return sum(self.bytes_of(e) for e in self.items)

    def push(self, entry):
        self.items.insert(0, entry)
        while len(self.items) > HISTORY_KEEP or (self.total_bytes() > HISTORY_MAX_BYTES and len(self.items) > 1):
            self.items.pop()

    def label(self, e):
        c = e["cfg"]
        return "{}   |   {} coil{}, {} mm   |   {}   |   scrap {}-{}   |   {:,} combinations".format(
            e["when"], c["coils"], "" if c["coils"] == 1 else "s", c["width"],
            "/".join(str(x) for x in e["sizes"]), c["smin"], c["smax"], e["n"])


# ---------------------------------------------------------------- import app info
from app_info import APP_NAME, FACTORY_NAME, APP_VERSION as VERSION, MAX_COILS, HISTORY_KEEP, HISTORY_MAX_BYTES


# ---------------------------------------------------------------- small painted widgets
class SectionTitle(QWidget):
    def __init__(self, text):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        bar = QFrame()
        bar.setFixedSize(3, 16)
        bar.setStyleSheet("background:%s;border:none;" % RED)
        lay.addWidget(bar)
        lay.addWidget(mk_label(text, 10.5, INK, QFont.Weight.DemiBold))
        lay.addStretch(1)


class StripBar(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.vm = None

    def set_vm(self, vm):
        self.vm = vm
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        clip = QPainterPath()
        clip.addRoundedRect(r, 4, 4)
        p.setClipPath(clip)
        p.fillRect(self.rect(), QColor("#ECEFF3"))
        vm = self.vm
        if vm:
            p.setFont(make_font(8.5, QFont.Weight.Medium))
            fm = QFontMetrics(p.font())
            scale = r.width() / vm["width"]
            x = 0.0
            for i, (s, q) in enumerate(zip(vm["sizes"], vm["qty"])):
                for _ in range(q):
                    w = s * scale
                    seg = QRectF(x, 0, w, self.height())
                    p.fillRect(seg, size_color(i))
                    p.setPen(QPen(QColor("#FFFFFF"), 1))
                    p.drawLine(int(x), 0, int(x), self.height())
                    if w >= fm.horizontalAdvance(str(s)) + 6:
                        p.setPen(QColor(INK))
                        p.drawText(seg, Qt.AlignmentFlag.AlignCenter, str(s))
                    x += w
            if vm["scrap"] > 0:
                p.fillRect(QRectF(x, 0, vm["scrap"] * scale + 1, self.height()), QColor(SCRAP_RED))
        p.setClipping(False)
        p.setPen(QPen(QColor("#AEB7C2"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 4, 4)


class Ruler(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.vm = None

    def set_vm(self, vm):
        self.vm = vm
        self.update()

    def paintEvent(self, _e):
        if not self.vm:
            return
        vm = self.vm
        p = QPainter(self)
        p.setPen(QPen(QColor("#8A94A3"), 1))
        W = self.width() - 1
        scale = W / vm["width"]
        p.drawLine(0, 2, W, 2)
        p.drawLine(0, 0, 0, 7)
        p.drawLine(W, 0, W, 7)
        for k in vm["knives"]:
            x = int(k * scale)
            p.drawLine(x, 2, x, 5)
        p.setFont(make_font(8.5))
        p.setPen(QColor(MUTED))
        rect = QRect(0, 8, self.width(), self.height() - 8)
        p.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "0")
        p.drawText(rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(vm["width"]))
        p.drawText(rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   "Coil width %d mm" % vm["width"])


class Legend(QWidget):
    """Painted legend: solid rounded squares + text. Never a QLabel with HTML/stylesheet."""
    GAP = 16
    SQ = 12

    def __init__(self):
        super().__init__()
        self.items = []
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_vm(self, vm):
        self.items = []
        if vm:
            for i, (s, q) in enumerate(zip(vm["sizes"], vm["qty"])):
                self.items.append((size_color(i), "%d x %d" % (s, q)))
            if vm["scrap"] > 0:
                self.items.append((QColor(SCRAP_RED), "Scrap %d mm" % vm["scrap"]))
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        fm = QFontMetrics(make_font(8.5))
        if not self.items:
            return QSize(fm.horizontalAdvance("—") + 4, 22)
        w = sum(self.SQ + 6 + fm.horizontalAdvance(t) + self.GAP for _c, t in self.items) - self.GAP
        return QSize(w + 2, 22)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(make_font(8.5))
        fm = p.fontMetrics()
        if not self.items:
            p.setPen(QColor(MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "—")
            return
        x = 1
        cy = self.height() // 2
        for color, text in self.items:
            p.setPen(QPen(QColor(0, 0, 0, 50), 1))
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x + 0.5, cy - self.SQ / 2 + 0.5, self.SQ - 1, self.SQ - 1), 3, 3)
            p.setPen(QColor(INK))
            tw = fm.horizontalAdvance(text)
            p.drawText(QRect(x + self.SQ + 6, 0, tw + 2, self.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
            x += self.SQ + 6 + tw + self.GAP


class ElidedLabel(QLabel):
    """Single-line label that elides on the right; full text in the tooltip."""

    def __init__(self, text="", align=Qt.AlignmentFlag.AlignLeft):
        super().__init__()
        self.align = align
        self.setProperty("skip_text_check", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(22)
        self.setFont(make_font(8.5))
        self.full = ""
        self.color = MUTED
        self.set_full(text)

    def set_color(self, hexcolor):
        self.color = hexcolor
        self.update()

    def set_full(self, text):
        self.full = text
        self.setToolTip(text)
        self.update()

    def setText(self, text):
        self.set_full(text)

    def text(self):
        return self.full

    def minimumSizeHint(self):
        return QSize(0, 22)

    def sizeHint(self):
        return QSize(120, 22)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setFont(self.font())
        p.setPen(QColor(self.color))
        txt = p.fontMetrics().elidedText(self.full, Qt.TextElideMode.ElideRight, self.width())
        p.drawText(self.rect(), self.align | Qt.AlignmentFlag.AlignVCenter, txt)


class Badge(QWidget):
    STATES = {"none": ("NO CALCULATION", GREY), "pick": ("SELECT A FORMULA", GREY),
              "ok": ("WEIGHT CHECK OK", GREEN), "bad": ("WEIGHT MISMATCH", BAD)}

    def __init__(self):
        super().__init__()
        self.state = "none"
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_state(self, state):
        self.state = state
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        text = self.STATES[self.state][0]
        return QSize(QFontMetrics(make_font(8.5, QFont.Weight.DemiBold)).horizontalAdvance(text) + 22, 22)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, _e):
        text, color = self.STATES[self.state]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 5, 5)
        p.setFont(make_font(8.5, QFont.Weight.DemiBold))
        p.setPen(QColor("#FFFFFF"))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)


class FitMeter(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(6)
        self.used, self.total = 0, 0

    def set_values(self, used, total):
        self.used, self.total = used, total
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#E4E8EE"))
        p.drawRoundedRect(QRectF(0, 0, self.width(), 6), 3, 3)
        if self.total > 0 and self.used > 0:
            frac = min(1.0, self.used / self.total)
            p.setBrush(QColor(BAD if self.used > self.total else GREEN))
            p.drawRoundedRect(QRectF(0, 0, self.width() * frac, 6), 3, 3)


class Card(QFrame):
    def __init__(self, title, accent):
        super().__init__()
        self.setObjectName("Card")
        self.setMinimumHeight(60)
        self.setStyleSheet("#Card{background:#FFFFFF;border:1px solid %s;border-left:4px solid %s;"
                           "border-radius:4px;}" % (LINE, accent))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)
        lay.addStretch(1)
        self.title = mk_label(title, 8.5, MUTED)
        self.value = mk_label("—", 13, INK, QFont.Weight.DemiBold)
        lay.addWidget(self.title)
        lay.addWidget(self.value)
        lay.addStretch(1)

    def set_value(self, text):
        self.value.setText(text)


# ---------------------------------------------------------------- tables
HEADER_QSS = ("QHeaderView::section{background:#F2F4F7;color:%s;border:none;"
              "border-bottom:1px solid %s;border-right:1px solid #E4E8EE;padding:2px 4px;}" % (INK, LINE))
TABLE_QSS = "QTableWidget{background:#FFFFFF;border:1px solid %s;}" % LINE


class SwatchDelegate(QStyledItemDelegate):
    """Painted swatch (first column) + faint tint (~18%) of that size's color; a bold grey 'total' row."""

    def paint(self, painter, option, index):
        color = index.data(Qt.ItemDataRole.UserRole)
        total = index.data(Qt.ItemDataRole.UserRole + 1) == "total"
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if total:
            painter.fillRect(option.rect, QColor("#EEF1F5"))
        elif isinstance(color, QColor):
            tint = QColor(color)
            tint.setAlpha(46)
            painter.fillRect(option.rect, QColor("#FFFFFF"))
            painter.fillRect(option.rect, tint)
        else:
            painter.fillRect(option.rect, QColor("#FFFFFF"))
        rect = option.rect.adjusted(8, 0, -8, 0)
        align = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
        if index.column() == 0 and total:
            align = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        elif index.column() == 0 and isinstance(color, QColor):
            sw = QRect(option.rect.left() + 8, option.rect.center().y() - 6, 12, 12)
            painter.setPen(QPen(QColor(0, 0, 0, 50), 1))
            painter.setBrush(color)
            painter.drawRoundedRect(sw, 3, 3)
            rect = option.rect.adjusted(28, 0, -8, 0)
            align = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        painter.setPen(QColor(INK))
        f = QFont(option.font)
        if total:
            f.setBold(True)
        painter.setFont(f)
        painter.drawText(rect, align, str(index.data(Qt.ItemDataRole.DisplayRole) or ""))
        painter.setPen(QColor("#AEB7C2" if total else "#E4E8EE"))
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
        if total:
            painter.drawLine(option.rect.topLeft(), option.rect.topRight())
        painter.restore()


def base_table(table, header_height=34, row_height=24):
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    hh = table.horizontalHeader()
    hh.setFixedHeight(header_height)
    hh.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
    hh.setFont(make_font(8.5, QFont.Weight.Medium))
    hh.setStyleSheet(HEADER_QSS)
    table.setFont(make_font(9))
    table.setStyleSheet(TABLE_QSS)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.setShowGrid(False)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)


class StripTable(QTableWidget):
    HEADERS = ["Strip width\n(mm)", "Qty per\ncoil", "Total\nqty", "Weight/strip\n(kg)", "Total weight\n(kg)"]
    ROWS = 7
    HEIGHT = 30 + (ROWS + 1) * 20 + 2          # header + up to 7 sizes + the total row

    def __init__(self):
        super().__init__(0, 5)
        base_table(self, 30, 20)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setItemDelegate(SwatchDelegate(self))
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setFixedHeight(self.HEIGHT)   # worst case (7 sizes): never scrolls, never squeezed
        self.show_empty()

    def _put(self, r, c, text, color):
        it = QTableWidgetItem(text)
        if color is not None:
            it.setData(Qt.ItemDataRole.UserRole, color)
        self.setItem(r, c, it)

    def show_empty(self):
        self.setRowCount(1)
        for c in range(5):
            self._put(0, c, "—", None)

    def show_vm(self, vm):
        n = len(vm["sizes"])
        self.setRowCount(n + 1)
        for i, s in enumerate(vm["sizes"]):
            col = size_color(i)
            for c, text in enumerate([str(s), str(vm["qty"][i]), str(vm["total_qty"][i]),
                                      "%.2f" % vm["wps"][i], "%.2f" % vm["total_w"][i]]):
                self._put(i, c, text, col)
        for c, text in enumerate(["Total", str(sum(vm["qty"])), str(sum(vm["total_qty"])), "",
                                  "%.2f" % sum(vm["total_w"])]):
            it = QTableWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole + 1, "total")
            self.setItem(n, c, it)


# ---------------------------------------------------------------- input panel
EDIT_QSS = ("QLineEdit{background:#FFFFFF;border:1px solid #AEB7C2;border-radius:3px;padding:0 4px;}"
            "QLineEdit:focus{border:1px solid %s;}" % RED)
PANEL_QSS = "#Panel{background:#FFFFFF;border:1px solid %s;border-radius:6px;}" % LINE
OUTLINE_QSS = ("QPushButton{background:#FFFFFF;color:%s;border:1px solid #AEB7C2;border-radius:4px;padding:0 10px;}"
               "QPushButton:hover{background:#F2F4F7;}" % INK)
PRIMARY_QSS = ("QPushButton{background:%s;color:#FFFFFF;border:1px solid %s;border-radius:4px;padding:0 14px;}"
               "QPushButton:hover{background:#B71C1C;}" % (RED, RED))


def style_edit(e, w=100):
    e.setFixedSize(w, 26)
    e.setAlignment(Qt.AlignmentFlag.AlignCenter)
    e.setFont(make_font(9.5, QFont.Weight.Medium))
    e.setStyleSheet(EDIT_QSS)
    return e


def make_combo(items, w=100):
    c = QComboBox()
    c.addItems(items)
    c.setFixedSize(w, 26)
    c.setFont(make_font(9.5, QFont.Weight.Medium))
    return c


class CoilCountEdit(QLineEdit):
    """Number of coils. Insert (or F2) opens the Coil Weights window."""
    insertPressed = Signal()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Insert, Qt.Key.Key_F2):
            self.insertPressed.emit()
            e.accept()
            return
        super().keyPressEvent(e)


class AvgEdit(QLineEdit):
    """Average weight box. Read-only (click / Enter / Insert opens the window) when there are 2+ coils."""
    activated = Signal()

    def mousePressEvent(self, e):
        if self.isReadOnly():
            self.activated.emit()
            e.accept()
            return
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        keys = (Qt.Key.Key_Insert, Qt.Key.Key_F2)
        if self.isReadOnly():
            keys += (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space)
        if e.key() in keys:
            self.activated.emit()
            e.accept()
            return
        super().keyPressEvent(e)


class WeightDelegate(QStyledItemDelegate):
    advance = Signal(int)

    def createEditor(self, parent, option, index):
        ed = QLineEdit(parent)
        v = QDoubleValidator(0.0, 1e9, 3, ed)
        v.setNotation(QDoubleValidator.Notation.StandardNotation)
        v.setLocale(QLocale.c())
        ed.setValidator(v)
        ed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ed.setStyleSheet(EDIT_QSS)
        row = index.row()
        ed.returnPressed.connect(lambda: self._enter(ed, row))
        return ed

    def _enter(self, ed, row):
        # Qt itself commits and closes the editor after Enter; we only move on afterwards
        QTimer.singleShot(0, lambda: self.advance.emit(row))


class WeightTable(QTableWidget):
    pasteRequested = Signal()

    def keyPressEvent(self, e):
        if e.matches(QKeySequence.StandardKey.Paste):
            self.pasteRequested.emit()
            e.accept()
            return
        super().keyPressEvent(e)


class CoilWeightsDialog(QDialog):
    """Enter the weight of every coil. Any number of coils; paste a column from Excel."""
    OUTLIER = 0.30       # a weight more than 30% away from the median gets an amber tint

    def __init__(self, parent, weights):
        super().__init__(parent)
        self.setWindowTitle("Coil Weights")
        self.setModal(True)
        self.setStyleSheet("QDialog{background:%s;}" % WINDOW_BG)
        self.setMinimumSize(420, 440)
        self.resize(440, 580)
        self._building = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._refresh)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)
        outer.addWidget(SectionTitle("Coil Weights"))
        hint = mk_label("Enter the weight of each coil in kg. Tip: copy a column from Excel, "
                        "click the first cell and press Ctrl+V.", 8.5, MUTED)
        hint.setWordWrap(True)
        outer.addWidget(hint)

        row1 = QHBoxLayout()
        row1.addWidget(mk_label("Number of coils:"))
        row1.addStretch(1)
        self.n_edit = style_edit(QLineEdit(), 90)
        self.n_edit.setValidator(QIntValidator(1, MAX_COILS, self))
        row1.addWidget(self.n_edit)
        outer.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(mk_label("Set all coils to (kg):"))
        row2.addStretch(1)
        self.fill_edit = style_edit(QLineEdit(), 90)
        self.fill_btn = QPushButton("Set all")
        self.fill_btn.setFixedSize(64, 26)
        self.fill_btn.setFont(make_font(9, QFont.Weight.Medium))
        self.fill_btn.setStyleSheet(OUTLINE_QSS)
        self.fill_btn.setAutoDefault(False)
        row2.addWidget(self.fill_edit)
        row2.addWidget(self.fill_btn)
        outer.addLayout(row2)

        self.table = WeightTable(0, 2)
        base_table(self.table, 28, 24)
        self.table.setHorizontalHeaderLabels(["Coil", "Weight (kg)"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.resizeSection(0, 70)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                                   QAbstractItemView.EditTrigger.EditKeyPressed |
                                   QAbstractItemView.EditTrigger.AnyKeyPressed |
                                   QAbstractItemView.EditTrigger.SelectedClicked)
        self.delegate = WeightDelegate(self.table)
        self.table.setItemDelegateForColumn(1, self.delegate)
        outer.addWidget(self.table, 1)

        self.sum1 = mk_label("", 10, INK, QFont.Weight.DemiBold)
        self.sum2 = ElidedLabel("")
        self.msg = ElidedLabel("")
        self.msg.set_color(BAD)
        outer.addWidget(self.sum1)
        outer.addWidget(self.sum2)
        outer.addWidget(self.msg)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.clear_btn = QPushButton("Clear")
        self.cancel_btn = QPushButton("Cancel")
        self.apply_btn = QPushButton("Apply")
        for b, qss in ((self.clear_btn, OUTLINE_QSS), (self.cancel_btn, OUTLINE_QSS), (self.apply_btn, PRIMARY_QSS)):
            b.setFixedHeight(32)
            b.setMinimumWidth(84)
            b.setFont(make_font(9, QFont.Weight.Medium))
            b.setStyleSheet(qss)
            b.setAutoDefault(False)
        btns.addWidget(self.clear_btn)
        btns.addStretch(1)
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.apply_btn)
        outer.addLayout(btns)

        self._set_rows(len(weights), weights)
        self.n_edit.setText(str(len(weights)))
        self.n_edit.textChanged.connect(self._n_changed)
        self.table.itemChanged.connect(self._item_changed)
        self.table.pasteRequested.connect(self._paste)
        self.delegate.advance.connect(self._advance)
        self.fill_btn.clicked.connect(self._fill_all)
        self.fill_edit.returnPressed.connect(self._fill_all)
        self.clear_btn.clicked.connect(self._clear_all)
        self.cancel_btn.clicked.connect(self.reject)
        self.apply_btn.clicked.connect(self._apply)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._apply)
        self._refresh()
        self.table.setCurrentCell(0, 1)
        self.table.setFocus()

    # -- table helpers
    def _set_rows(self, n, weights=None):
        self._building = True
        old = self.table.rowCount()
        self.table.setRowCount(n)
        for r in range(old, n):
            it0 = QTableWidgetItem(str(r + 1))
            it0.setFlags(Qt.ItemFlag.ItemIsEnabled)
            it0.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 0, it0)
            v = weights[r] if (weights and r < len(weights)) else None
            it1 = QTableWidgetItem("" if v is None else fmt_weight(v))
            it1.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 1, it1)
        self._building = False

    def _values(self):
        out = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 1)
            out.append(parse_weight(it.text()) if it else None)
        return out

    def _n_changed(self, text):
        n = int(text) if text.isdigit() else 0
        self._set_rows(min(n, MAX_COILS))
        self.msg.set_full("")
        self._timer.start()

    def _item_changed(self, _item):
        if not self._building:
            self.msg.set_full("")
            self._timer.start()

    def _advance(self, row):
        nxt = row + 1
        if nxt < self.table.rowCount():
            self.table.setCurrentCell(nxt, 1)
            self.table.editItem(self.table.item(nxt, 1))

    def _refresh(self):
        vals = self._values()
        filled = [v for v in vals if v]
        n = len(vals)
        if filled:
            avg = sum(filled) / len(filled)
            self.sum1.setText("Average %s kg" % "{:,.2f}".format(avg))
            lo, hi = min(filled), max(filled)
            rng = "all equal" if lo == hi else "min {:,.0f}  -  max {:,.0f}".format(lo, hi)
            self.sum2.set_full("Total {:,.0f} kg   |   {}   |   filled {} of {}".format(sum(filled), rng, len(filled), n))
        else:
            self.sum1.setText("Average -")
            self.sum2.set_full("filled 0 of %d" % n)
        # tint outliers (typo catcher): far from the median
        self._building = True
        med = statistics.median(filled) if len(filled) >= 3 else None
        for r, v in enumerate(vals):
            it = self.table.item(r, 1)
            if it is None:
                continue
            if med and v and abs(v - med) / med > self.OUTLIER:
                it.setBackground(QBrush(QColor("#FFF1CC")))
                it.setToolTip("%.0f%% away from the median (%s kg). Typo?" % (abs(v - med) / med * 100, fmt_weight(med)))
            else:
                it.setBackground(QBrush())
                it.setToolTip("")
        self._building = False

    def _paste(self):
        toks = parse_pasted_numbers(QGuiApplication.clipboard().text())
        if not toks:
            self.msg.set_full("Nothing to paste.")
            return
        start = max(0, self.table.currentRow())
        need = start + len(toks)
        note = ""
        if need > self.table.rowCount():
            if need > MAX_COILS:
                toks = toks[:MAX_COILS - start]
                need = MAX_COILS
            self.n_edit.blockSignals(True)
            self.n_edit.setText(str(need))
            self.n_edit.blockSignals(False)
            self._set_rows(need)
            note = "Number of coils changed to %d. " % need
        self._building = True
        for i, tok in enumerate(toks):
            self.table.item(start + i, 1).setText(tok)
        self._building = False
        self._refresh()
        self.msg.set_color(MUTED)
        self.msg.set_full(note + "Pasted %d values starting at coil %d." % (len(toks), start + 1))

    def _fill_all(self):
        v = parse_weight(self.fill_edit.text())
        self.msg.set_color(BAD)
        if v is None:
            self.msg.set_full("Type a weight above 0 in 'Set all coils to'.")
            return
        self._building = True
        for r in range(self.table.rowCount()):
            self.table.item(r, 1).setText(fmt_weight(v))
        self._building = False
        self._refresh()

    def _clear_all(self):
        self._building = True
        for r in range(self.table.rowCount()):
            self.table.item(r, 1).setText("")
        self._building = False
        self._refresh()

    def _apply(self):
        self.msg.set_color(BAD)
        vals = self._values()
        if not vals:
            self.msg.set_full("Type the number of coils first.")
            return
        bad = [i for i, v in enumerate(vals) if v is None]
        if bad:
            self.table.setCurrentCell(bad[0], 1)
            self.table.scrollToItem(self.table.item(bad[0], 1))
            self.table.setFocus()
            self.msg.set_full("%d weight(s) missing or invalid, first: coil %d." % (len(bad), bad[0] + 1))
            return
        self.accept()

    def weights(self):
        return [v for v in self._values()]


class InputPanel(QFrame):

    def __init__(self):
        super().__init__()
        self.setObjectName("Panel")
        self.setStyleSheet(PANEL_QSS)
        self.weights = []          # one entry per coil when there are 2+ coils (float or None)
        self._single = None        # the weight when there is 1 coil (typed inline)
        self._mode_inline = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)
        outer.addWidget(SectionTitle("Input Parameters"))

        form = QGridLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        form.setColumnStretch(0, 1)
        r = 0
        self.coils_edit = style_edit(CoilCountEdit())
        self.coils_edit.setValidator(QIntValidator(1, MAX_COILS, self))
        self.coils_edit.setToolTip("Press Insert (or F2) to enter the weight of each coil")
        form.addWidget(mk_label("Number of coils:"), r, 0)
        form.addWidget(self.coils_edit, r, 1)
        r += 1
        self.avg_label = mk_label("Coil weight (kg):")
        self.avg_edit = style_edit(AvgEdit())
        form.addWidget(self.avg_label, r, 0)
        form.addWidget(self.avg_edit, r, 1)
        r += 1
        self.summary_row = QWidget()
        sr = QHBoxLayout(self.summary_row)
        sr.setContentsMargins(0, 0, 0, 0)
        sr.setSpacing(8)
        self.summary = ElidedLabel("")
        self.edit_btn = QPushButton("Edit...")
        self.edit_btn.setFixedSize(58, 24)
        self.edit_btn.setFont(make_font(9, QFont.Weight.Medium))
        self.edit_btn.setStyleSheet(OUTLINE_QSS)
        self.edit_btn.setToolTip("Edit the coil weights (Insert)")
        sr.addWidget(self.summary, 1)
        sr.addWidget(self.edit_btn)
        form.addWidget(self.summary_row, r, 0, 1, 2)
        r += 1
        self.width_edit = style_edit(QLineEdit())
        form.addWidget(mk_label("Coil width (mm):"), r, 0)
        form.addWidget(self.width_edit, r, 1)
        r += 1
        self.sizes_box = make_combo([str(i) for i in range(0, 8)])
        form.addWidget(mk_label("Strip sizes count:"), r, 0)
        form.addWidget(self.sizes_box, r, 1)
        r += 1
        rng = QWidget()
        rng.setFixedSize(100, 26)
        rl = QHBoxLayout(rng)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)
        self.smin_edit = style_edit(QLineEdit(), 38)
        self.smax_edit = style_edit(QLineEdit(), 38)
        rl.addWidget(self.smin_edit)
        rl.addWidget(mk_label("to", 9, MUTED))
        rl.addWidget(self.smax_edit)
        form.addWidget(mk_label("Scrap range (mm):"), r, 0)
        form.addWidget(rng, r, 1)
        r += 1
        self.every = QCheckBox("At least one of each size")
        self.every.setFont(make_font(9))
        form.addWidget(self.every, r, 0, 1, 2)
        outer.addLayout(form)

        # strip size rows: 1 column up to 3 sizes, 2 columns from 4 sizes (worst case: 7 sizes = 4 rows)
        self.sizes_grid = QGridLayout()
        self.sizes_grid.setHorizontalSpacing(8)
        self.sizes_grid.setVerticalSpacing(6)
        self.heads = [mk_label("Size", 8.5, MUTED, QFont.Weight.Medium),
                      mk_label("Width (mm)", 8.5, MUTED, QFont.Weight.Medium),
                      mk_label("Size", 8.5, MUTED, QFont.Weight.Medium),
                      mk_label("Width (mm)", 8.5, MUTED, QFont.Weight.Medium)]
        self.size_labels = [mk_label("Size %d:" % (i + 1)) for i in range(7)]
        self.size_edits = [style_edit(QLineEdit(), 70) for _ in range(7)]
        outer.addLayout(self.sizes_grid)

        self.fit_label = mk_label("One strip of each size: 0 / 0 mm", 8.5, MUTED)
        self.fit = FitMeter()
        outer.addSpacing(2)
        outer.addWidget(self.fit)
        outer.addWidget(self.fit_label)
        outer.addStretch(1)

        self.coils_edit.textChanged.connect(self._on_count)
        self.coils_edit.insertPressed.connect(self.open_weights)
        self.avg_edit.activated.connect(self.open_weights)
        self.avg_edit.textEdited.connect(self._on_avg_typed)
        self.edit_btn.clicked.connect(self.open_weights)
        self.sizes_box.currentIndexChanged.connect(self._relayout_sizes)
        for ed in [self.width_edit] + self.size_edits:       # the fit bar follows what is typed
            ed.textChanged.connect(self._update_fit)
        self._relayout_sizes()
        self.refresh()

    # -- coil count and weights
    def _count(self):
        t = self.coils_edit.text().strip()
        return int(t) if t.isdigit() else 0

    def _on_count(self, _t=None):
        n = self._count()
        if n >= 2:
            cur = len(self.weights)
            if cur == 0:
                self.weights = [self._single] + [None] * (n - 1)
            elif n > cur:
                self.weights += [None] * (n - cur)
            else:
                del self.weights[n:]
        else:
            if self.weights:
                self._single = self.weights[0]
            self.weights = []
        self.refresh()

    def _on_avg_typed(self, text):
        if self._count() <= 1:
            self._single = parse_weight(text)

    def refresh(self):
        n = self._count()
        inline = n <= 1
        self.avg_label.setText("Coil weight (kg):" if inline else "Avg weight/coil (kg):")
        self.summary_row.setVisible(not inline)
        if inline:
            self.avg_edit.setReadOnly(False)
            self.avg_edit.setStyleSheet(EDIT_QSS)
            self.avg_edit.unsetCursor()
            if self._mode_inline is not True:
                self.avg_edit.blockSignals(True)
                self.avg_edit.setText("" if self._single is None else fmt_weight(self._single))
                self.avg_edit.blockSignals(False)
        else:
            vals = [v for v in self.weights if v]
            missing = len(self.weights) - len(vals)
            self.avg_edit.setReadOnly(True)
            self.avg_edit.setStyleSheet(READONLY_QSS)
            self.avg_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            if missing == 0 and vals:
                self.avg_edit.setText("%.2f" % (sum(vals) / len(vals)))
                lo, hi = min(vals), max(vals)
                rng = "all equal" if lo == hi else "{:,.0f} to {:,.0f}".format(lo, hi)
                self.summary.set_color(MUTED)
                self.summary.set_full("Total {:,.0f} kg  |  {}".format(sum(vals), rng))
            else:
                self.avg_edit.setText("—")
                self.summary.set_color(BAD)
                self.summary.set_full("%d weight%s missing - press Insert" % (missing, "" if missing == 1 else "s"))
        self._mode_inline = inline

    def open_weights(self):
        n = max(self._count(), 1)
        if n == 1:
            w = [self._single]
        else:
            w = list(self.weights) if len(self.weights) == n else [None] * n
        dlg = CoilWeightsDialog(self.window(), w)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.apply_weights(dlg.weights())

    def apply_weights(self, vals):
        n = len(vals)
        self.coils_edit.blockSignals(True)
        self.coils_edit.setText(str(n))
        self.coils_edit.blockSignals(False)
        if n >= 2:
            self.weights = list(vals)
        else:
            self.weights = []
            self._single = vals[0] if vals else None
        self._mode_inline = None
        self.refresh()

    def needs_weights(self):
        n = self._count()
        if n >= 2:
            return any(v is None for v in self.weights)
        return self._single is None

    # -- strip sizes
    def _relayout_sizes(self):
        n = int(self.sizes_box.currentText())
        two = n >= 4
        for w in self.heads + self.size_labels + self.size_edits:
            self.sizes_grid.removeWidget(w)
            w.hide()
        # columns: 0 label | 1 edit | 2 gap | 3 label | 4 edit
        self.sizes_grid.setColumnStretch(0, 1)
        self.sizes_grid.setColumnStretch(3, 1 if two else 0)
        self.sizes_grid.setColumnMinimumWidth(2, 12 if two else 0)
        if n == 0:
            return
        self.sizes_grid.addWidget(self.heads[0], 0, 0)
        self.sizes_grid.addWidget(self.heads[1], 0, 1)
        self.heads[0].show()
        self.heads[1].show()
        if two:
            self.sizes_grid.addWidget(self.heads[2], 0, 3)
            self.sizes_grid.addWidget(self.heads[3], 0, 4)
            self.heads[2].show()
            self.heads[3].show()
        for i in range(n):
            row, col = (i // 2 + 1, 3 if i % 2 else 0) if two else (i + 1, 0)
            self.sizes_grid.addWidget(self.size_labels[i], row, col)
            self.sizes_grid.addWidget(self.size_edits[i], row, col + 1)
            self.size_labels[i].show()
            self.size_edits[i].show()
        self._update_fit()

    def _update_fit(self, _t=None):
        n = int(self.sizes_box.currentText())
        total = 0
        for ed in self.size_edits[:n]:
            v = parse_weight(ed.text())
            total += v if v else 0
        cw = parse_weight(self.width_edit.text()) or 0
        self.fit.set_values(total, cw)
        bad = cw > 0 and total > cw
        self.fit_label.setStyleSheet("color:%s;" % (BAD if bad else MUTED))
        self.fit_label.setText("One strip of each size: %s / %s mm" % (fmt_weight(total), fmt_weight(cw)))

    def set_state(self, cfg):
        if cfg is None:
            self.coils_edit.blockSignals(True)
            self.coils_edit.clear()
            self.coils_edit.blockSignals(False)
            self.weights = []
            self._single = None
            self._mode_inline = None
            self.avg_edit.clear()
            self.sizes_box.setCurrentIndex(0)
            for ed in self.size_edits + [self.width_edit, self.smin_edit, self.smax_edit]:
                ed.clear()
            self.every.setChecked(False)
            self.refresh()
            self._update_fit()
            return
        self.apply_weights([float(w) for w in cfg["weights"]])
        self.sizes_box.setCurrentText(str(len(cfg["sizes"])))
        self.width_edit.setText(str(cfg["width"]))
        self.smin_edit.setText(str(cfg["smin"]))
        self.smax_edit.setText(str(cfg["smax"]))
        self.every.setChecked(cfg["every"])
        for ed in self.size_edits:
            ed.clear()
        for ed, sz in zip(self.size_edits, cfg["sizes"]):
            ed.setText(str(sz))
        self._update_fit()

    # --- Getter methods for controller ---
    def get_coils(self):
        n = self._count()
        return n if n > 0 else 1

    def get_weights(self):
        n = self._count()
        if n <= 1:
            # If _single is not set (e.g., programmatic setText), read from avg_edit
            if self._single is not None:
                return [self._single]
            # Fallback: read from avg_edit text
            try:
                v = float(self.avg_edit.text())
                return [v] if v > 0 else []
            except ValueError:
                return []
        return [v if v is not None else 0 for v in self.weights]

    def get_width(self):
        return int(self.width_edit.text()) if self.width_edit.text() else 0

    def get_avg(self):
        if self._count() <= 1:
            return float(self.avg_edit.text()) if self.avg_edit.text() else 0.0
        vals = [v for v in self.weights if v]
        return sum(vals) / len(vals) if vals else 0.0

    def get_sizes_count(self):
        return int(self.sizes_box.currentText())

    def get_sizes(self):
        n = self.get_sizes_count()
        return [int(self.size_edits[i].text()) if self.size_edits[i].text() else 0 for i in range(n)]

    def get_smin(self):
        return int(self.smin_edit.text()) if self.smin_edit.text() else 0

    def get_smax(self):
        return int(self.smax_edit.text()) if self.smax_edit.text() else 0

    def get_every(self):
        return self.every.isChecked()

    def get_all_params(self):
        params = {
            "coils": self.get_coils(),
            "weights": self.get_weights(),
            "width": self.get_width(),
            "avg": self.get_avg(),
            "sizes": self.get_sizes(),
            "smin": self.get_smin(),
            "smax": self.get_smax(),
            "every": self.get_every(),
        }
        return params

    # ---------------------------------------------------------------- right panel
class ResultsPanel(QFrame):
    inputsRestore = Signal(object)
    suggestion = Signal(str, int)

    def __init__(self):
        super().__init__()
        self.setObjectName("Panel")
        self.setStyleSheet(PANEL_QSS)
        self.cfg = None
        self.memory = None  # Injected by controller
        self.history = ResultsHistory()
        self.filter_state = None
        self.calc_id = 0
        self.cur_src = None
        self.cur_vm = None
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(7)

        head = QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(SectionTitle("Results"))
        head.addSpacing(6)
        self.filter_btn = QPushButton("Filter...")
        self.unfilter_btn = QPushButton("Show all")
        self.hist_btn = QPushButton("History")
        for b_, w_, tip in ((self.filter_btn, 84, "Show only the combinations that match (at least / at most of each size, strips, scrap)"),
                            (self.unfilter_btn, 76, "Remove the filter and show every combination again"),
                            (self.hist_btn, 112, "Go back to one of the last results without searching again")):
            b_.setFixedSize(w_, 22)
            b_.setFont(make_font(9, QFont.Weight.Medium))
            b_.setStyleSheet(OUTLINE_QSS)
            b_.setToolTip(tip)
            b_.setAutoDefault(False)
            head.addWidget(b_)
        self.unfilter_btn.hide()
        self.status = ElidedLabel("No calculation yet", Qt.AlignmentFlag.AlignRight)
        head.addWidget(self.status, 1)
        v.addLayout(head)

        self.table = ResultsView()
        v.addWidget(self.table, 1)

        head2 = QHBoxLayout()
        head2.setSpacing(6)
        head2.addWidget(SectionTitle("Selected Combination"), 1)
        self.pin_btn = QPushButton("Pin")
        self.cmp_btn = QPushButton("Compare...")
        for b_, w_, tip in ((self.pin_btn, 60, "Pin this combination into memory (a star shows in the Formula column)"),
                            (self.cmp_btn, 96, "Compare combinations side by side (max 4, pinned ones are in memory)")):
            b_.setFixedSize(w_, 24)
            b_.setFont(make_font(9, QFont.Weight.Medium))
            b_.setStyleSheet(OUTLINE_QSS)
            b_.setToolTip(tip)
            b_.setAutoDefault(False)
            head2.addWidget(b_)
        head2.addSpacing(8)
        self.prev_btn = QPushButton("◂")
        self.next_btn = QPushButton("▸")
        for b_, tip in ((self.prev_btn, "Previous combination (Alt+Left, or the Up arrow in the table)"),
                        (self.next_btn, "Next combination (Alt+Right, or the Down arrow in the table)")):
            b_.setFixedSize(28, 24)
            b_.setFont(make_font(10, QFont.Weight.Medium))
            b_.setStyleSheet(NAV_QSS)
            b_.setToolTip(tip)
            b_.setAutoDefault(False)
        self.nav = mk_label("", 8.5, MUTED)
        self.nav.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nav.setProperty("skip_text_check", True)
        head2.addWidget(self.prev_btn)
        head2.addWidget(self.nav)
        head2.addWidget(self.next_btn)
        head2.addSpacing(8)
        self.badge = Badge()
        head2.addWidget(self.badge)
        v.addLayout(head2)

        self.bar = StripBar()
        self.ruler = Ruler()
        v.addWidget(self.bar)
        v.addWidget(self.ruler)

        line = QHBoxLayout()
        line.setSpacing(10)
        self.legend = Legend()
        self.knives = ElidedLabel("Knife positions (mm): —")
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setFixedSize(60, 24)
        self.copy_btn.setFont(make_font(9, QFont.Weight.Medium))
        self.copy_btn.setStyleSheet(OUTLINE_QSS)
        self.copy_btn.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.knives.full))
        line.addWidget(self.legend)
        line.addWidget(self.knives, 1)
        line.addWidget(self.copy_btn)
        v.addLayout(line)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        grid = QGridLayout()
        grid.setSpacing(8)
        self.cards = [Card("Used width (mm)", GREEN), Card("Scrap (mm)", SCRAP_RED),
                      Card("Scrap per coil (kg)", BLUE), Card("Scrap total (kg)", BLUE)]
        for i, c in enumerate(self.cards):
            grid.addWidget(c, i // 2, i % 2)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        self.strip_table = StripTable()
        bottom.addLayout(grid, 2)
        bottom.addWidget(self.strip_table, 3, Qt.AlignmentFlag.AlignTop)
        v.addLayout(bottom)

        self.table.rowChosen.connect(self._row_chosen)
        self.table.notice.actionClicked.connect(self._notice_action)
        self.pin_btn.clicked.connect(self.toggle_pin)
        self.cmp_btn.clicked.connect(self.open_compare)
        self.filter_btn.clicked.connect(self.open_filter)
        self.unfilter_btn.clicked.connect(lambda: self.set_filter(None))
        self.hist_btn.clicked.connect(self.show_history_menu)
        self.prev_btn.clicked.connect(lambda: self.step(-1))
        self.next_btn.clicked.connect(lambda: self.step(+1))
        self.table.horizontalHeader().sectionClicked.connect(lambda _c: self._set_status())
        QShortcut(QKeySequence("Alt+Left"), self, activated=lambda: self.step(-1))
        QShortcut(QKeySequence("Alt+Right"), self, activated=lambda: self.step(+1))
        self._set_nav(None)
        self._update_memory_ui()
        self._update_history_ui()
        self._update_filter_ui()

    # -- navigation between combinations
    def step(self, delta):
        if self.table.results.shown:
            self.table.select_row(max(0, self.table.currentIndex().row()) + delta)

    def _set_nav(self, view_row):
        n = self.table.results.shown
        self.prev_btn.setEnabled(bool(n) and view_row is not None and view_row > 0)
        self.next_btn.setEnabled(bool(n) and view_row is not None and view_row < n - 1)
        if not n or view_row is None:
            self.nav.setText("")
            self.nav.setFixedWidth(40)
            return
        rank = self.table.results.row_plan(view_row)[2]
        text = "{:,} of {:,}  |  F{:,}".format(view_row + 1, n, rank)
        self.nav.setText(text)
        self.nav.setFixedWidth(QFontMetrics(self.nav.font()).horizontalAdvance(text) + 14)

    def _set_status(self):
        r = self.table.results
        if not r.n:
            return
        if r.visible is not None:
            head = ("Showing {:,} of {:,} combinations (filtered)".format(r.shown, r.n) if r.shown
                    else "No combination matches the filter (0 of {:,})".format(r.n))
        else:
            head = "Showing all {:,} combinations".format(r.n)
        self.status.setText(head + ("  |  sorted by {}".format(r.sort_text()) if r.shown else ""))

    def _row_chosen(self, view_row):
        r = self.table.results
        if self.cfg is None or not (0 <= view_row < r.shown):
            return
        scrap, qty, rank = r.row_plan(view_row)
        self.cur_vm = plan_vm(self.cfg, scrap, qty)
        self.cur_src = rank - 1
        self.show_plan(self.cur_vm)
        self._set_nav(view_row)
        self._update_memory_ui()

    # -- filter
    def _update_filter_ui(self):
        on = self.filter_state is not None
        self.filter_btn.setText("Filter ON" if on else "Filter...")
        self.filter_btn.setStyleSheet(OUTLINE_QSS + "QPushButton{color:%s;border:1px solid %s;}" % (RED, RED) if on else OUTLINE_QSS)
        self.unfilter_btn.setVisible(on)
        self.filter_btn.setEnabled(self.table.results.n > 0)

    def open_filter(self):
        r = self.table.results
        if not r.n:
            return
        dlg = FilterDialog(self.window(), r, self.filter_state)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.set_filter(dlg.filter())

    def set_filter(self, f):
        r = self.table.results
        self.filter_state = f
        if f is None:
            r.clear_filter()
        else:
            r.apply_filter(f)
        self._update_filter_ui()
        self._set_status()
        if r.shown:
            self.table.notice.hide()
            self.table.select_row(0)
        else:
            self.cur_vm = None
            self.cur_src = None
            self._set_nav(None)
            self._blank_plan()
            self._update_memory_ui()
            self.table.notice.show_info("No combination matches the filter",
                                        "Loosen the limits, or show all {:,} combinations again.".format(r.n),
                                        "Show all combinations", "clear_filter", 0)
            self.unfilter_btn.hide()

    def _notice_action(self, key, value):
        if key == "clear_filter":
            self.set_filter(None)
        else:
            self.suggestion.emit(key, value)

    # -- history: the last results, without searching again
    def _update_history_ui(self):
        n = len(self.history.items)
        self.hist_btn.setText("History (%d)" % n if n else "History")
        self.hist_btn.setEnabled(n > 0)

    def history_actions(self):
        return [(self.history.label(e), i, e["calc"] == self.calc_id) for i, e in enumerate(self.history.items)]

    def show_history_menu(self):
        menu = QMenu(self)
        for label, i, current in self.history_actions():
            act = menu.addAction(("●  " if current else "      ") + label)
            act.triggered.connect(lambda _c=False, i=i: self.restore(i))
        menu.addSeparator()
        info = menu.addAction("Memory used: {:.1f} MB of {:.0f} MB   (keeps the last {} results)".format(
            self.history.total_bytes() / 1048576.0, HISTORY_MAX_BYTES / 1048576.0, HISTORY_KEEP))
        info.setEnabled(False)
        menu.exec(self.hist_btn.mapToGlobal(QPoint(0, self.hist_btn.height())))

    def restore(self, index):
        e = self.history.items[index]
        self.calc_id = e["calc"]
        self.cfg = e["cfg"]
        self.filter_state = None
        r = self.table.results
        r.load_arrays(e["width"], e["sizes"], e["qty"], e["scrap"], e["strips"])
        r.pinned = {it["src"] for it in self.memory.items if it["calc"] == self.calc_id}
        r.set_pinned(-1, False)
        self.table.notice.hide()
        self._update_filter_ui()
        self._set_status()
        self.inputsRestore.emit(e["cfg"])
        self._clear_choice()

    # -- memory and compare
    def _update_memory_ui(self):
        if self.memory is None:
            return
        pinned = self.cur_src is not None and self.memory.find(self.calc_id, self.cur_src) is not None
        self.pin_btn.setText("Unpin" if pinned else "Pin")
        self.pin_btn.setEnabled(self.cur_vm is not None)
        n = len(self.memory)
        # Show 4-way / 3-way / 2-way depending on how many entries are available
        entries = self._compare_entries()
        entries_available = len(entries)
        if entries_available >= 4:
            self.cmp_btn.setText("Compare 4 (%d)" % n if n else "Compare 4")
            self.cmp_btn.setToolTip("Compare up to four combinations side by side")
        elif entries_available >= 3:
            self.cmp_btn.setText("Compare 3 (%d)" % n if n else "Compare 3")
            self.cmp_btn.setToolTip("Compare three combinations side by side (max 3)")
        else:
            self.cmp_btn.setText("Compare (%d)" % n if n else "Compare...")
            self.cmp_btn.setToolTip("Compare two combinations side by side (pinned ones are in memory)")
        self.cmp_btn.setEnabled(entries_available >= 2)

    def toggle_pin(self):
        if self.memory is None or self.cur_vm is None or self.cur_src is None:
            return
        item = self.memory.find(self.calc_id, self.cur_src)
        if item:
            self.memory.remove(item)
            self.table.results.set_pinned(self.cur_src, False)
        else:
            if self.memory.add(dict(self.cur_vm), self.calc_id, self.cur_src, self.cur_src + 1) is None:
                self.status.setText("Memory is full (%d pinned). Clear it in Compare." % MemoryStore.MAX)
                return
            self.table.results.set_pinned(self.cur_src, True)
        self._update_memory_ui()

    def _compare_entries(self):
        entries, cur_key = [], None
        if self.cur_vm is not None:
            cur_key = (self.calc_id, self.cur_src)
            entries.append(("Current selection  (Formula F{:,}):  {}".format(self.cur_src + 1, plan_text(self.cur_vm)), self.cur_vm))
        if self.cfg is not None and self.table.results.n:
            scrap, qty = self.table.results.plan_src(0)
            entries.append(("Formula F1:  " + plan_text(plan_vm(self.cfg, scrap, qty)), plan_vm(self.cfg, scrap, qty)))
        if self.memory is not None:
            for it in self.memory.items:
                vm = it["vm"]
                entries.append(("Pinned #%d  (Formula F%s, coil %s mm):  %s" % (it["id"], "{:,}".format(it["rank"]), vm["width"], plan_text(vm)), vm))
        return entries

    def open_compare(self):
        entries = self._compare_entries()
        if not entries:
            return
        has_cur = self.cur_vm is not None
        base = 1 if has_cur else 0
        has_low = self.cfg is not None and self.table.results.n > 0
        low_i = base if has_low else None
        pin0 = base + (1 if has_low else 0)
        picks = []
        for k, it in enumerate(self.memory.items):                     # pinned ones, oldest first
            if has_cur and it["calc"] == self.calc_id and it["src"] == self.cur_src:
                continue
            picks.append(pin0 + k)
        if has_cur:
            picks.append(0)                                            # the selected one last
        if len(picks) < 2 and low_i is not None and low_i not in picks:
            picks.insert(0, low_i)
        picks = picks[-4:]
        picks += [None] * (4 - len(picks))
        dlg = CompareDialog(self.window(), entries, picks)
        dlg.exec()
        if dlg.cleared:
            self.memory.clear()
            self.table.results.pinned = set()
            self.table.results.set_pinned(-1, False)
            self._update_memory_ui()

    # -- showing things
    def _blank_plan(self, hint=False):
        self.badge.set_state("pick" if hint else "none")
        self.bar.set_vm(None)
        self.ruler.set_vm(None)
        self.legend.set_vm(None)
        self.knives.set_full("Knife positions (mm): —")
        for c in self.cards:
            c.set_value("—")
        self.strip_table.show_empty()

    def _clear_choice(self):
        self.cur_vm = None
        self.cur_src = None
        self.table.clearSelection()
        self.table.setCurrentIndex(QModelIndex())
        self.table.scrollToTop()
        self._set_nav(None)
        self._blank_plan(hint=self.table.results.shown > 0)
        self._update_memory_ui()

    def show_plan(self, vm):
        self.badge.set_state("ok" if vm["weight_ok"] else "bad")
        self.bar.set_vm(vm)
        self.ruler.set_vm(vm)
        self.legend.set_vm(vm)
        self.knives.set_full("Knife positions (mm): " + " | ".join(str(k) for k in vm["knives"]))
        self.cards[0].set_value(str(vm["used"]))
        self.cards[1].set_value(str(vm["scrap"]))
        self.cards[2].set_value("%.2f" % vm["scrap_per"])
        self.cards[3].set_value("%.2f" % vm["scrap_total"])
        self.strip_table.show_vm(vm)

    def apply(self, vm, cfg=None):
        self.calc_id += 1
        self.filter_state = None
        if vm is None:
            self.cfg = None
            self.cur_vm = None
            self.cur_src = None
            self.table.results.clear()
            self._set_nav(None)
            self._blank_plan()
            self._update_memory_ui()
            self._update_filter_ui()
            if cfg is not None:
                info = explain_no_plan(cfg)
                self.status.setText("No combination found")
                self.table.notice.show_info(info["title"], info["body"], info.get("button"),
                                            info.get("key", ""), info.get("value", 0))
            else:
                self.status.setText("No calculation yet")
                self.table.notice.hide()
            return
        self.table.notice.hide()
        self.cfg = vm["cfg"]
        self.table.results.load(vm["width"], vm["sizes"], vm["rows"])
        entry = self.table.results.snapshot()
        entry.update(calc=self.calc_id, when=time.strftime("%H:%M:%S"), cfg=self.cfg)
        self.history.push(entry)
        self._update_history_ui()
        self._update_filter_ui()
        self._set_status()
        self._clear_choice()

    def set_memory_store(self, memory):
        """Inject MemoryStore from controller."""
        self.memory = memory


# ---------------------------------------------------------------- top bar + status line
PRIMARY_QSS = ("QPushButton{background:%s;color:#FFFFFF;border:1px solid %s;border-radius:4px;padding:0 14px;}"
               "QPushButton:hover{background:#B71C1C;}" % (RED, RED))
OUTLINE_QSS = ("QPushButton{background:#FFFFFF;color:%s;border:1px solid #AEB7C2;border-radius:4px;padding:0 10px;}"
               "QPushButton:hover{background:#F2F4F7;}" % INK)


def get_resource_path(filename):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    import sys, os
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, filename)


class LogoWidget(QLabel):
    """Logo widget that loads the real logo.png file, scaled to 40px high keeping aspect ratio."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: transparent; border: none;")
        self.load_logo()

    def load_logo(self):
        logo_path = get_resource_path("logo.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            if not pixmap.isNull():
                # Scale to 40px high keeping aspect ratio, with smooth transformation
                dpr = self.devicePixelRatioF()
                target_height = int(40 * dpr)
                scaled = pixmap.scaledToHeight(target_height, Qt.SmoothTransformation)
                scaled.setDevicePixelRatio(dpr)
                self.setPixmap(scaled)
                self.setFixedWidth(scaled.width() // dpr)
                print(f"Logo loaded: {logo_path}, original: {pixmap.size()}, displayed: {self.size()}")
                return
            else:
                print(f"Failed to load logo pixmap from: {logo_path}")
        else:
            print(f"Logo file not found: {logo_path}")
        # Fallback to painted "CS" square
        self.setText("CS")
        self.setStyleSheet("background-color: #D32F2F; color: white; border-radius: 7px; font-weight: bold; font-size: 11px;")
        self.setFixedSize(36, 36)

# Alias for backward compatibility
LogoMark = LogoWidget


class TopBar(QFrame):
    # name, full text, compact text
    SPEC = [("Calculate", "Calculate", "Calculate"), ("Cancel", "Cancel", "✕"), ("Clear", "Clear", "⌫"),
            ("Export PDF", "Export PDF", "PDF"), ("Export Excel", "Export Excel", "XLS"),
            ("Save Preset", "Save Preset", "Save"), ("Load Preset", "Load Preset", "Load"),
            ("View Log", "View Log", "Log")]

    def __init__(self):
        super().__init__()
        self.setObjectName("TopBar")
        self.setStyleSheet("#TopBar{background:#FFFFFF;border:none;border-bottom:2px solid %s;}" % RED)
        self.setFixedHeight(60)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(8)
        lay.addWidget(LogoMark())
        tb = QVBoxLayout()
        tb.setSpacing(0)
        tb.addStretch(1)
        tb.addWidget(mk_label(APP_NAME, 14, INK, QFont.Weight.DemiBold))
        tb.addWidget(mk_label(FACTORY_NAME, 8.5, MUTED, QFont.Weight.Medium))
        tb.addWidget(mk_label("Version " + VERSION, 8.5, MUTED))
        tb.addStretch(1)
        lay.addLayout(tb)
        lay.addStretch(1)
        self.buttons = {}
        for name, _full, _short in self.SPEC:
            b = QPushButton(name)
            b.setFixedHeight(32)
            b.setFont(make_font(9, QFont.Weight.Medium))
            b.setStyleSheet(PRIMARY_QSS if name == "Calculate" else OUTLINE_QSS)
            lay.addWidget(b)
            self.buttons[name] = b
        self.compact = False

    def set_compact(self, compact):
        if compact == self.compact:
            return
        self.compact = compact
        for name, full, short in self.SPEC:
            b = self.buttons[name]
            b.setText(short if compact else full)
            b.setToolTip(full)
            if compact and name != "Calculate":
                b.setFixedWidth(max(40, QFontMetrics(b.font()).horizontalAdvance(short) + 22))
            else:
                b.setMinimumWidth(0)
                b.setMaximumWidth(16777215)
            b.updateGeometry()


class StatusLine(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Status")
        self.setStyleSheet("#Status{background:#FFFFFF;border:none;border-top:1px solid %s;}" % LINE)
        self.setFixedHeight(24)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        self.left = mk_label("Ready  -  layout skeleton, fake data.  F1 startup   F2 CASE W   F3 7 sizes", 8.5, MUTED)
        self.left.setProperty("skip_text_check", True)
        lay.addWidget(self.left, 1)
        lay.addWidget(mk_label("Developed by Abdalhamed", 8.5, MUTED))

    def say(self, text):
        self.left.setText(text)


# ---------------------------------------------------------------- main window
from PySide6.QtCore import Signal

class MainWindow(QMainWindow):
    # Signals that the controller will connect to
    calculate_requested = Signal()
    clear_requested = Signal()
    cancel_requested = Signal()
    export_pdf_requested = Signal()
    export_excel_requested = Signal()
    save_preset_requested = Signal()
    load_preset_requested = Signal()
    view_log_requested = Signal()
    params_changed = Signal(dict)  # emits all input parameters

    def __init__(self):
        super().__init__()
        self.setWindowTitle("%s - %s - Version %s" % (APP_NAME, FACTORY_NAME, VERSION))
        # Set window icon from logo.png
        logo_path = get_resource_path("logo.png")
        if os.path.exists(logo_path):
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon(logo_path))
        root = QWidget()
        root.setObjectName("Root")
        root.setStyleSheet("#Root{background:%s;}" % WINDOW_BG)
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.topbar = TopBar()
        v.addWidget(self.topbar)
        body = QWidget()
        h = QHBoxLayout(body)
        h.setContentsMargins(12, 12, 12, 12)
        h.setSpacing(12)
        self.left = InputPanel()
        self.left.setFixedWidth(340)
        self.right = ResultsPanel()
        h.addWidget(self.left)
        h.addWidget(self.right, 1)
        v.addWidget(body, 1)
        self.statusline = StatusLine()
        v.addWidget(self.statusline)

        # Connect top bar buttons to signals (controller will connect to these)
        b = self.topbar.buttons
        b["Calculate"].clicked.connect(self.calculate_requested.emit)
        b["Clear"].clicked.connect(self.clear_requested.emit)
        b["Cancel"].clicked.connect(self.cancel_requested.emit)
        b["Export PDF"].clicked.connect(self.export_pdf_requested.emit)
        b["Export Excel"].clicked.connect(self.export_excel_requested.emit)
        b["Save Preset"].clicked.connect(self.save_preset_requested.emit)
        b["Load Preset"].clicked.connect(self.load_preset_requested.emit)
        b["View Log"].clicked.connect(self.view_log_requested.emit)

        # Connect input panel changes to params_changed signal
        self.left.coils_edit.textChanged.connect(self._emit_params)
        self.left.sizes_box.currentIndexChanged.connect(self._emit_params)
        self.left.width_edit.editingFinished.connect(self._emit_params)
        self.left.avg_edit.editingFinished.connect(self._emit_params)
        self.left.smin_edit.editingFinished.connect(self._emit_params)
        self.left.smax_edit.editingFinished.connect(self._emit_params)
        self.left.every.stateChanged.connect(self._emit_params)
        for ed in self.left.size_edits:
            ed.editingFinished.connect(self._emit_params)

        # Start in empty state
        self.show_empty()

    def _emit_params(self):
        self.params_changed.emit(self.left.get_all_params())

    def show_empty(self):
        """Reset to empty startup state"""
        self.left.set_state(None)
        self.right.apply(None)
        self.statusline.say("Ready")

    def show_results(self, vm, cfg=None):
        """Display calculation results from view model"""
        if vm is None:
            self.show_empty()
            return
        self.right.apply(vm, cfg)

    def set_status(self, text):
        self.statusline.say(text)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        w = self.width()
        self.left.setFixedWidth(max(300, min(380, int(w * 0.28))))
        self.topbar.set_compact(w < 1100)


# ---------------------------------------------------------------- layout self-check
def _layout_widgets(layout, out):
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is not None:
            out.append(item.widget())
        elif item.layout() is not None:
            _layout_widgets(item.layout(), out)


def check_window(win, req_w, req_h):
    problems = []
    if win.width() > req_w + 1 or win.height() > req_h + 1:
        mh = win.minimumSizeHint()
        problems.append("window cannot shrink to %dx%d: it stays %dx%d (needs about %dx%d)"
                        % (req_w, req_h, win.width(), win.height(), mh.width(), mh.height()))
    wrect = QRect(0, 0, win.width(), win.height())
    for name, btn in win.topbar.buttons.items():
        if not btn.isVisible():
            problems.append("button '%s' is not visible" % name)
            continue
        r = QRect(btn.mapTo(win, QPoint(0, 0)), btn.size())
        if not wrect.contains(r):
            problems.append("button '%s' is outside the window" % name)
    for host in [win.centralWidget()] + win.centralWidget().findChildren(QWidget):
        lay = host.layout()
        if lay is None or not host.isVisible():
            continue
        items = []
        _layout_widgets(lay, items)
        items = [x for x in items if x.isVisible()]
        for x in items:
            msh = x.minimumSizeHint()
            mn = x.minimumSize()
            need_w = mn.width() if mn.width() > 0 else msh.width()
            need_h = mn.height() if mn.height() > 0 else msh.height()
            if x.width() + 1 < need_w or x.height() + 1 < need_h:
                problems.append("%s is squeezed: %dx%d, wants at least %dx%d"
                                % (x.metaObject().className(), x.width(), x.height(), need_w, need_h))
            if not host.rect().adjusted(-1, -1, 1, 1).contains(x.geometry()):
                problems.append("%s sticks out of its parent" % x.metaObject().className())
            if not wrect.contains(QRect(x.mapTo(win, QPoint(0, 0)), x.size())):
                problems.append("%s is outside the window" % x.metaObject().className())
        for a in range(len(items)):
            for b in range(a + 1, len(items)):
                if not items[a].geometry().intersected(items[b].geometry()).isEmpty():
                    problems.append("%s overlaps %s" % (items[a].metaObject().className(),
                                                        items[b].metaObject().className()))
    for lab in win.findChildren(QLabel):
        if lab.isVisible() and lab.text() and not lab.wordWrap() and not lab.property("skip_text_check"):
            if lab.fontMetrics().horizontalAdvance(lab.text()) > lab.width() + 1:
                problems.append("label '%s' is cut off" % lab.text())
    for btn in win.findChildren(QPushButton):
        if btn.isVisible() and btn.fontMetrics().horizontalAdvance(btn.text()) + 8 > btn.width():
            problems.append("button text '%s' is cut off" % btn.text())
    for tbl in win.findChildren(QTableWidget):
        if not tbl.isVisible():
            continue
        fm = tbl.horizontalHeader().fontMetrics()
        for c in range(tbl.columnCount()):
            item = tbl.horizontalHeaderItem(c)
            if item is None:
                continue
            need = max(fm.horizontalAdvance(part) for part in item.text().split("\n")) + 10
            if need > tbl.columnWidth(c):
                problems.append("table header '%s' is cut off" % item.text().replace("\n", " "))
    return problems


def run_check(app, out_dir):
    """Run layout self-check at multiple window sizes and states."""
    os.makedirs(out_dir, exist_ok=True)
    win = MainWindow()
    win.show()
    bad = 0
    print("%-11s %-6s %-9s %s" % ("size", "state", "needs_h", "problems"))

    # Test states: empty startup, typical results (simulated by calling show_results with mock vm)
    test_states = [
        ("empty", None),
        ("results", _mock_vm()),
    ]

    for (w, h) in [(1280, 648), (1366, 696), (1536, 792), (1920, 1008)]:
        for st_name, vm in test_states:
            win.showNormal()
            win.resize(w, h)
            if vm is None:
                win.show_empty()
            else:
                win.show_results(vm)
            for _ in range(5):
                app.processEvents()
            win.centralWidget().layout().activate()
            app.processEvents()
            problems = check_window(win, w, h)
            need_h = win.centralWidget().minimumSizeHint().height()
            print("%-11s %-6s %-9d %s" % ("%dx%d" % (w, h), st_name, need_h, "OK" if not problems else len(problems)))
            for pr in sorted(set(problems)):
                print("      -", pr)
            bad += len(problems)
            win.grab().save(os.path.join(out_dir, "%dx%d_%s.png" % (w, h, st_name)))
    print("\nResult:", "ALL CHECKS PASSED" if bad == 0 else "%d problem(s) found" % bad)
    print("Screenshots saved in:", os.path.abspath(out_dir))
    return 0 if bad == 0 else 1


def _mock_vm():
    """Create a mock view model for layout testing (similar to CASE W)."""
    width = 1290
    sizes = [111, 250, 79]
    avg = 10000.0
    coils = 3
    # Build a mock VM similar to what the real calculator would produce
    # Simple mock: 1x111, 1x250, 1x79 = 440 used, scrap=850
    qty = [1, 1, 1]
    scrap = 850
    knives, pos = [], 0
    for s, q in zip(sizes, qty):
        for _ in range(q):
            pos += s
            knives.append(pos)
    wps = [avg * s / width for s in sizes]
    total_qty = [q * coils for q in qty]
    total_w = [t * w for t, w in zip(total_qty, wps)]
    scrap_per = scrap / width * avg
    rows = [(850, (1, 1, 1)), (860, (1, 1, 2)), (870, (1, 2, 1))]
    return dict(width=width, sizes=sizes, qty=list(qty), scrap=scrap, used=width - scrap,
                pct=scrap / width * 100, strips=sum(qty), rows=rows, total=len(rows),
                knives=knives, wps=wps, total_qty=total_qty, total_w=total_w,
                scrap_per=scrap_per, scrap_total=scrap_per * coils, coils=coils, avg=avg,
                weight_ok=True,
                cfg=dict(width=width, sizes=sizes, avg=avg, coils=coils))


def apply_light_palette(app):
    """Apply the exact same light palette as layout_skeleton.py"""
    app.setStyle("Fusion")
    pal = QPalette()
    roles = {QPalette.ColorRole.Window: WINDOW_BG, QPalette.ColorRole.WindowText: INK,
             QPalette.ColorRole.Base: "#FFFFFF", QPalette.ColorRole.AlternateBase: "#F7F9FB",
             QPalette.ColorRole.Text: INK, QPalette.ColorRole.Button: "#FFFFFF",
             QPalette.ColorRole.ButtonText: INK, QPalette.ColorRole.Highlight: "#CFE3F7",
             QPalette.ColorRole.HighlightedText: INK, QPalette.ColorRole.ToolTipBase: "#FFFFFF",
             QPalette.ColorRole.ToolTipText: INK, QPalette.ColorRole.PlaceholderText: MUTED}
    for role, hexv in roles.items():
        pal.setColor(role, QColor(hexv))
    app.setPalette(pal)
    # Force light color scheme if API available
    if hasattr(app.styleHints(), "setColorScheme"):
        try:
            from PySide6.QtCore import Qt
            app.styleHints().setColorScheme(Qt.ColorScheme.Light)
        except Exception:
            pass


def main():
    """Main entry point for standalone layout testing."""
    ap = argparse.ArgumentParser(description="Slitra v%s - Layout Skeleton" % VERSION)
    ap.add_argument("--check", action="store_true", help="run the layout self-check and save screenshots")
    ap.add_argument("--shots", default="skeleton_screenshots", help="folder for --check screenshots")
    ap.add_argument("--grab", help="save a screenshot of the window to this PNG path and exit")
    args = ap.parse_args()

    app = QApplication(sys.argv[:1])
    apply_light_palette(app)
    app.setFont(make_font(9))

    if args.check:
        sys.exit(run_check(app, args.shots))

    win = MainWindow()
    win.showMaximized()

    if args.grab:
        for _ in range(5):
            app.processEvents()
        win.centralWidget().layout().activate()
        app.processEvents()
        win.grab().save(args.grab)
        print("Saved", os.path.abspath(args.grab))
        sys.exit(0)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
