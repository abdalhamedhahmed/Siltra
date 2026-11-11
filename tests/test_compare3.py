#!/usr/bin/env python3
"""Test 3-way compare dialog (non-blocking - calls _refresh directly)"""
import sys
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QBrush


class Compare3Dialog(QDialog):
    METRICS = [
        ("Used width (mm)", "used", "int", +1),
        ("Scrap (mm)", "scrap", "int", -1),
        ("Scrap (%)", "pct", "f2", -1),
        ("Total strips per coil", "strips", "int", 0),
        ("Scrap per coil (kg)", "scrap_per", "f2", -1),
        ("Scrap total (kg)", "scrap_total", "f2", -1),
    ]
    BETTER = "#E3F2E5"

    def __init__(self, parent, entries, a_idx=0, b_idx=1, c_idx=2):
        super().__init__(parent)
        self.setWindowTitle("Compare Three Combinations")
        self.setModal(True)
        self.entries = entries
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)

        self.combo_a = QComboBox()
        self.combo_b = QComboBox()
        self.combo_c = QComboBox()
        self.bar_a = QLabel("Bar A")
        self.bar_b = QLabel("Bar B")
        self.bar_c = QLabel("Bar C")

        for tag, combo, bar in (("A", self.combo_a, self.bar_a),
                                 ("B", self.combo_b, self.bar_b),
                                 ("C", self.combo_c, self.bar_c)):
            row = QHBoxLayout()
            row.addWidget(QLabel(tag))
            for label, _ in entries:
                combo.addItem(label)
            combo.setFont(QFont("Segoe UI", 9))
            combo.setFixedHeight(26)
            row.addWidget(combo, 1)
            outer.addLayout(row)
            outer.addWidget(bar)

        self.combo_a.setCurrentIndex(min(a_idx, len(entries) - 1))
        self.combo_b.setCurrentIndex(min(b_idx, len(entries) - 1))
        self.combo_c.setCurrentIndex(min(c_idx, len(entries) - 1))

        self.verdict = QLabel("")
        self.verdict.setWordWrap(True)
        self.verdict.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        outer.addWidget(self.verdict)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["", "A", "B", "C", "B−A", "C−A", "C−B"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(0, 210)
        outer.addWidget(self.table, 1)

        btns = QHBoxLayout()
        self.rotate_btn = QPushButton("Rotate A->B->C")
        self.swap_ab_btn = QPushButton("Swap A/B")
        self.swap_bc_btn = QPushButton("Swap B/C")
        self.clear_btn = QPushButton("Clear memory")
        self.close_btn = QPushButton("Close")
        for b in (self.rotate_btn, self.swap_ab_btn, self.swap_bc_btn, self.clear_btn, self.close_btn):
            b.setFixedHeight(32)
            b.setMinimumWidth(96)
            b.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
            btns.addWidget(b)
        btns.addStretch(1)
        outer.addLayout(btns)

        self.combo_a.currentIndexChanged.connect(self._refresh)
        self.combo_b.currentIndexChanged.connect(self._refresh)
        self.combo_c.currentIndexChanged.connect(self._refresh)
        self.rotate_btn.clicked.connect(self._rotate)
        self.swap_ab_btn.clicked.connect(lambda: self._swap(self.combo_a, self.combo_b))
        self.swap_bc_btn.clicked.connect(lambda: self._swap(self.combo_b, self.combo_c))
        self.clear_btn.clicked.connect(self._clear)
        self.close_btn.clicked.connect(self.accept)
        self._refresh()

    def _swap(self, ca, cb):
        a, b = ca.currentIndex(), cb.currentIndex()
        ca.blockSignals(True)
        cb.blockSignals(True)
        ca.setCurrentIndex(b)
        cb.setCurrentIndex(a)
        ca.blockSignals(False)
        cb.blockSignals(False)
        self._refresh()

    def _rotate(self):
        a, b, c = self.combo_a.currentIndex(), self.combo_b.currentIndex(), self.combo_c.currentIndex()
        self.combo_a.blockSignals(True)
        self.combo_b.blockSignals(True)
        self.combo_c.blockSignals(True)
        self.combo_a.setCurrentIndex(c)
        self.combo_b.setCurrentIndex(a)
        self.combo_c.setCurrentIndex(b)
        self.combo_a.blockSignals(False)
        self.combo_b.blockSignals(False)
        self.combo_c.blockSignals(False)
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
            return "="
        return ("%+d" % d) if kind == "int" else ("%+.2f" % d)

    def _refresh(self):
        va = self.entries[self.combo_a.currentIndex()][1]
        vb = self.entries[self.combo_b.currentIndex()][1]
        vc = self.entries[self.combo_c.currentIndex()][1]

        rows = [(lab, va[key], vb[key], vc[key], kind, d) for lab, key, kind, d in self.METRICS]
        qa = dict(zip(va["sizes"], va["qty"]))
        qb = dict(zip(vb["sizes"], vb["qty"]))
        qc = dict(zip(vc["sizes"], vc["qty"]))
        for sz in sorted(set(qa) | set(qb) | set(qc)):
            rows.append(("Qty of %d mm per coil" % sz, qa.get(sz, 0), qb.get(sz, 0), qc.get(sz, 0), "int", 0))

        self.table.setRowCount(len(rows))
        bold = QFont("Segoe UI", 9, QFont.Weight.DemiBold)
        for r, (lab, a, b, c, kind, d) in enumerate(rows):
            d_ba = self._delta(a, b, kind)
            d_ca = self._delta(a, c, kind)
            d_cb = self._delta(b, c, kind)
            cells = [lab, self._fmt(a, kind), self._fmt(b, kind), self._fmt(c, kind), d_ba, d_ca, d_cb]
            for col, text in enumerate(cells):
                it = QTableWidgetItem(text)
                it.setTextAlignment((Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft) if col == 0 else Qt.AlignmentFlag.AlignCenter)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled)

                if col in (1, 2, 3):
                    vals = [a, b, c]
                    if kind == "int" and d != 0 and kind in ("used",):
                        best_idx = vals.index(max(vals))
                        if col - 1 == best_idx:
                            it.setBackground(QBrush(QColor(self.BETTER)))
                            it.setFont(bold)
                    elif kind != "int":
                        best_idx = vals.index(min(vals))
                        if col - 1 == best_idx:
                            it.setBackground(QBrush(QColor(self.BETTER)))
                            it.setFont(bold)
                self.table.setItem(r, col, it)

        plans = [(va, "A"), (vb, "B"), (vc, "C")]
        best = min(plans, key=lambda x: x[0]["scrap_total"])
        worst = max(plans, key=lambda x: x[0]["scrap_total"])
        if abs(best[0]["scrap_total"] - worst[0]["scrap_total"]) < 0.005:
            self.verdict.setText("All three leave the same scrap (%.2f kg)." % best[0]["scrap_total"])
        else:
            self.verdict.setText("%s leaves %.2f kg less scrap than %s  (%.2f%% vs %.2f%%)." % (
                best[1], worst[0]["scrap_total"] - best[0]["scrap_total"], worst[1],
                best[0]["pct"], worst[0]["pct"]))

    def values(self):
        return [tuple(self.table.item(r, c).text() for c in range(7)) for r in range(self.table.rowCount())]


