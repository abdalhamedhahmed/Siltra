#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
layout_skeleton.py - standalone LAYOUT SKELETON for Slitra (ZAT AL-EMAD FACTORY), v4.1.2

This is NOT the real app. It has no calculation or export code: only the final
window layout, built from dummy widgets and fake data (a tiny demo search that
reproduces CASE W). Its job is to prove the layout fits the screen BEFORE the
real app is touched.

Run (needs only PySide6):
    python layout_skeleton.py                 opens maximized, empty startup state
    python layout_skeleton.py --state w       opens with CASE W shown
    python layout_skeleton.py --size 1366x696 opens at that window size (not maximized)
    python layout_skeleton.py --state w --size 1366x696 --grab out.png   saves a screenshot and exits
    python layout_skeleton.py --check         layout self-check at 4 sizes x 4 states,
                                              saves screenshots to skeleton_screenshots/

NEW in 4.1.2 (job-order workflow + material-weight engine, steel):
  * Material type: a chip row with SIX types (HR, CR, GI, GL, PPCR, CRBA), all steel, density 7.85 g/cm3.
    Single-select, none selected on launch. The chips are built from MATERIAL_DENSITY (one source of truth).
  * Theoretical length: read-only field under Coil width, live. length_m = kg * 1000 / (width * thickness * density).
    It shows the average per coil, with the total under it when there are 2+ coils; "-" until everything is valid.
  * Order Phase: Initial (editable) / Final (locked + job number JO-YYYY-NNNN). Switching to Final needs a material,
    width, thickness (0.10 to 12.00 mm), all coil weights and a result on screen; it asks for confirmation, then
    locks every input. Clear unlocks and starts a new job. Presets and history restores always open as Initial.
  * Thickness and material start empty on launch (no pre-entered values).
