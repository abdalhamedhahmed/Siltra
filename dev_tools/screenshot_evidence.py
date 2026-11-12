#!/usr/bin/env python3
"""
SLITRA FIX 7 (REVISED) - Screenshot evidence for all four parts.

Loads Segoe UI font AFTER creating QApplication (offscreen loads no fonts by default).
"""
import sys
import os

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

app = QApplication(sys.argv[:1])

# Load Segoe UI font AFTER QApplication created
segoe_path = r"C:\Windows\Fonts\segoeui.ttf"
if os.path.exists(segoe_path):
    font_id = QFontDatabase.addApplicationFont(segoe_path)
    families = QFontDatabase.applicationFontFamilies(font_id)
    print(f"Loaded font ID {font_id}: {families}")
else:
    print(f"WARNING: Segoe UI font not found at {segoe_path}")

from slitra_window import MainWindow, apply_light_palette
from state import MemoryStore

os.makedirs("screenshots/slitra_fix7", exist_ok=True)

def save(widget, path):
    pixmap = widget.grab()
    pixmap.save(path)
    print(f"  Saved: {path}")

apply_light_palette(app)

# Verify font loaded
print("Segoe UI available:", 'Segoe UI' in QFontDatabase().families())
app.setFont(QFont("Segoe UI", 9))

win = MainWindow()
win.right.set_memory_store(MemoryStore())
win.resize(1280, 648)
win.show()
for _ in range(10):
    app.processEvents()

right = win.right
right.inputsRestore.connect(lambda cfg: win.left.set_state(cfg))
right.suggestion.connect(lambda key, value: (win.left.smax_edit.setText(str(value)) if key == "scrap_max" else win.left.smin_edit.setText(str(value))))

# Build results
def build_vm(scrap, qty, width=1290, sizes=None, avg=10000.0, coils=3):
    if sizes is None:
        sizes = [111, 250, 79]
    cfg = dict(width=width, sizes=sizes, avg=avg, coils=coils,
               weights=[avg] * coils, smin=0, smax=30, every=True)
    return dict(width=width, sizes=sizes, qty=list(qty), scrap=scrap,
                used=width - scrap, pct=scrap / width * 100, strips=sum(qty),
                knives=[], wps=[avg * s / width for s in sizes],
                total_qty=[q * coils for q in qty],
                total_w=[q * coils * avg * s / width for s, q in zip(sizes, qty)],
                scrap_per=scrap / width * avg,
                scrap_total=scrap / width * avg * coils,
                coils=coils, avg=avg, weight_ok=True, cfg=cfg)

def apply_results(rows):
    width = 1290
    sizes = [111, 250, 79]
    scrap0 = rows[0][0] if rows else 0
    qty0 = rows[0][1] if rows else (1, 1, 1)
    vm = build_vm(scrap0, qty0)
    vm['rows'] = rows
    vm['total'] = len(rows)
    win.show_results(vm)

# ================================================================
# PART (a) - Pin and Compare (star in Rank)
# ================================================================
print("========== PART (a): Pin and Compare ==========")
apply_results([(2, (2, 3, 4)), (5, (3, 2, 5)), (11, (5, 1, 6)), (20, (4, 4, 4)), (30, (6, 6, 6))])
app.processEvents()
right.table.select_row(0)
app.processEvents()
right.toggle_pin()  # Pin rank 1 -> star shows in Rank
app.processEvents()
save(win, "screenshots/slitra_fix7/part_a_pin_star_in_rank.png")
# Unpin
right.toggle_pin()
app.processEvents()
save(win.right.table, "screenshots/slitra_fix7/part_a_no_pin.png")

# ================================================================
# PART (b) - Filter ON + no-match
# ================================================================
print("========== PART (b): Filter ==========")
apply_results([(2, (2, 3, 4)), (5, (3, 2, 5)), (11, (5, 1, 6)), (20, (4, 4, 4)), (30, (6, 6, 6))])
app.processEvents()
f = {"qty": [(None, None)] * 3, "strips": (None, None), "scrap": (10, None)}
right.set_filter(f)
app.processEvents()
save(win, "screenshots/slitra_fix7/part_b_filter_on.png")
save(win.right.table, "screenshots/slitra_fix7/part_b_filtered_table.png")

# No-match
f_none = {"qty": [(None, None)] * 3, "strips": (None, None), "scrap": (999, None)}
right.set_filter(f_none)
app.processEvents()
save(win, "screenshots/slitra_fix7/part_b_no_match.png")
right.set_filter(None)
app.processEvents()

# ================================================================
# PART (c) - No combination message with suggestion
# ================================================================
print("========== PART (c): No combination ==========")
params = dict(width=1000, sizes=[100], smin=0, smax=30, every=True)
right.apply(None, params)
app.processEvents()
save(win, "screenshots/slitra_fix7/part_c_no_combination.png")
# Click suggestion
notice = right.table.notice
notice.actionClicked.emit(notice._key, notice._value)
app.processEvents()
save(win, "screenshots/slitra_fix7/part_c_suggestion_applied.png")

# ================================================================
# PART (d) - History (N) button
# ================================================================
print("========== PART (d): History ==========")
for i in range(7):
    apply_results([(i * 2, (i, i + 1, i + 2))])
    app.processEvents()
save(win, "screenshots/slitra_fix7/part_d_history_button.png")

app.quit()
print("\nAll screenshots captured.")
sys.exit(0)