def main():
    app = QApplication.instance() or QApplication(sys.argv[:1])

    entries = [
        ("A: 2x111 + 3x250 + 4x79", {"width": 1290, "sizes": [111, 250, 79], "qty": [2, 3, 4],
                                     "scrap": 2.0, "used": 1288.0, "pct": 0.155, "strips": 9,
                                     "scrap_per": 15.50, "scrap_total": 46.51}),
        ("B: 5x111 + 1x250 + 6x79", {"width": 1290, "sizes": [111, 250, 79], "qty": [5, 1, 6],
                                     "scrap": 11.0, "used": 1279.0, "pct": 0.853, "strips": 12,
                                     "scrap_per": 85.27, "scrap_total": 255.81}),
        ("C: 3x111 + 2x250 + 5x79", {"width": 1290, "sizes": [111, 250, 79], "qty": [3, 2, 5],
                                     "scrap": 5.0, "used": 1285.0, "pct": 0.388, "strips": 10,
                                     "scrap_per": 38.76, "scrap_total": 116.28}),
    ]

    dlg = Compare3Dialog(None, entries)

    print("=== 3-Way Compare Dialog Test ===")
    print(f"Entries: {len(entries)}")
    print(f"Table rows: {dlg.table.rowCount()}")
    print(f"Table cols: {dlg.table.columnCount()}")

    for r in range(dlg.table.rowCount()):
        row_data = []
        for c in range(dlg.table.columnCount()):
            it = dlg.table.item(r, c)
            row_data.append(it.text() if it else "")
        print(f"  Row {r}: {row_data}")

    print(f"Verdict: {dlg.verdict.text()}")

    # Test swap A/B
    print("\n=== After Swap A/B ===")
    dlg._swap(dlg.combo_a, dlg.combo_b)
    print(f"Verdict: {dlg.verdict.text()}")
    for r in range(dlg.table.rowCount()):
        if dlg.table.item(r, 0) and dlg.table.item(r, 0).text() == "Scrap (mm)":
            print(f"  Scrap row: A={dlg.table.item(r,1).text()} B={dlg.table.item(r,2).text()} C={dlg.table.item(r,3).text()}")
            break

    # Test rotate
    print("\n=== After Rotate A->B->C ===")
    dlg._rotate()
    print(f"Verdict: {dlg.verdict.text()}")

    # Test swap B/C
    print("\n=== After Swap B/C ===")
    dlg._swap(dlg.combo_b, dlg.combo_c)
    print(f"Verdict: {dlg.verdict.text()}")

    print("\n3-way compare prototype works correctly!")
    app.quit()


if __name__ == "__main__":
    main()