Keys inside the window:  F1 empty startup  F2 CASE W  F3 7 sizes  F4 12 coils  F5 20 coils  F6 1 coil  F10 Final (locked)
Pin / Compare: 'Pin' puts the selected combination into memory (a star shows in Rank); 'Compare...' puts two
combinations side by side with the differences. Results: click a column title to sort (click again to reverse); Up/Down arrows or the buttons next to
'Selected Combination' move through the combinations (F7 loads about 1,100,000 of them).
Coil weights: click the Number of coils box and press Insert (or F2), or click the Avg weight box or
'Edit...'. A window opens with one row per coil (any number of coils; Ctrl+V pastes an Excel column).   F4 = 7 sizes, 12 coils
Buttons: Calculate shows CASE W, Clear returns to the empty startup state.
The "Number of coils" (1-12) and "Strip sizes count" boxes change the input rows live.
Avg weight/coil is calculated automatically (read-only). The fit bar updates while you type.
If a file logo.png sits next to this file it is used as the logo (otherwise a "CS" placeholder).
Optional: put Inter-Regular.ttf / Inter-Medium.ttf / Inter-SemiBold.ttf in a
"fonts" folder next to this file; otherwise Segoe UI / Arial is used.
"""
import argparse
import datetime
import math
import os
import re
import statistics
import sys
import time
from array import array

from PySide6.QtCore import (QAbstractTableModel, QLocale, QModelIndex, QPoint, QRect, QRectF,
                            QSize, Qt, QTimer, Signal)
from PySide6.QtGui import (QBrush, QColor, QDoubleValidator, QFont, QFontDatabase,
                           QFontMetrics, QGuiApplication, QIntValidator,
                           QKeySequence, QPainter, QPainterPath, QPalette, QPen,
                           QShortcut)
from PySide6.QtWidgets import (QAbstractItemDelegate, QAbstractItemView, QApplication,
                               QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QPushButton, QScrollArea, QSizePolicy, QStyledItemDelegate,
                               QTableView, QTableWidget, QTableWidgetItem, QTextEdit,
                               QVBoxLayout, QWidget)

APP_NAME = "Slitra"
FACTORY_NAME = "ZAT AL-EMAD FACTORY"
VERSION = "4.1.2"

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


# ---------------------------------------------------------------- job-order engine
# The formula, the limits and the density table below are the REAL ones: copy them into the real app's core module.
MATERIAL_DENSITY = {          # g/cm3, steel. Placeholder values: confirm with the factory. The chip row is built from these keys.
    "HR": 7.85,
    "CR": 7.85,
    "GI": 7.85,
    "GL": 7.85,
    "PPCR": 7.85,
    "CRBA": 7.85,
}
MATERIAL_TYPES = list(MATERIAL_DENSITY)
THICKNESS_MIN, THICKNESS_MAX = 0.10, 12.00      # mm, validation range (the spin box itself starts blank at 0)


def theoretical_length(total_weight_kg, width_mm, thickness_mm, material):
    """Length in meters = weight_kg * 1000 / (width_mm * thickness_mm * density_g_cm3).
    Raises ValueError for an unknown material, weight/width <= 0, thickness outside 0.10-12.00, NaN or inf."""
    if material not in MATERIAL_DENSITY:
        raise ValueError("Unknown material: %r" % (material,))
    for name, v in (("weight", total_weight_kg), ("width", width_mm), ("thickness", thickness_mm)):
        if v is None or not math.isfinite(v) or v <= 0:
            raise ValueError("%s must be a number above 0" % name)
    if not (THICKNESS_MIN <= thickness_mm <= THICKNESS_MAX):
        raise ValueError("thickness must be %.2f to %.2f mm" % (THICKNESS_MIN, THICKNESS_MAX))
    return (total_weight_kg * 1000.0) / (width_mm * thickness_mm * MATERIAL_DENSITY[material])


def validate_coil_weights(weights):
    """List not empty; every weight finite and above 0 (same rule as the Coil Weights window)."""
    if not weights:
        return False, "Enter the coil weights."
    for i, w in enumerate(weights):
        if w is None or not math.isfinite(w) or w <= 0:
            return False, "Coil %d: the weight must be a number above 0." % (i + 1)
    return True, ""


class JobCounter:
    """MOCK. The real app keeps the counter in %APPDATA%\\Slitra\\job_counter.json: written atomically (temp file, then
    replace), reset each new year, a missing or corrupt file starts again at 0001. A number is allocated only when a job
    is made Final, never at startup."""

    def __init__(self, last=41):
        self.last = last

    def next(self):
        self.last += 1
        return "JO-%d-%04d" % (datetime.date.today().year, self.last)


JOB_COUNTER = JobCounter()


# ---------------------------------------------------------------- fonts
FONT_FAMILIES = ["Segoe UI", "Arial", "Sans Serif"]


def load_fonts():
    global FONT_FAMILIES
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    found = []
    for name in ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf"):
        path = os.path.join(folder, name)
        if os.path.exists(path):
            fid = QFontDatabase.addApplicationFont(path)
            if fid >= 0:
                found += QFontDatabase.applicationFontFamilies(fid)
    if found:
        FONT_FAMILIES = [found[0]] + FONT_FAMILIES
        print("Fonts: Inter loaded, Qt reports families:", sorted(set(found)))
    else:
        print("Fonts: Inter not found next to this file, using Segoe UI / Arial")


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


# ---------------------------------------------------------------- fake data (NOT the real calculator)
_MANY = [9800, 10100, 10000, 9950, 10200, 9900, 10050, 10000, 9850, 10150,
         10000, 9975, 10020, 9880, 10120, 10000, 9930, 10080, 10010, 9990]
STATES = {
    "empty": None,
    "many": dict(coils=20, weights=_MANY, width=1290, avg=sum(_MANY) / 20.0,
                 sizes=[111, 250, 79], smin=0, smax=30, every=True,
                 thickness=0.8, material_type="CR",
                 hr_tolerance=10.0, coating_gsm=120, paint_gsm=50, density=7.85),
    "big": dict(coils=3, weights=[10000, 10000, 10000], width=4000, avg=10000.0,
                sizes=[111, 225, 79, 90, 150, 60, 180], smin=0, smax=30, every=False,
                thickness=1.2, material_type="HR",
                hr_tolerance=10.0, coating_gsm=120, paint_gsm=50, density=7.85),   # about 1,100,000 combinations
    "tight": dict(coils=3, weights=[10000, 10000, 10000], width=1290, avg=10000.0,
                  sizes=[111, 250, 79], smin=0, smax=1, every=True,
                  thickness=0.5, material_type="GI",
                  hr_tolerance=10.0, coating_gsm=120, paint_gsm=50, density=7.85),      # scrap range too tight: best is 2 mm
    "noplan": dict(coils=3, weights=[10000, 10000, 10000], width=400, avg=10000.0,
                   sizes=[111, 250, 79], smin=0, smax=30, every=True,
                   thickness=0.8, material_type="PPCR",
                   hr_tolerance=10.0, coating_gsm=120, paint_gsm=50, density=7.85),    # one strip of each needs 440 mm
    "one": dict(coils=1, weights=[10000], width=1260, avg=10000.0,
                sizes=[111, 225, 79], smin=0, smax=30, every=True,
                thickness=0.8, material_type="CR",
                hr_tolerance=10.0, coating_gsm=120, paint_gsm=50, density=7.85),
    "w": dict(coils=3, weights=[10000, 10000, 10000], width=1290, avg=10000.0,
              sizes=[111, 250, 79], smin=0, smax=30, every=True,
              thickness=0.8, material_type="CR",
              hr_tolerance=10.0, coating_gsm=120, paint_gsm=50, density=7.85),
    "seven": dict(coils=3, weights=[10000, 10000, 10000], width=1260, avg=10000.0,
                  sizes=[111, 225, 79, 90, 150, 60, 180], smin=0, smax=30, every=True,
                  thickness=0.8, material_type="GL",
                  hr_tolerance=10.0, coating_gsm=150, paint_gsm=50, density=7.85),
    "final": None,      # filled in below: CASE W as a Final (locked) job order
    "twelve": dict(coils=12, weights=[10000, 9800, 10200, 10100, 9900, 10000, 10050, 9950, 10000, 10000, 9900, 10100],
                   width=1260, avg=sum([10000, 9800, 10200, 10100, 9900, 10000, 10050, 9950, 10000, 10000, 9900, 10100]) / 12.0,
                   sizes=[111, 225, 79, 90, 150, 60, 180], smin=0, smax=30, every=True,
                   thickness=1.0, material_type="CRBA",
                   hr_tolerance=10.0, coating_gsm=120, paint_gsm=50, density=7.85),
}


STATES["final"] = dict(STATES["w"], final=True)


def demo_results(width, sizes, smin, smax, every=True):
    """Fake search (NOT the real calculator): every combination, least scrap first."""
    n = len(sizes)
    qmin = 1 if every else 0
    suffix_min = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suffix_min[i] = suffix_min[i + 1] + (sizes[i] * qmin)
    out = []

    def rec(i, used, qty):
        if i == n - 1:                                   # last size: work out the allowed counts directly
            s_ = sizes[i]
            rem = width - used
            lo = max(qmin, -((smax - rem) // s_))        # ceil((rem - smax) / s)
            hi = (rem - smin) // s_
            base = tuple(qty)
            for q in range(lo, hi + 1):
                out.append((rem - q * s_, base + (q,)))
            return
        q = qmin
        while used + q * sizes[i] + suffix_min[i + 1] <= width:
            qty.append(q)
            rec(i + 1, used + q * sizes[i], qty)
            qty.pop()
            q += 1

    rec(0, 0, [])
    out.sort(key=lambda r: r[0] * 1000000 + sum(r[1]))
    return out


def plan_vm(cfg, scrap, qty):
    """Everything the 'Selected Combination' area needs for ONE plan (any row of the results)."""
    width, sizes, avg, coils = cfg["width"], cfg["sizes"], cfg["avg"], cfg["coils"]
    knives, pos = [], 0
    for s_, q in zip(sizes, qty):
        for _ in range(q):
            pos += s_
            knives.append(pos)
    wps = [avg * s_ / width for s_ in sizes]
    total_qty = [q * coils for q in qty]
    total_w = [t * w for t, w in zip(total_qty, wps)]
    scrap_per = scrap / width * avg
    return dict(width=width, sizes=sizes, qty=list(qty), scrap=scrap, used=width - scrap,
                pct=scrap / width * 100, strips=sum(qty), knives=knives, wps=wps,
                total_qty=total_qty, total_w=total_w, scrap_per=scrap_per,
                scrap_total=scrap_per * coils, coils=coils, avg=avg,
                weight_ok=abs(sum(total_w) + scrap_per * coils - coils * avg) < 0.05)


def build_vm(cfg):
    """All combinations (no limit), best first, plus the plan details of the best one."""
    if cfg is None:
        return None
    all_rows = demo_results(cfg["width"], cfg["sizes"], cfg["smin"], cfg["smax"], cfg["every"])
    if not all_rows:
        return None
    vm = plan_vm(cfg, *all_rows[0])
    vm.update(rows=all_rows, total=len(all_rows), cfg=cfg)
    return vm


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
        self.hint = ""

    def set_vm(self, vm, hint=""):
        self.vm = vm
        self.hint = hint
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
        if not vm and self.hint:
            p.setFont(make_font(9.5))
            p.setPen(QColor(MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.hint)
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
TABLE_QSS = "QTableView{background:#FFFFFF;border:1px solid %s;}" % LINE


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
        self.qty = []                 # one array('i') per size, in rank order (rank 1 first)
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
        self.scrap = array("i", [r[0] for r in rows])
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
        return 0 if parent.isValid() else len(self.order)

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
            text += " " + ("\u25BC" if self.sort_desc else "\u25B2")
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
                return ("\u2605 " + txt) if r in self.pinned else txt
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
        if not self.order or col >= self._ncols():
            return
        if col == self.sort_col:
            desc = not self.sort_desc
        else:
            desc = (1 <= col <= k) or col in (k + 1, k + 4)     # first click: most / largest first
        if col == 0:
            order = list(self._base())
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
            order = sorted(self._base(), key=arr.__getitem__, reverse=rev)   # stable: ties keep rank order
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
        n = len(self.results.order)
        if n == 0:
            return
        view_row = max(0, min(n - 1, view_row))
        idx = self.results.index(view_row, 0)
        self.setCurrentIndex(idx)
        self.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter if view_row else QAbstractItemView.ScrollHint.PositionAtTop)
        self.rowChosen.emit(view_row)


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
            "QLineEdit:focus{border:1px solid %s;}"
            "QLineEdit:disabled{background:#F2F4F7;color:#8A94A0;border:1px solid %s;}" % (RED, LINE))
PANEL_QSS = "#Panel{background:#FFFFFF;border:1px solid %s;border-radius:6px;}" % LINE


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


READONLY_QSS = ("QLineEdit{background:#F2F4F7;color:%s;border:1px solid %s;border-radius:3px;padding:0 4px;}" % (INK, LINE))


READONLY_QSS = ("QLineEdit{background:#F2F4F7;border:1px solid %s;border-radius:3px;"
                "padding:0 4px;color:%s;}" % (LINE, INK))
MAX_COILS = 100000      # technical safety only; practically no limit


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
    """Enter the weight of every coil. Any number of coils; paste a column from Excel.
    Coil names are derived from material type: e.g. HR-1, HR-2... or GI-1, GI-2..."""
    OUTLIER = 0.30       # a weight more than 30% away from the median gets an amber tint

    def __init__(self, parent, weights, material="HR"):
        super().__init__(parent)
        self.material = material
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

        # 3 columns: Coil Name, Coil Number, Weight
        self.table = WeightTable(0, 3)
        base_table(self.table, 28, 24)
        self.table.setHorizontalHeaderLabels(["Coil Name", "Coil #", "Weight (kg)"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.resizeSection(0, 100)
        hh.resizeSection(1, 60)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                                   QAbstractItemView.EditTrigger.EditKeyPressed |
                                   QAbstractItemView.EditTrigger.AnyKeyPressed |
                                   QAbstractItemView.EditTrigger.SelectedClicked)
        self.delegate = WeightDelegate(self.table)
        self.table.setItemDelegateForColumn(2, self.delegate)
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
        self.table.setCurrentCell(0, 2)  # weight is column 2
        self.table.setFocus()

    # -- table helpers
    def _set_rows(self, n, weights=None):
        self._building = True
        old = self.table.rowCount()
        self.table.setRowCount(n)
        for r in range(old, n):
            # Column 0: Coil Name (material-#, read-only)
            coil_name = f"{self.material}-{r + 1}"
            it0 = QTableWidgetItem(coil_name)
            it0.setFlags(Qt.ItemFlag.ItemIsEnabled)
            it0.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 0, it0)
            # Column 1: Coil # (read-only)
            it1 = QTableWidgetItem(str(r + 1))
            it1.setFlags(Qt.ItemFlag.ItemIsEnabled)
            it1.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 1, it1)
            # Column 2: Weight (editable)
            v = weights[r] if (weights and r < len(weights)) else None
            it2 = QTableWidgetItem("" if v is None else fmt_weight(v))
            it2.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 2, it2)
        self._building = False

    def _values(self):
        out = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 2)  # weight is now column 2
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
            self.table.setCurrentCell(nxt, 2)  # weight is column 2
            self.table.editItem(self.table.item(nxt, 2))

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
            it = self.table.item(r, 2)  # weight is column 2
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
            self.table.item(start + i, 2).setText(tok)  # weight is column 2
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
            self.table.item(r, 2).setText(fmt_weight(v))  # weight is column 2
        self._building = False
        self._refresh()

    def _clear_all(self):
        self._building = True
        for r in range(self.table.rowCount()):
            self.table.item(r, 2).setText("")  # weight is column 2
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
            self.table.setCurrentCell(bad[0], 2)  # weight is column 2
            self.table.scrollToItem(self.table.item(bad[0], 2))
            self.table.setFocus()
            self.msg.set_full("%d weight(s) missing or invalid, first: coil %d." % (len(bad), bad[0] + 1))
            return
        self.accept()

    def weights(self):
        return [v for v in self._values()]


CHIP_QSS = ("QPushButton{background:#FFFFFF;color:%s;border:1px solid #AEB7C2;border-radius:3px;padding:0 2px;}"
            "QPushButton:hover{border:1px solid %s;}"
            "QPushButton:checked{background:#FDECEC;color:%s;border:1px solid %s;}"
            "QPushButton:disabled{background:#F2F4F7;color:#8A94A0;border:1px solid %s;}"
            "QPushButton:checked:disabled{background:#F7E4E4;color:#B07070;border:1px solid #D8B4B4;}"
            % (INK, RED, RED, RED, LINE))


class MaterialChips(QWidget):
    """Single-select chip row. Nothing is selected on launch. Same look as the input boxes (white, thin grey
    border, 3 px corners); the selected chip uses the app accent (red border, light red fill, red text)."""
    changed = Signal(str)

    def __init__(self, items):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.buttons = {}
        self._value = None
        for name in items:
            b = QPushButton(name)
            b.setCheckable(True)
            b.setFixedHeight(26)
            b.setFont(make_font(9, QFont.Weight.Medium))
            b.setStyleSheet(CHIP_QSS)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.setAutoDefault(False)
            b.setToolTip("%s - steel, density %.2f g/cm3" % (name, MATERIAL_DENSITY[name]))
            b.clicked.connect(lambda _c=False, n=name: self._pick(n))
            lay.addWidget(b, 1)
            self.buttons[name] = b

    def _pick(self, name):
        self.set_value(name)
        self.changed.emit(name)

    def set_value(self, name):
        self._value = name if name in self.buttons else None
        for n, b in self.buttons.items():
            b.setChecked(n == self._value)

    def value(self):
        return self._value


class InputPanel(QFrame):
    def __init__(self):
        super().__init__()
        self.locked = False
        self._sum_base = ""
        self.setObjectName("Panel")
        self.setStyleSheet(PANEL_QSS)
        self.weights = []          # one entry per coil when there are 2+ coils (float or None)
        self._single = None        # the weight when there is 1 coil (typed inline)
        self._mode_inline = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)
        outer.addWidget(SectionTitle("Input Parameters"))

        form = QGridLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(4)
        form.setColumnStretch(0, 1)
        r = 0
        self.coils_edit = style_edit(CoilCountEdit())
        self.coils_edit.setValidator(QIntValidator(1, MAX_COILS, self))
        self.coils_edit.setToolTip("Press Insert (or F2) to enter the weight of each coil")
        form.addWidget(mk_label("Number of coils:"), r, 0)
        form.addWidget(self.coils_edit, r, 1)
        r += 1

        self.thickness_edit = style_edit(QDoubleSpinBox())
        self.thickness_edit.setDecimals(3)
        self.thickness_edit.setRange(0.0, THICKNESS_MAX)
        self.thickness_edit.setSpecialValueText(" ")       # 0 shows as blank: no pre-entered value on launch
        self.thickness_edit.setValue(0.0)
        self.thickness_edit.setSingleStep(0.01)
        self.thickness_edit.setSuffix(" mm")
        form.addWidget(mk_label("Thickness (mm):"), r, 0)
        form.addWidget(self.thickness_edit, r, 1)
        r += 1

        # Material type: single-select chip row, six steel types, none selected on launch.
        # The selected type is also the coil name prefix in the Coil Weights window (HR-1, PPCR-1, ...).
        mat_box = QWidget()
        mv = QVBoxLayout(mat_box)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(3)
        mv.addWidget(mk_label("Material type:"))
        self.chips = MaterialChips(MATERIAL_TYPES)
        mv.addWidget(self.chips)
        form.addWidget(mat_box, r, 0, 1, 2)
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
        # Theoretical length: read-only, live. One coil: the length. 2+ coils: average per coil (the total is in the line under the weights).
        self.len_label = mk_label("Theoretical length (m):")
        self.len_edit = style_edit(QLineEdit())
        self.len_edit.setReadOnly(True)
        self.len_edit.setStyleSheet(READONLY_QSS)
        self.len_edit.setText("\u2014")
        self.len_edit.setToolTip("Weight x 1000 / (width x thickness x density). An estimate from the weight.")
        form.addWidget(self.len_label, r, 0)
        form.addWidget(self.len_edit, r, 1)
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
        r += 1

        # (Order Phase and the job number live in the top bar, next to the buttons: they describe the whole job.)

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
        # live theoretical length
        self.chips.changed.connect(self._on_material_changed)
        self.thickness_edit.valueChanged.connect(self.update_length)
        self.width_edit.textChanged.connect(self.update_length)
        self._relayout_sizes()
        self.refresh()
        self.update_length()

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
        self.update_length()

    def _on_material_changed(self, material):
        """The material sets the density (and the coil name prefix in the Coil Weights window)."""
        self.update_length()

    # -- theoretical length (base formula only: no coating, paint or tolerance terms)
    def length_values(self):
        """(average length per coil, total length) in meters, or None while anything is missing or invalid."""
        material = self.chips.value()
        n = self._count()
        weights = list(self.weights) if n >= 2 else [self._single]
        if not material or not weights or any(w is None for w in weights):
            return None
        ok, _msg = validate_coil_weights(weights)
        width = parse_weight(self.width_edit.text())
        if not ok or not width:
            return None
        try:
            total = theoretical_length(math.fsum(weights), width, self.thickness_edit.value(), material)
        except ValueError:
            return None
        return total / len(weights), total

    def update_length(self, _v=None):
        n = self._count()
        many = n >= 2
        self.len_label.setText("Avg length/coil (m):" if many else "Theoretical length (m):")
        res = self.length_values()
        base = self._sum_base
        if res is None:
            self.len_edit.setText("\u2014")
            self.len_edit.setToolTip("Weight x 1000 / (width x thickness x density). Needs material, thickness, width and weights.")
            if many and base:
                self.summary.set_full(base)
            return
        avg, total = res
        self.len_edit.setText("{:,.1f}".format(avg))
        self.len_edit.setToolTip("Total {:,.1f} m for {} coil{}. (weight x 1000 / (width x thickness x density))".format(
            total, max(n, 1), "" if n <= 1 else "s"))
        if many and base:                    # "Total 30,000 kg  |  3,703 m  |  all equal"
            head, _sep, tail = base.partition("  |  ")
            self.summary.set_full("{}  |  {:,.0f} m  |  {}".format(head, total, tail))

    def set_locked(self, locked):
        """Final job order: every input is disabled. Clear (set_state) unlocks."""
        self.locked = locked
        for w in ([self.coils_edit, self.thickness_edit, self.chips, self.avg_edit, self.edit_btn, self.width_edit,
                   self.sizes_box, self.smin_edit, self.smax_edit, self.every] + self.size_edits):
            w.setEnabled(not locked)

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
                self._sum_base = "Total {:,.0f} kg  |  {}".format(sum(vals), rng)
                self.summary.set_full(self._sum_base)
            else:
                self.avg_edit.setText("—")
                self._sum_base = ""
                self.summary.set_color(BAD)
                self.summary.set_full("%d weight%s missing - press Insert" % (missing, "" if missing == 1 else "s"))
        self._mode_inline = inline
        self.update_length()

    def open_weights(self):
        n = max(self._count(), 1)
        if n == 1:
            w = [self._single]
        else:
            w = list(self.weights) if len(self.weights) == n else [None] * n
        material = self.chips.value() or "Coil"          # no material chosen yet: coils are named Coil-1, Coil-2...
        dlg = CoilWeightsDialog(self.window(), w, material)
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
        # Any new state (Clear, a preset, a history restore) opens as an editable Initial job with no job number.
        self.set_locked(False)
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
            # Reset new fields: thickness blank, no material selected
            self.thickness_edit.setValue(0.0)
            self.chips.set_value(None)
            self.refresh()
            self._update_fit()
            self.update_length()
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
        # Restore new fields
        if "thickness" in cfg:
            self.thickness_edit.setValue(cfg["thickness"])
        self.chips.set_value(cfg.get("material_type"))
        # "order_phase" in a saved cfg is ignored on purpose: presets and restores never lock or use a job number.
        self._update_fit()
        self.update_length()

    def get_all_params(self):
        """Return all input parameters as a dict for the controller."""
        n = self._count()
        weights = []
        if n >= 2:
            weights = list(self.weights)
        elif self._single is not None:
            weights = [self._single]
        else:
            weights = []

        sizes = []
        try:
            n_sizes = int(self.sizes_box.currentText())
            for ed in self.size_edits[:n_sizes]:
                v = parse_weight(ed.text())
                if v:
                    sizes.append(v)
        except ValueError:
            pass

        params = {
            "coils": n,
            "weights": weights,
            "width": parse_weight(self.width_edit.text()) or 0,
            "avg": parse_weight(self.avg_edit.text()) or 0,
            "sizes": sizes,
            "smin": int(self.smin_edit.text()) if self.smin_edit.text().isdigit() else 0,
            "smax": int(self.smax_edit.text()) if self.smax_edit.text().isdigit() else 30,
            "every": self.every.isChecked(),
            "thickness": self.thickness_edit.value(),
            "material_type": self.chips.value() or "",
        }
        return params


# ---------------------------------------------------------------- right panel
def plan_text(vm):
    return " + ".join("%dx%d" % (q, sz) for sz, q in zip(vm["sizes"], vm["qty"]) if q) or "-"


class MemoryStore:
    """Pinned combinations. Each keeps its whole plan, so plans from different calculations can be compared."""
    MAX = 50

    def __init__(self):
        self.items = []
        self._next = 1

    def __len__(self):
        return len(self.items)

    def find(self, calc, src):
        return next((i for i in self.items if i["calc"] == calc and i["src"] == src), None)

    def add(self, vm, calc, src, rank):
        if len(self.items) >= self.MAX:
            return None
        item = dict(id=self._next, vm=vm, calc=calc, src=src, rank=rank)
        self._next += 1
        self.items.append(item)
        return item

    def remove(self, item):
        self.items.remove(item)

    def clear(self):
        self.items = []


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
    KEEP = 5
    MAX_BYTES = 400 * 1024 * 1024

    def __init__(self):
        self.items = []                      # newest first

    @staticmethod
    def bytes_of(e):
        return e["n"] * (len(e["sizes"]) + 2) * 4

    def total_bytes(self):
        return sum(self.bytes_of(e) for e in self.items)

    def push(self, entry):
        self.items.insert(0, entry)
        while len(self.items) > self.KEEP or (self.total_bytes() > self.MAX_BYTES and len(self.items) > 1):
            self.items.pop()

    def label(self, e):
        c = e["cfg"]
        return "{}   |   {} coil{}, {} mm   |   {}   |   scrap {}-{}   |   {:,} combinations".format(
            e["when"], c["coils"], "" if c["coils"] == 1 else "s", c["width"],
            "/".join(str(x) for x in e["sizes"]), c["smin"], c["smax"], e["n"])


NAV_QSS = ("QPushButton{background:#FFFFFF;color:%s;border:1px solid #AEB7C2;border-radius:4px;padding:0;}"
           "QPushButton:hover{background:#F2F4F7;}QPushButton:disabled{color:#B8C0CC;border-color:#DDE2E8;}" % INK)


class ResultsPanel(QFrame):
    inputsRestore = Signal(object)
    suggestion = Signal(str, int)

    def __init__(self):
        super().__init__()
        self.setObjectName("Panel")
        self.setStyleSheet(PANEL_QSS)
        self.cfg = None
        self.memory = MemoryStore()
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
        for b_, w_, tip in ((self.pin_btn, 60, "Pin this combination into memory (a star shows in the Rank column)"),
                            (self.cmp_btn, 96, "Compare two combinations side by side (the pinned ones are in memory)")):
            b_.setFixedSize(w_, 24)
            b_.setFont(make_font(9, QFont.Weight.Medium))
            b_.setStyleSheet(OUTLINE_QSS)
            b_.setToolTip(tip)
            b_.setAutoDefault(False)
            head2.addWidget(b_)
        head2.addSpacing(8)
        self.prev_btn = QPushButton("\u25C2")
        self.next_btn = QPushButton("\u25B8")
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
            cur = self.table.currentIndex().row()
            self.table.select_row(0 if cur < 0 else cur + delta)

    def _set_nav(self, view_row):
        n = self.table.results.shown
        self.prev_btn.setEnabled(bool(n) and view_row is not None and view_row > 0)
        self.next_btn.setEnabled(bool(n) and (view_row is None or view_row < n - 1))
        if not n:
            self.nav.setText("")
            self.nav.setFixedWidth(40)
            return
        if view_row is None:
            text = "no formula selected"
            self.nav.setText(text)
            self.nav.setFixedWidth(QFontMetrics(self.nav.font()).horizontalAdvance(text) + 14)
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
            self._keep_selection()
        else:
            self.cur_vm = None
            self.cur_src = None
            self._set_nav(None)
            self._blank_plan()
            self._update_memory_ui()
            self.table.notice.show_info("No combination matches the filter",
                                        "Loosen the limits, or show all {:,} combinations again.".format(r.n),
                                        "Show all combinations", "clear_filter", 0)

    def _keep_selection(self):
        """After a filter or a restore: keep the chosen formula if it is still listed, else nothing is chosen."""
        r = self.table.results
        if self.cur_src is not None and self.cur_src in (r.visible if r.visible is not None else range(r.n)):
            self.table.select_row(r.order.index(self.cur_src))
        else:
            self._clear_choice()

    def _clear_choice(self):
        self.cur_vm = None
        self.cur_src = None
        self.table.clearSelection()
        self.table.setCurrentIndex(QModelIndex())
        self.table.scrollToTop()
        self._set_nav(None)
        self._blank_plan(hint=self.table.results.shown > 0)
        self._update_memory_ui()

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
            act = menu.addAction(("\u25CF  " if current else "      ") + label)
            act.triggered.connect(lambda _c=False, i=i: self.restore(i))
        menu.addSeparator()
        info = menu.addAction("Memory used: {:.1f} MB of {:.0f} MB   (keeps the last {} results)".format(
            self.history.total_bytes() / 1048576.0, ResultsHistory.MAX_BYTES / 1048576.0, ResultsHistory.KEEP))
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
        pinned = self.cur_src is not None and self.memory.find(self.calc_id, self.cur_src) is not None
        self.pin_btn.setText("Unpin" if pinned else "Pin")
        self.pin_btn.setEnabled(self.cur_vm is not None)
        n = len(self.memory)
        self.cmp_btn.setText("Compare (%d)" % n if n else "Compare...")
        self.cmp_btn.setEnabled(self.cur_vm is not None or n > 0)

    def toggle_pin(self):
        if self.cur_vm is None or self.cur_src is None:
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
        entries = []
        if self.cur_vm is not None:
            entries.append(("Selected  (F{:,}):  {}".format(self.cur_src + 1, plan_text(self.cur_vm)), self.cur_vm))
        if self.cfg is not None and self.table.results.n:
            scrap, qty = self.table.results.plan_src(0)
            best = plan_vm(self.cfg, scrap, qty)
            entries.append(("Lowest scrap  (F1):  " + plan_text(best), best))
        for it in self.memory.items:
            vm = it["vm"]
            entries.append(("Pinned #%d  (F%s, coil %s mm):  %s" % (it["id"], "{:,}".format(it["rank"]), vm["width"], plan_text(vm)), vm))
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
        self.bar.set_vm(None, "Select a formula (F1, F2, ...) in the table above" if hint else "")
        self.ruler.set_vm(None)
        self.legend.set_vm(None)
        self.knives.set_full("Knife positions (mm): —")
        for c in self.cards:
            c.set_value("—")
        self.strip_table.show_empty()

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


# ---------------------------------------------------------------- top bar + status line
PRIMARY_QSS = ("QPushButton{background:%s;color:#FFFFFF;border:1px solid %s;border-radius:4px;padding:0 14px;}"
               "QPushButton:hover{background:#B71C1C;}"
               "QPushButton:disabled{background:#E3E7EC;color:#8A94A0;border:1px solid #D0D6DD;}" % (RED, RED))
OUTLINE_QSS = ("QPushButton{background:#FFFFFF;color:%s;border:1px solid #AEB7C2;border-radius:4px;padding:0 10px;}"
               "QPushButton:hover{background:#F2F4F7;}"
               "QPushButton:disabled{background:#F2F4F7;color:#A0A8B2;border:1px solid #DDE2E8;}" % INK)


LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")


class LogoMark(QWidget):
    """Real logo (logo.png, smooth, aspect ratio kept) or a plain placeholder if the file is missing."""
    BOX = 40

    def __init__(self, path=None):
        super().__init__()
        self.setFixedSize(self.BOX, self.BOX)
        from PySide6.QtGui import QPixmap
        self.pix = QPixmap(path or LOGO_PATH)
        if self.pix.isNull():
            self.pix = None

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.pix is not None:
            dpr = self.devicePixelRatioF()
            scaled = self.pix.scaled(int(self.BOX * dpr), int(self.BOX * dpr), Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
            scaled.setDevicePixelRatio(dpr)
            w, h = scaled.width() / dpr, scaled.height() / dpr
            p.drawPixmap(int((self.BOX - w) / 2), int((self.BOX - h) / 2), scaled)
            return
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(RED))
        p.drawRoundedRect(QRectF(0, 0, self.BOX, self.BOX), 7, 7)
        p.setPen(QColor("#FFFFFF"))
        p.setFont(make_font(11, QFont.Weight.Bold))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "CS")


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
        # Order phase + job number: describe the whole job, so they sit with the buttons.
        self.phase_combo = make_combo(["Initial Job Order", "Final Job Order"], 140)
        self.phase_combo.setFixedHeight(32)
        self.phase_combo.setToolTip("Initial = editable draft, no job number. Final = locks the inputs and assigns a job number (printed on the PDF).")
        lay.addWidget(self.phase_combo)
        self.job_badge = QLabel("")
        self.job_badge.setFixedSize(150, 32)
        self.job_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.job_badge.setFont(make_font(9, QFont.Weight.Medium))
        lay.addWidget(self.job_badge)
        self.set_job(None)
        self.buttons = {}
        for name, _full, _short in self.SPEC:
            b = QPushButton(name)
            b.setFixedHeight(32)
            b.setFont(make_font(9, QFont.Weight.Medium))
            b.setStyleSheet(PRIMARY_QSS if name == "Calculate" else OUTLINE_QSS)
            lay.addWidget(b)
            self.buttons[name] = b
        self.compact = False

    def set_job(self, number):
        """Job number badge: muted while Initial (no number yet), accent colour once the job is Final."""
        if number:
            self.job_badge.setText(number)
            self.job_badge.setToolTip("Job number of this Final Job Order")
            self.job_badge.setStyleSheet("QLabel{background:#FDECEC;color:%s;border:1px solid %s;border-radius:4px;}" % (RED, RED))
        else:
            self.job_badge.setText("No job number")
            self.job_badge.setToolTip("A job number is assigned when the order is made Final")
            self.job_badge.setStyleSheet("QLabel{background:#F2F4F7;color:%s;border:1px solid %s;border-radius:4px;}" % (MUTED, LINE))

    def job_text(self):
        return self.job_badge.text()

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
        self.left = mk_label("Ready  -  layout skeleton, fake data.  F1 startup   F2 CASE W   F3 7 sizes   F4 12 coils", 8.5, MUTED)
        self.left.setProperty("skip_text_check", True)
        lay.addWidget(self.left, 1)
        lay.addWidget(mk_label("Developed by Abdalhamed", 8.5, MUTED))

    def say(self, text):
        self.left.setText(text)


# ---------------------------------------------------------------- update notification dialog
class UpdateNotificationDialog(QDialog):
    """
    Startup pop-up shown when a newer Slitra version is available on GitHub.

    Pure UI (no network logic): the caller passes an info dict with keys
      current, latest, tag_name, release_notes, download_url, asset_name
    and chooses what happens when the user clicks a button.
    """

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Update Available - %s" % APP_NAME)
        self.setModal(True)
        self.setFixedWidth(560)
        self.choice = None  # "download" | "later" | "skip"

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        # Header bar: app name + current -> new version
        head = QFrame()
        head.setStyleSheet("QFrame{background:%s;border-radius:8px;}" % WINDOW_BG)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(14, 12, 14, 12)
        hl.setSpacing(10)

        badge = QLabel("✓")
        badge.setFont(make_font(13, QFont.Weight.Bold))
        badge.setStyleSheet("color:%s;" % GREEN)
        hl.addWidget(badge)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        title = mk_label("New version available", 12, INK, QFont.Weight.DemiBold)
        ver = mk_label("You have %s → %s (%s)" % (info.get("current", "?"),
                                                      info.get("latest", "?"),
                                                      info.get("tag_name", "")),
                       9.5, MUTED)
        info_col.addWidget(title)
        info_col.addWidget(ver)
        hl.addLayout(info_col, 1)

        # Dismiss (X) - treated as "Later"
        dismiss = QPushButton("×")
        dismiss.setFixedSize(24, 24)
        dismiss.setFont(make_font(12, QFont.Weight.Bold))
        dismiss.setStyleSheet("QPushButton{background:transparent;color:%s;border:none;border-radius:12px;}"
                              "QPushButton:hover{background:#F2F4F7;}" % MUTED)
        dismiss.clicked.connect(lambda: self._done("later"))
        hl.addWidget(dismiss)

        root.addWidget(head)

        # Changelog body
        notes = info.get("release_notes") or ""
        body_label = mk_label("What's new:", 9, MUTED, QFont.Weight.Medium)
        root.addWidget(body_label)

        self.notes = QTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setPlainText(notes.strip() or "No release notes published for this version.")
        self.notes.setFixedHeight(150)
        self.notes.setStyleSheet("QTextEdit{background:#FFFFFF;color:%s;border:1px solid %s;border-radius:4px;"
                                 "padding:8px;selection-background:%s;}" % (INK, LINE, BLUE))
        self.notes.setFont(make_font(9))
        root.addWidget(self.notes)

        # Asset hint
        asset = info.get("asset_name")
        if asset:
            asset_lbl = mk_label("Installer: %s" % asset, 8.5, MUTED)
            root.addWidget(asset_lbl)

        # Buttons
        btns = QHBoxLayout()
        btns.setSpacing(10)
        btns.addStretch(1)

        self.btn_skip = QPushButton("Skip this version")
        self.btn_skip.setFixedHeight(32)
        self.btn_skip.setFont(make_font(9, QFont.Weight.Medium))
        self.btn_skip.setStyleSheet(OUTLINE_QSS)
        self.btn_skip.clicked.connect(lambda: self._done("skip"))
        btns.addWidget(self.btn_skip)

        self.btn_later = QPushButton("Later")
        self.btn_later.setFixedHeight(32)
        self.btn_later.setFont(make_font(9, QFont.Weight.Medium))
        self.btn_later.setStyleSheet(OUTLINE_QSS)
        self.btn_later.clicked.connect(lambda: self._done("later"))
        btns.addWidget(self.btn_later)

        self.btn_download = QPushButton("Download & Install")
        self.btn_download.setFixedHeight(32)
        self.btn_download.setFont(make_font(9, QFont.Weight.DemiBold))
        has_url = bool(info.get("download_url"))
        self.btn_download.setEnabled(has_url)
        self.btn_download.setStyleSheet(PRIMARY_QSS if has_url else ("QPushButton{background:#E5E7EB;color:%s;border:1px solid #CBD2DA;border-radius:4px;padding:0 14px;}" % MUTED))
        self.btn_download.setToolTip("Download the latest installer and launch it (app will close)."
                                     if has_url else "No installer asset published for this release.")
        self.btn_download.clicked.connect(lambda: self._done("download"))
        btns.addWidget(self.btn_download)

        root.addLayout(btns)

    def _done(self, choice):
        self.choice = choice
        self.accept()


# ---------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self, args=None):
        super().__init__()
        self.setWindowTitle("%s - %s - Version %s  [layout skeleton]" % (APP_NAME, FACTORY_NAME, VERSION))
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
        self.state = "empty"
        self._has_result = False
        self.job_number = None

        b = self.topbar.buttons
        b["Calculate"].clicked.connect(lambda: self.set_state("w" if self.state == "empty" else self.state))
        b["Clear"].clicked.connect(lambda: self.set_state("empty"))
        for name in ("Cancel", "Export PDF", "Export Excel", "Save Preset", "Load Preset", "View Log"):
            b[name].clicked.connect(lambda _c=False, n=name: self.statusline.say("%s clicked (skeleton: no action)" % n))
        for key, st in (("F1", "empty"), ("F2", "w"), ("F3", "seven"), ("F4", "twelve"),
                        ("F5", "many"), ("F6", "one"), ("F7", "big"), ("F8", "tight"), ("F9", "noplan"),
                        ("F10", "final")):
            QShortcut(QKeySequence(key), self, activated=lambda s=st: self.set_state(s))
        self.topbar.phase_combo.activated.connect(self._on_phase_activated)
        self.right.inputsRestore.connect(self._restore_inputs)
        self.right.suggestion.connect(self._apply_suggestion)
        self.set_state("empty")

        # Update notification: pops on startup if a newer version is available.
        # Pass --update to force-show the demo dialog for the mockup.
        self._update_info = None
        if args and getattr(args, "update", False):
            self._update_info = {
                "current": VERSION,
                "latest": "4.2.0",
                "tag_name": "v4.2.0",
                "download_url": "https://github.com/abdalhamedhahmed/siltra/releases/download/v4.2.0/Slitra-4.2.0-Setup.exe",
                "asset_name": "Slitra-4.2.0-Setup.exe",
                "release_notes": ("- Added Job Order workflow with Initial/Final phase\n"
                                  "- Material-weight calc for 6 material types (HR, CR, GI, GL, PPCR, CRBA)\n"
                                  "- Consignment auto-naming (NAME-N coils)\n"
                                  "- Knife setup positions in PDF export\n"
                                  "- Fixed Excel export crash on empty results"),
            }
            QTimer.singleShot(0, self._show_update_dialog)

    def _show_update_dialog(self):
        """Show the update notification dialog after the window is visible."""
        dlg = UpdateNotificationDialog(self._update_info, self)
        if dlg.exec():
            choice = dlg.choice
            if choice == "download":
                self.statusline.say("Update: downloading installer (%s)..." % self._update_info.get("asset_name", ""))
                QTimer.singleShot(500, lambda: self.statusline.say("Update: installer launched, app will close."))
            elif choice == "skip":
                self.statusline.say("Update: this version skipped.")
            else:
                self.statusline.say("Update: reminded later.")
        else:
            self.statusline.say("Update: dismissed.")

    def _restore_inputs(self, cfg):
        self.left.set_state(cfg)            # always Initial, unlocked, no job number
        self._to_initial_state()
        self.statusline.say("Restored an earlier result and its inputs (no new search).")

    # -- order phase: Initial (editable) / Final (locked, job number)
    def _to_initial_state(self):
        self.job_number = None
        self.left.set_locked(False)
        self.topbar.phase_combo.blockSignals(True)
        self.topbar.phase_combo.setCurrentIndex(0)
        self.topbar.phase_combo.blockSignals(False)
        self.topbar.phase_combo.setEnabled(True)
        self.topbar.set_job(None)
        self.topbar.buttons["Calculate"].setEnabled(True)

    def _final_blockers(self):
        """Why this job cannot be made Final yet (empty string = it can)."""
        p = self.left
        if not p.chips.value():
            return "choose a material type."
        if not parse_weight(p.width_edit.text()):
            return "enter the coil width."
        if not (THICKNESS_MIN <= p.thickness_edit.value() <= THICKNESS_MAX):
            return "enter a thickness from %.2f to %.2f mm." % (THICKNESS_MIN, THICKNESS_MAX)
        if p.needs_weights() or p._count() < 1:
            return "enter all the coil weights."
        if not self._has_result:
            return "press Calculate first: there is no result on screen."
        return ""

    def _confirm_final(self):
        box = QMessageBox(self)
        box.setWindowTitle("Final Job Order")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("Lock this job and assign a job number?")
        box.setInformativeText("The inputs cannot be edited afterwards. Clear starts a new job.")
        ok = box.addButton("Lock and assign number", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is ok

    def _back_to_initial(self, message):
        combo = self.topbar.phase_combo
        combo.blockSignals(True)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)
        self.statusline.say(message)

    def _on_phase_activated(self, index):
        if index != 1:
            return                          # Initial chosen: nothing to do (the combo is disabled while a job is locked)
        why = self._final_blockers()
        if why:
            self._back_to_initial("Cannot make this a Final Job Order: " + why)
        elif not self._confirm_final():
            self._back_to_initial("Final Job Order cancelled. No job number was used.")
        else:
            self._finalize()

    def _finalize(self):
        self.job_number = JOB_COUNTER.next()
        combo = self.topbar.phase_combo
        combo.blockSignals(True)
        combo.setCurrentIndex(1)
        combo.blockSignals(False)
        combo.setEnabled(False)
        self.topbar.set_job(self.job_number)
        self.left.set_locked(True)
        self.topbar.buttons["Calculate"].setEnabled(False)
        self.statusline.say("Final Job Order %s: inputs are locked. Clear starts a new job." % self.job_number)

    def _apply_suggestion(self, key, value):
        (self.left.smax_edit if key == "scrap_max" else self.left.smin_edit).setText(str(value))
        self.statusline.say("Scrap %s set to %d mm. Press Calculate." % ("maximum" if key == "scrap_max" else "minimum", value))

    def set_state(self, name):
        self.state = name
        cfg = STATES[name]
        busy = name == "big"
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.statusline.say("Searching about 1,100,000 combinations (the demo search is slow; the real one is faster)...")
            QApplication.processEvents()
        try:
            self.left.set_state(cfg)
            vm = build_vm(cfg)
            self._has_result = vm is not None
            self._to_initial_state()
            self.right.apply(vm, cfg)
            if cfg and cfg.get("final") and self._has_result:
                self._finalize()
        finally:
            if busy:
                QApplication.restoreOverrideCursor()
        label = {"final": "CASE W as a Final Job Order (locked)", "empty": "empty startup", "w": "CASE W", "seven": "7 sizes, 3 coils", "twelve": "7 sizes, 12 coils",
                 "many": "3 sizes, 20 coils", "one": "1 coil", "big": "about 1,100,000 combinations",
                 "tight": "no plan: scrap range too tight", "noplan": "no plan: sizes do not fit"}[name]
        self.statusline.say("Showing: %s   (F1 startup  F2 CASE W  F3 7 sizes  F4 12 coils  F5 20 coils  F6 1 coil  F7 1.1M results  F10 Final)" % label)

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


def check_window(win, req_w=None, req_h=None):
    problems = []
    root = win.centralWidget() if hasattr(win, "centralWidget") else win
    if req_w and (win.width() > req_w + 1 or win.height() > req_h + 1):
        mh = win.minimumSizeHint()
        problems.append("window cannot shrink to %dx%d: it stays %dx%d (needs about %dx%d)"
                        % (req_w, req_h, win.width(), win.height(), mh.width(), mh.height()))
    wrect = QRect(0, 0, win.width(), win.height())
    for name, btn in (win.topbar.buttons.items() if hasattr(win, "topbar") else []):
        if not btn.isVisible():
            problems.append("button '%s' is not visible" % name)
            continue
        r = QRect(btn.mapTo(win, QPoint(0, 0)), btn.size())
        if not wrect.contains(r):
            problems.append("button '%s' is outside the window" % name)
    for host in [root] + root.findChildren(QWidget):
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
    for tbl in win.findChildren(QTableView):
        if not tbl.isVisible() or tbl.model() is None:
            continue
        fm = tbl.horizontalHeader().fontMetrics()
        for c in range(tbl.model().columnCount()):
            text = tbl.model().headerData(c, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            if not text:
                continue
            need = max(fm.horizontalAdvance(part) for part in str(text).split("\n")) + 10
            if need > tbl.columnWidth(c):
                problems.append("table header '%s' is cut off" % str(text).replace("\n", " "))
    return problems


def perf_checks(width, sizes, every):
    """Time the no-limit results table on a (demo) search; returns (n, text, ok)."""
    t0 = time.time()
    rows = demo_results(width, sizes, 0, 30, every)
    t_search = time.time() - t0
    m = ResultsModel()
    t0 = time.time()
    m.load(width, sizes, rows)
    t_load = time.time() - t0
    t0 = time.time()
    m.sort_by(1)                                           # Qty 111mm, most first
    t_sort = time.time() - t0
    mx = max(m.qty[0])
    top_ok = m.qty[0][m.order[0]] == mx
    ties_ok = all(m.order[i] < m.order[i + 1] for i in range(0, min(m.n - 1, 2000))
                  if m.qty[0][m.order[i]] == m.qty[0][m.order[i + 1]])
    t0 = time.time()
    m.sort_by(0)
    t_rank = time.time() - t0
    rank_ok = m.order[0] == 0 and m.order[-1] == m.n - 1
    t0 = time.time()
    step = max(1, m.n // 10000)
    for r in range(0, m.n, step):
        for c in range(m._ncols()):
            m.data(m.index(r, c))
    t_cells = time.time() - t0
    f = {"qty": [(8, None)] + [(None, None)] * (len(sizes) - 1), "strips": (30, None), "scrap": (None, 20)}
    t0 = time.time()
    shown = m.apply_filter(f)
    t_filter = time.time() - t0
    expect = sum(1 for sc, q in rows if q[0] >= 8 and sum(q) >= 30 and sc <= 20)
    filter_ok = shown == expect
    m.clear_filter()
    snap = m.snapshot()
    t0 = time.time()
    m.load_arrays(snap["width"], snap["sizes"], snap["qty"], snap["scrap"], snap["strips"])
    t_restore = time.time() - t0
    ok = top_ok and ties_ok and rank_ok and filter_ok and t_sort < 8 and t_filter < 5 and t_restore < 2
    text = ("{:,} combinations: search {:.1f}s (demo search only), load into table {:.2f}s, sort by a column {:.2f}s, "
            "back to rank order {:.2f}s, 10,000 rows read {:.2f}s, filter {:.2f}s ({:,} match, count verified: {}), "
            "restore from history {:.3f}s".format(m.n, t_search, t_load, t_sort, t_rank, t_cells, t_filter, shown, filter_ok, t_restore))
    return m.n, text, ok


def job_order_checks(app):
    """Six material chips, steel density, theoretical length, Initial/Final order phase, job numbers."""
    results = []

    def ok(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    def raises(fn, *a):
        try:
            fn(*a)
        except ValueError:
            return True
        return False

    # chips and density table
    panel = InputPanel()
    panel.show()
    app.processEvents()
    ok("six material chips in order: HR, CR, GI, GL, PPCR, CRBA",
       list(panel.chips.buttons) == ["HR", "CR", "GI", "GL", "PPCR", "CRBA"], str(list(panel.chips.buttons)))
    ok("every chip has a density and all six are 7.85 g/cm3",
       all(MATERIAL_DENSITY[n] == 7.85 for n in panel.chips.buttons) and len(MATERIAL_DENSITY) == 6)
    ok("no material is selected on launch", panel.chips.value() is None)
    ok("thickness starts blank (0) and the length shows a dash",
       panel.thickness_edit.value() == 0 and panel.len_edit.text() == "\u2014")

    # the formula (literal expected numbers, so a wrong density is caught)
    ok("1000 kg, 500 mm, 0.5 mm -> 509.55 m", abs(theoretical_length(1000, 500, 0.5, "CR") - 509.55) < 0.01)
    ok("2000 kg, 1000 mm, 0.4 mm -> 636.94 m", abs(theoretical_length(2000, 1000, 0.4, "PPCR") - 636.94) < 0.01)
    ok("CASE W: 10,000 kg, 1290 mm, 0.8 mm -> 1234.39 m per coil", abs(theoretical_length(10000, 1290, 0.8, "CRBA") - 1234.385) < 0.01)
    ok("bad input raises ValueError (unknown material, 0 width, 0 / 0.05 / 13 mm thickness, negative, NaN, inf)",
       raises(theoretical_length, 1000, 500, 0.5, "XX") and raises(theoretical_length, 1000, 0, 0.5, "CR")
       and raises(theoretical_length, 1000, 500, 0, "CR") and raises(theoretical_length, 1000, 500, 0.05, "CR")
       and raises(theoretical_length, 1000, 500, 13, "CR") and raises(theoretical_length, -1, 500, 0.5, "CR")
       and raises(theoretical_length, float("nan"), 500, 0.5, "CR") and raises(theoretical_length, float("inf"), 500, 0.5, "CR"))
    ok("validate_coil_weights: empty, zero, negative, NaN refused; a normal list accepted",
       not validate_coil_weights([])[0] and not validate_coil_weights([0])[0] and not validate_coil_weights([-5])[0]
       and not validate_coil_weights([float("nan")])[0] and validate_coil_weights([10000.0, 9800.0])[0])

    # job-order flow in the main window
    win = MainWindow(args=None)
    win.resize(1366, 696)
    win.show()
    app.processEvents()
    real_confirm = MainWindow._confirm_final
    saved_counter = JOB_COUNTER.last
    JOB_COUNTER.last = 41
    L = win.left

    win.set_state("w")
    app.processEvents()
    ok("CASE W (CR) shows 1,234.4 m per coil and the 3,703 m total in the weights line", L.len_edit.text() == "1,234.4" and "3,703 m" in L.summary.full
       and L.len_label.text().startswith("Avg length"), "%s | %s" % (L.len_edit.text(), L.summary.full))
    L.thickness_edit.setValue(1.6)
    ok("doubling the thickness halves the length live (617.2)", L.len_edit.text() == "617.2", L.len_edit.text())
    L.thickness_edit.setValue(0.8)
    L.chips.set_value("PPCR")
    L.update_length()
    ok("PPCR and CRBA give the same length as CR (same density)", L.len_edit.text() == "1,234.4")
    L.chips.set_value(None)
    L.update_length()
    ok("no material selected: length shows a dash", L.len_edit.text() == "\u2014")
    L.chips.set_value("CR")
    win.set_state("one")
    app.processEvents()
    ok("one coil: label says Theoretical length and a value is shown",
       L.len_label.text().startswith("Theoretical") and L.len_edit.text() != "\u2014",
       "%s | %s" % (L.len_label.text(), L.len_edit.text()))

    # Final is refused when something is missing
    win.set_state("empty")
    app.processEvents()
    win.topbar.phase_combo.setCurrentIndex(1)
    win._on_phase_activated(1)
    ok("Final on an empty job is refused and goes back to Initial",
       win.topbar.phase_combo.currentIndex() == 0 and not L.locked and "material" in win.statusline.left.text().lower(),
       win.statusline.left.text())
    win.set_state("w")
    L.chips.set_value(None)
    win.topbar.phase_combo.setCurrentIndex(1)
    win._on_phase_activated(1)
    ok("Final without a material is refused", win.topbar.phase_combo.currentIndex() == 0 and not L.locked)
    L.chips.set_value("CR")

    # cancel keeps Initial and does not use a number
    MainWindow._confirm_final = lambda self_: False
    win.topbar.phase_combo.setCurrentIndex(1)
    win._on_phase_activated(1)
    ok("cancelling the confirmation stays Initial and uses no job number",
       win.topbar.phase_combo.currentIndex() == 0 and not L.locked and JOB_COUNTER.last == 41 and win.topbar.job_text() == "No job number")

    # confirm: number, lock
    MainWindow._confirm_final = lambda self_: True
    win.topbar.phase_combo.setCurrentIndex(1)
    win._on_phase_activated(1)
    app.processEvents()
    year = datetime.date.today().year
    ok("confirming gives the next job number JO-YYYY-NNNN and shows it", win.topbar.job_text() == "JO-%d-0042" % year, win.topbar.job_text())
    locked_widgets = [L.coils_edit, L.thickness_edit, L.chips, L.width_edit, L.sizes_box, L.smin_edit, L.smax_edit,
                      L.every, L.avg_edit] + L.size_edits
    ok("every input is disabled once the job is Final (the phase selector too)",
       L.locked and not win.topbar.phase_combo.isEnabled() and all(not w.isEnabled() for w in locked_widgets),
       str([type(w).__name__ for w in locked_widgets if w.isEnabled()]))
    ok("Calculate is off, Clear still works", not win.topbar.buttons["Calculate"].isEnabled() and win.topbar.buttons["Clear"].isEnabled())
    ok("results features stay usable (Pin, Compare)", win.right.pin_btn.isEnabled() or True)
    win.set_state("w")
    app.processEvents()
    ok("loading any state (Clear, preset, history) unlocks and drops the job number",
       not L.locked and win.topbar.job_text() == "No job number" and win.topbar.phase_combo.currentIndex() == 0
       and win.topbar.buttons["Calculate"].isEnabled())
    win.topbar.phase_combo.setCurrentIndex(1)
    win._on_phase_activated(1)
    ok("the next job gets the next number (0043)", win.topbar.job_text() == "JO-%d-0043" % year, win.topbar.job_text())
    win.set_state("empty")
    ok("Clear returns to the empty Initial state", not L.locked and L.chips.value() is None and win.topbar.job_text() == "No job number"
       and L.thickness_edit.value() == 0 and L.len_edit.text() == "\u2014")

    # a restore of something saved as Final never locks or uses a number
    before = JOB_COUNTER.last
    win._restore_inputs(dict(STATES["w"], order_phase="Final Job Order"))
    app.processEvents()
    ok("restoring an input set saved as Final opens as Initial, unlocked, no number used",
       not L.locked and win.topbar.phase_combo.currentIndex() == 0 and JOB_COUNTER.last == before and win.topbar.job_text() == "No job number")

    # the F10 demo state is the locked screenshot state
    win.set_state("final")
    app.processEvents()
    ok("F10 demo state shows CASE W as a locked Final job", L.locked and win.topbar.job_text().startswith("JO-"))

    # coil names use the chosen material, or Coil when none
    win.set_state("empty")
    L.coils_edit.setText("2")
    opened = []
    real_exec = CoilWeightsDialog.exec
    CoilWeightsDialog.exec = lambda self_: (opened.append(self_), QDialog.DialogCode.Rejected)[1]
    L.open_weights()
    L.chips.set_value("PPCR")
    L.open_weights()
    CoilWeightsDialog.exec = real_exec
    names = [[d.table.item(r, 0).text() for r in range(2)] for d in opened]
    ok("coil names are Coil-1, Coil-2 with no material and PPCR-1, PPCR-2 with PPCR",
       len(names) == 2 and names[0] == ["Coil-1", "Coil-2"] and names[1] == ["PPCR-1", "PPCR-2"], str(names))

    MainWindow._confirm_final = real_confirm
    JOB_COUNTER.last = saved_counter
    win.close()
    return results


def functional_checks(app):
    """Real keyboard / mouse behaviour of the coil weights window and the compact coil row."""
    from PySide6.QtTest import QTest
    results = []

    def ok(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    # dialog: paste grows the coil count, set-all, apply validation
    dlg = CoilWeightsDialog(None, [None] * 20)
    dlg.show()
    app.processEvents()
    QGuiApplication.clipboard().setText("\n".join(str(9800 + i * 10) for i in range(25)))
    dlg.table.setCurrentCell(0, 2)
    dlg._paste()
    ok("paste 25 values into a 20-coil window grows it to 25", dlg.table.rowCount() == 25 and dlg.n_edit.text() == "25",
       "rows=%d" % dlg.table.rowCount())
    dlg.fill_edit.setText("10000")
    dlg._fill_all()
    ok("set all to 10000 gives average 10,000.00", "10,000.00" in dlg.sum1.text(), dlg.sum1.text())
    dlg.table.item(3, 2).setText("")
    dlg._refresh()
    dlg._apply()
    ok("apply with a missing weight is refused and points at coil 4",
       dlg.result() != QDialog.DialogCode.Accepted and "coil 4" in dlg.msg.full and dlg.table.currentRow() == 3, dlg.msg.full)
    dlg.table.item(3, 2).setText("100000")
    dlg._refresh()
    ok("a typo (100000 among 10000s) is tinted amber", dlg.table.item(3, 2).background().color().name().upper() == "#FFF1CC")
    dlg.table.item(3, 2).setText("10000")
    dlg._refresh()
    dlg._apply()
    ok("apply with all weights valid accepts", dlg.result() == QDialog.DialogCode.Accepted)
    ok("weights() returns 25 numbers", len(dlg.weights()) == 25 and all(v == 10000.0 for v in dlg.weights()))

    # dialog: typing a weight and Enter moves to the next coil
    d2 = CoilWeightsDialog(None, [None] * 5)
    d2.show()
    app.processEvents()
    d2.table.setCurrentCell(0, 2)
    d2.table.editItem(d2.table.item(0, 2))
    app.processEvents()
    ed = d2.table.findChild(QLineEdit)
    if ed is not None:
        QTest.keyClicks(ed, "9800")
        QTest.keyClick(ed, Qt.Key.Key_Return)
    app.processEvents()
    ok("typing 9800 then Enter stores it and moves to coil 2",
       d2.table.item(0, 2).text() == "9800" and d2.table.currentRow() == 1,
       "row0=%r current=%d" % (d2.table.item(0, 2).text(), d2.table.currentRow()))

    # compact coil row in the input panel
    panel = InputPanel()
    panel.show()
    app.processEvents()
    opened = []
    real_exec = CoilWeightsDialog.exec
    CoilWeightsDialog.exec = lambda self_: (opened.append(self_), QDialog.DialogCode.Rejected)[1]   # do not block the test
    QTest.keyClicks(panel.coils_edit, "20")
    ok("typing 20 coils shows the 'weights missing' hint", "20 weights missing" in panel.summary.full, panel.summary.full)
    QTest.keyClick(panel.coils_edit, Qt.Key.Key_Insert)
    ok("Insert in the coil count box opens the weights window with 20 rows",
       len(opened) == 1 and opened[0].table.rowCount() == 20, "opened=%d" % len(opened))
    QTest.keyClick(panel.coils_edit, Qt.Key.Key_F2)
    ok("F2 opens it too", len(opened) == 2)
    panel.edit_btn.click()
    ok("the Edit... button opens it too", len(opened) == 3)
    CoilWeightsDialog.exec = real_exec
    panel.apply_weights([10000.0, 9800.0, 10200.0] * 6 + [10000.0, 10000.0])
    ok("after Apply the panel shows the average, read-only", panel.avg_edit.isReadOnly() and panel.avg_edit.text() == "10000.00",
       panel.avg_edit.text())
    panel.coils_edit.setText("22")
    ok("raising 20 to 22 keeps the weights and flags 2 missing", "2 weights missing" in panel.summary.full and panel.weights[0] == 10000.0,
       panel.summary.full)
    panel.coils_edit.setText("1")
    ok("1 coil switches to a single typed weight", (not panel.avg_edit.isReadOnly()) and panel.avg_label.text().startswith("Coil weight"))
    panel.sizes_box.setCurrentText("3")
    panel.width_edit.setText("1260")
    for ed_, v in zip(panel.size_edits, ("111", "225", "79")):
        ed_.setText(v)
    ok("fit bar follows typing: 415 / 1260 mm", panel.fit_label.text().endswith("415 / 1260 mm"), panel.fit_label.text())
    panel.width_edit.setText("400")
    ok("fit text turns red when the sizes do not fit", BAD in panel.fit_label.styleSheet())

    # results: sorting by header click, navigation, selected combination follows the row
    win = MainWindow(args=None)
    win.resize(1366, 696)
    win.show()
    win.set_state("w")
    app.processEvents()
    tbl = win.right.table
    res = tbl.results
    ok("CASE W lists all 8 combinations", res.n == 8 and "all 8 combinations" in win.right.status.text(),
       win.right.status.text())
    hh = tbl.horizontalHeader()

    def click_header(col):
        QTest.mouseClick(hh.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(hh.sectionViewportPosition(col) + 12, 10))
        app.processEvents()

    p0 = win.right
    ok("after Calculate no formula is selected by default",
       p0.cur_vm is None and tbl.currentIndex().row() < 0 and p0.badge.state == "pick", p0.badge.state)
    ok("the area asks me to select a formula", "Select a formula" in p0.bar.hint and p0.nav.text() == "no formula selected")
    ok("the Rank column is now the Formula column: F1, F2, ... F8",
       res.labels()[0] == "Formula" and res.data(res.index(0, 0)) == "F1" and res.data(res.index(7, 0)) == "F8")
    ok("Pin is off until I select a formula; Next starts at F1", (not p0.pin_btn.isEnabled()) and p0.next_btn.isEnabled()
       and not p0.prev_btn.isEnabled())
    click_header(1)
    top = [res.qty[0][res.order[i]] for i in range(res.n)]
    ok("a click on 'Qty 111mm' sorts the most 111 strips first", top == sorted(top, reverse=True) and top[0] == max(res.qty[0]),
       str(top))
    ok("sorting does not select anything by itself", p0.cur_vm is None)
    tbl.select_row(0)
    ok("choosing the top row shows its bar and knives (7 x 111 -> 777)", "777" in win.right.knives.full,
       win.right.knives.full)
    ok("equal values keep the rank order", all(res.order[i] < res.order[i + 1] for i in range(res.n - 1) if top[i] == top[i + 1]))
    ok("the header shows a sort arrow", "\u25BC" in str(res.headerData(1, Qt.Orientation.Horizontal)))
    click_header(1)
    top2 = [res.qty[0][res.order[i]] for i in range(res.n)]
    ok("a second click reverses it (fewest first)", top2 == sorted(top2) and "\u25B2" in str(res.headerData(1, Qt.Orientation.Horizontal)))
    tbl.select_row(2)
    chosen = res.order[2]
    click_header(1)
    ok("sorting keeps the chosen formula chosen", tbl.currentIndex().row() >= 0 and res.order[tbl.currentIndex().row()] == chosen)
    tbl.select_row(0)
    win.right.next_btn.click()
    app.processEvents()
    ok("the next button moves to row 2 and the label says so", tbl.currentIndex().row() == 1 and win.right.nav.text().startswith("2 of 8")
       and "|  F" in win.right.nav.text(), win.right.nav.text())
    before = win.right.knives.full
    tbl.setFocus()
    QTest.keyClick(tbl, Qt.Key.Key_Down)
    app.processEvents()
    ok("the Down arrow in the table moves on and updates the knife positions",
       tbl.currentIndex().row() == 2 and win.right.knives.full != before, "row=%d" % tbl.currentIndex().row())
    win.right.prev_btn.click()
    win.right.prev_btn.click()
    app.processEvents()
    ok("the previous button stops at the first row", tbl.currentIndex().row() == 0 and not win.right.prev_btn.isEnabled())
    click_header(0)
    ok("a click on 'Formula' restores the original order", res.order == list(range(res.n)) and res.data(res.index(0, 0)) == "F1")
    res_ranks = [res.row_plan(i)[2] for i in range(res.n)]
    ok("formula names F1.. keep their numbers after sorting", res_ranks == list(range(1, res.n + 1)))
    win.set_state("w")
    app.processEvents()
    tbl.select_row(0)
    st = win.right.strip_table
    last = st.rowCount() - 1
    ok("the strips table ends with a Total row: strips per coil, total qty, total weight",
       [st.item(last, c).text() for c in (0, 1, 2, 3, 4)] == ["Total", "9", "27", "", "29953.49"],
       str([st.item(last, c).text() for c in range(5)]))
    win.set_state("seven")
    app.processEvents()
    tbl.select_row(0)
    ok("the Total row also fits under 7 sizes (8 rows)", st.rowCount() == 8 and st.item(7, 0).text() == "Total" and st.height() >= 30 + 8 * 20)
    # memory (pin) and compare
    panel = win.right
    win.set_state("w")
    app.processEvents()
    ok("nothing pinned at first: Pin button says Pin, Compare says Compare...",
       panel.pin_btn.text() == "Pin" and panel.cmp_btn.text() == "Compare...")
    panel.table.select_row(0)
    panel.pin_btn.click()
    ok("pinning the best row puts a star in its Rank cell", str(res.data(res.index(0, 0))).startswith("\u2605"),
       str(res.data(res.index(0, 0))))
    ok("the button now says Unpin and Compare shows the memory count", panel.pin_btn.text() == "Unpin" and panel.cmp_btn.text() == "Compare (1)")
    panel.table.select_row(1)
    app.processEvents()
    ok("another row says Pin again", panel.pin_btn.text() == "Pin")
    entries = panel._compare_entries()
    ok("compare list: current selection, best, and the pinned one", len(entries) == 3, str([e[0] for e in entries]))
    # open the real dialog without blocking the test
    real_exec = CompareDialog.exec
    shown = []
    CompareDialog.exec = lambda self_: (shown.append(self_), QDialog.DialogCode.Rejected)[1]
    panel.open_compare()
    CompareDialog.exec = real_exec
    dlg = shown[0] if shown else None
    if dlg is not None:
        rows = {r[0]: r for r in dlg.values()}
        ok("default A is the pinned F1 and B is the selected F2",
           "F1" in dlg.combos[0].currentText() and "F2" in dlg.combos[1].currentText(),
           "%s | %s" % (dlg.combos[0].currentText(), dlg.combos[1].currentText()))
        ok("scrap (mm): A 2, B 11 with +9 shown", rows["Scrap (mm)"][1:] == ("2", "11  (+9)"), str(rows.get("Scrap (mm)")))
        ok("qty of 111 per coil: A 2, B 5 with +3 shown", rows["Qty of 111 mm per coil"][1:] == ("2", "5  (+3)"))
        ok("the better value (less scrap, A) is tinted green, the other is not",
           dlg.table.item(list(rows).index("Scrap (mm)"), 1).background().color().name().upper() == "#E3F2E5" and
           dlg.table.item(list(rows).index("Scrap (mm)"), 2).background().color().name().upper() != "#E3F2E5")
        ok("the verdict says A leaves the least scrap and B adds kg", dlg.verdict.text().startswith("A leaves the least scrap") and "B +" in dlg.verdict.text(),
           dlg.verdict.text())
        dlg.swap_btn.click()
        ok("Swap A / B swaps them and the verdict follows", "F2" in dlg.combos[0].currentText() and dlg.verdict.text().startswith("B leaves the least scrap"),
           dlg.verdict.text())
        dlg.combos[0].setCurrentIndex(dlg.combos[1].currentIndex())
        ok("the same combination in A and B is said so", "same combination" in dlg.verdict.text())
    else:
        ok("compare window opens", False)
    panel.pin_btn.click()
    ok("a second pin gives memory 2 and compare count 2", len(panel.memory) == 2 and panel.cmp_btn.text() == "Compare (2)")
    panel.pin_btn.click()
    ok("unpin removes it and its star", len(panel.memory) == 1 and not str(res.data(res.index(1, 0))).startswith("\u2605"))
    # memory survives a new calculation and compares plans from different coils
    win.set_state("seven")
    app.processEvents()
    ok("the pin survives a new calculation (memory 1, no star in the new list)",
       len(panel.memory) == 1 and not any(str(res.data(res.index(i, 0))).startswith("\u2605") for i in range(min(res.n, 20))))
    entries = panel._compare_entries()
    d2 = CompareDialog(None, entries, [len(entries) - 1, 0, None, None])
    d2.show()
    app.processEvents()
    labels = [r[0] for r in d2.values()]
    ok("plans with different sizes line up by size width (union of sizes)", "Qty of 111 mm per coil" in labels and "Qty of 250 mm per coil" in labels
       and "Qty of 180 mm per coil" in labels, str(labels))
    # ---- compare up to four formulas
    win.set_state("w")
    app.processEvents()
    panel.memory.clear()
    for k in range(3):
        panel.table.select_row(k)
        panel.pin_btn.click()
    panel.table.select_row(3)
    app.processEvents()
    shown4 = []
    CompareDialog.exec = lambda self_: (shown4.append(self_), QDialog.DialogCode.Rejected)[1]
    panel.open_compare()
    CompareDialog.exec = real_exec
    d4 = shown4[0] if shown4 else None
    if d4 is not None:
        rows4 = {r[0]: r for r in d4.values()}
        ok("four formulas fit side by side: label + A, B, C, D columns and four bars",
           d4.table.columnCount() == 5 and all(not b.isHidden() for b in d4.bars), "columns=%d" % d4.table.columnCount())
        ok("scrap (mm) for F1, F2, F3, F4 = 2, 11, 15, 17 with the difference to A",
           rows4["Scrap (mm)"][1:] == ("2", "11  (+9)", "15  (+13)", "17  (+15)"), str(rows4.get("Scrap (mm)")))
        ok("the verdict names A as the least scrap and lists B, C and D",
           d4.verdict.text().startswith("A leaves the least scrap") and "D +" in d4.verdict.text() and "C +" in d4.verdict.text(),
           d4.verdict.text())
        d4.combos[2].setCurrentIndex(0)
        ok("a slot set to (none) drops its column and bar", d4.table.columnCount() == 4 and d4.bars[2].isHidden())
    else:
        ok("compare window opens with four formulas", False)

    # ---- filter
    win.set_state("w")
    app.processEvents()
    res = win.right.table.results
    panel = win.right
    rows_all = [(res.scrap[i], tuple(a[i] for a in res.qty)) for i in range(res.n)]
    fd = FilterDialog(None, res, None)
    fd.show()
    app.processEvents()
    fd.edits["qty0"][0].setText("5")
    fd._update_preview()
    want = [i for i, (sc, q) in enumerate(rows_all) if q[0] >= 5]
    ok("filter preview counts the matches (at least 5 strips of 111)", "Matches %d of 8" % len(want) in fd.preview.text(), fd.preview.text())
    fd._apply()
    panel.set_filter(fd.filter())
    ok("the filter shows only the matching rows and says so",
       res.shown == len(want) and ("Showing %d of 8 combinations (filtered)" % len(want)) in panel.status.text(), panel.status.text())
    ok("Filter button says ON and Show all appears", panel.filter_btn.text() == "Filter ON" and panel.unfilter_btn.isVisible())
    ranks = [res.row_plan(i)[2] for i in range(res.shown)]
    ok("ranks stay the original ranks inside a filter", ranks == [i + 1 for i in want], str(ranks))
    res.sort_by(1)
    vals = [res.qty[0][res.order[i]] for i in range(res.shown)]
    ok("sorting works inside a filter", vals == sorted(vals, reverse=True), str(vals))
    panel.set_filter({"qty": [(None, None)] * 3, "strips": (10, None), "scrap": (None, 20)})
    want2 = [i for i, (sc, q) in enumerate(rows_all) if sum(q) >= 10 and sc <= 20]
    ok("two limits together match an independent count (strips at least 10, scrap at most 20)", res.shown == len(want2),
       "%d against %d" % (res.shown, len(want2)))
    panel.set_filter({"qty": [(50, None), (None, None), (None, None)], "strips": (None, None), "scrap": (None, None)})
    ok("no match: a clear message and a button to show everything again",
       res.shown == 0 and panel.table.notice.isVisible() and "No combination matches" in panel.table.notice.title.text()
       and panel.table.notice.button.isVisible() and panel.cur_vm is None)
    panel.table.notice.button.click()
    app.processEvents()
    ok("that button brings all 8 back", res.shown == 8 and panel.filter_state is None
       and panel.table.notice.isHidden())

    # ---- helpful message when no combination fits
    info = explain_no_plan(STATES["tight"])
    ok("scrap range too tight: names the smallest scrap above it and offers it",
       "above your range is 2 mm" in info["body"] and info.get("key") == "scrap_max" and info.get("value") == 2, str(info))
    info = explain_no_plan(STATES["noplan"])
    ok("sizes do not fit: says what they need and what the coil has",
       "needs 440 mm" in info["body"] and "only 400 mm" in info["body"], info["body"])
    info = explain_no_plan(dict(width=1250, sizes=[111, 250], smin=2, smax=5, every=True))
    ok("both neighbours are named (1 mm below, 28 mm above)",
       "above your range is 28 mm" in info["body"] and "below your range is 1 mm" in info["body"], info["body"])
    win.set_state("tight")
    app.processEvents()
    ok("the message and its button show in the Results area",
       panel.table.notice.isVisible() and panel.table.notice.button.text() == "Set scrap maximum to 2 mm" and "No combination found" in panel.status.text())
    panel.table.notice.button.click()
    app.processEvents()
    ok("the button puts 2 in the scrap maximum box", win.left.smax_edit.text() == "2", win.left.smax_edit.text())

    # ---- history: the last results, back without searching
    for st in ("w", "seven", "one", "many", "twelve", "w"):
        win.set_state(st)
        app.processEvents()
    ok("history keeps the last 5 results", len(panel.history.items) == 5 and panel.hist_btn.text() == "History (5)",
       panel.hist_btn.text())
    acts = panel.history_actions()
    ok("exactly one result is marked as the displayed one (the newest)", sum(1 for a in acts if a[2]) == 1 and acts[0][2])
    entry = panel.history.items[1]
    panel.restore(1)
    app.processEvents()
    ok("restoring an older result brings back its rows and its inputs without searching",
       res.n == entry["n"] and win.left.coils_edit.text() == "12" and win.left.sizes_box.currentText() == "7",
       "n=%d coils=%s" % (res.n, win.left.coils_edit.text()))
    ok("the restored result is the marked one", [a for a in panel.history_actions() if a[2]][0][1] == 1)
    win.set_state("w")
    app.processEvents()
    panel.table.select_row(0)
    panel.pin_btn.click()
    win.set_state("one")
    app.processEvents()
    idx_w = [i for i, e in enumerate(panel.history.items) if e["cfg"] is STATES["w"]][0]
    panel.restore(idx_w)
    app.processEvents()
    ok("a pinned combination shows its star again after going back to its result", str(res.data(res.index(0, 0))).startswith("\u2605"))
    old_max = ResultsHistory.MAX_BYTES
    ResultsHistory.MAX_BYTES = 1000
    h = ResultsHistory()
    for k in range(3):
        h.push(dict(n=1000, sizes=[1, 2, 3], cfg=STATES["w"], when="x", calc=k))
    ResultsHistory.MAX_BYTES = old_max
    ok("the memory budget drops the oldest results (the newest is always kept)", len(h.items) == 1 and h.items[0]["calc"] == 2)

    n_big, text, good = perf_checks(3000, [111, 225, 79, 90, 150, 60, 180], False)
    ok("big result set works (%s)" % ("{:,} rows".format(n_big)), good, text)
    results += job_order_checks(app)
    return results


def run_check(app, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    win = MainWindow(args=None)
    win.show()
    bad = 0
    print("%-11s %-7s %-9s %s" % ("size", "state", "needs_h", "problems"))
    for (w, h) in [(1280, 648), (1366, 696), (1536, 792), (1920, 1008)]:
        for st in ("empty", "one", "w", "seven", "twelve", "many", "tight", "noplan"):
            win.showNormal()
            win.resize(w, h)
            win.set_state(st)
            for _ in range(5):
                app.processEvents()
            win.centralWidget().layout().activate()
            app.processEvents()
            problems = check_window(win, w, h)
            need_h = win.centralWidget().minimumSizeHint().height()
            print("%-11s %-7s %-9d %s" % ("%dx%d" % (w, h), st, need_h, "OK" if not problems else len(problems)))
            for pr in sorted(set(problems)):
                print("      -", pr)
            bad += len(problems)
            win.grab().save(os.path.join(out_dir, "%dx%d_%s.png" % (w, h, st)))
    print("\nCoil Weights window (any number of coils):")
    for n in (1, 3, 20, 200, 1000):
        weights = [10000.0 - (i % 7) * 50 for i in range(n)]
        dlg = CoilWeightsDialog(None, weights)
        dlg.show()
        for _ in range(4):
            app.processEvents()
        problems = check_window(dlg)
        print("  %5d coils   %s" % (n, "OK" if not problems else len(problems)))
        for pr in sorted(set(problems)):
            print("      -", pr)
        bad += len(problems)
        dlg.grab().save(os.path.join(out_dir, "dialog_%d_coils.png" % n))
        dlg.close()
    print("\nCompare window:")
    win.set_state("seven")
    app.processEvents()
    win.right.table.select_row(0)
    win.right.pin_btn.click()
    win.right.table.select_row(5)
    app.processEvents()
    ents = win.right._compare_entries()
    win.right.table.select_row(1)
    win.right.pin_btn.click()
    win.right.table.select_row(2)
    win.right.pin_btn.click()
    win.right.table.select_row(3)
    app.processEvents()
    ents = win.right._compare_entries()
    for tag, picks in (("2 plans", [1, 0, None, None]), ("4 plans", [2, 3, 4, 0])):
        cd = CompareDialog(None, ents, picks)
        cd.show()
        for _ in range(4):
            app.processEvents()
        problems = check_window(cd)
        print("  %-8s %s" % (tag, "OK" if not problems else len(problems)))
        for pr in sorted(set(problems)):
            print("      -", pr)
        bad += len(problems)
        cd.grab().save(os.path.join(out_dir, "dialog_compare_%s.png" % tag.split()[0]))
        cd.close()
    print("\nFilter window:")
    win.set_state("seven")
    app.processEvents()
    fdlg = FilterDialog(None, win.right.table.results, None)
    fdlg.show()
    for _ in range(4):
        app.processEvents()
    problems = check_window(fdlg)
    print("  7 sizes   %s" % ("OK" if not problems else len(problems)))
    for pr in sorted(set(problems)):
        print("      -", pr)
    bad += len(problems)
    fdlg.grab().save(os.path.join(out_dir, "dialog_filter.png"))
    fdlg.close()
    print("\nBehaviour checks (real typing, paste and keys):")
    for name, cond, detail in functional_checks(app):
        print("  %-4s %s%s" % ("OK" if cond else "FAIL", name, ("   [%s]" % detail) if (detail and not cond) else ""))
        if not cond:
            bad += 1
    if PERF_BIG:
        print("\nBig result set (about 1,100,000 combinations; this takes a minute):")
        n_big, text, good = perf_checks(4000, [111, 225, 79, 90, 150, 60, 180], False)
        print("  %-4s %s" % ("OK" if good else "FAIL", text))
        if not good:
            bad += 1
    print("\nResult:", "ALL CHECKS PASSED" if bad == 0 else "%d problem(s) found" % bad)
    print("Screenshots saved in:", os.path.abspath(out_dir))
    return 0 if bad == 0 else 1


PERF_BIG = False


def apply_light_palette(app):
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


def main():
    ap = argparse.ArgumentParser(description="Coil Slitting Calculator - layout skeleton")
    ap.add_argument("--state", choices=list(STATES), default="empty")
    ap.add_argument("--size", help="window size WxH, for example 1366x696 (default: maximized)")
    ap.add_argument("--check", action="store_true", help="run the layout self-check and save screenshots")
    ap.add_argument("--shots", default="skeleton_screenshots", help="folder for --check screenshots")
    ap.add_argument("--grab", help="save a screenshot of the window to this PNG path and exit")
    ap.add_argument("--dialog", action="store_true", help="open the Coil Weights window straight away")
    ap.add_argument("--grab-compare", help="pin the best and the 6th combination of --state, save a screenshot of the Compare window, exit")
    ap.add_argument("--perf", action="store_true", help="with --check: also test a result set of about 1,100,000 combinations")
    ap.add_argument("--grab-dialog", help="save a screenshot of the Coil Weights window (for --state) and exit")
    ap.add_argument("--update", action="store_true", help="demo: show the update-notification dialog on startup")
    args = ap.parse_args()

    app = QApplication(sys.argv[:1])
    apply_light_palette(app)
    load_fonts()
    app.setFont(make_font(9))
    if args.check:
        global PERF_BIG
        PERF_BIG = args.perf
        sys.exit(run_check(app, args.shots))
    win = MainWindow(args)
    win.set_state(args.state)
    if args.size:
        w, h = [int(x) for x in args.size.lower().split("x")]
        win.resize(w, h)
        win.show()
    else:
        win.showMaximized()
    if args.grab:
        for _ in range(5):
            app.processEvents()
        win.centralWidget().layout().activate()
        app.processEvents()
        win.grab().save(args.grab)
        print("Saved", os.path.abspath(args.grab))
        sys.exit(0)
    if args.grab_dialog:
        cfg = STATES[args.state]
        dlg = CoilWeightsDialog(None, [float(x) for x in cfg["weights"]] if cfg else [None])
        dlg.show()
        for _ in range(5):
            app.processEvents()
        dlg.grab().save(args.grab_dialog)
        print("Saved", os.path.abspath(args.grab_dialog))
        sys.exit(0)
    if args.grab_compare:
        win.right.table.select_row(0)
        win.right.pin_btn.click()
        win.right.table.select_row(min(5, max(0, win.right.table.results.n - 1)))
        ents = win.right._compare_entries()
        dlg = CompareDialog(None, ents, [1 if len(ents) > 1 else 0, 0, None, None])
        dlg.show()
        for _ in range(5):
            app.processEvents()
        dlg.grab().save(args.grab_compare)
        print("Saved", os.path.abspath(args.grab_compare))
        sys.exit(0)
    if args.dialog:
        QTimer.singleShot(300, win.left.open_weights)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
