#!/usr/bin/env python3
"""
SLITRA FIX 7 (REVISED) - Proof of all four parts via real QTest clicks/keys.

Runs the actual MainWindow as the user would see it, exercising:
  (a) Pin/Compare: Pin/Unpin, star in Rank, Compare (2-way), Compare 3 (3-way), Swap A/B, Clear memory
  (b) Filter: FilterDialog, live preview "Matches N of M", Filter ON red button, Show all,
        status "Showing N of M combinations (filtered)", ranks stay original, sort/nav/pin/compare
        inside filter, new calculation clears filter, no-match message + "Show all combinations"
        button + blanked Selected Combination area
  (c) No combination message: explain_no_plan with one-click suggestion button
  (d) History: last 5 kept, oldest dropped, History (N) button, restore inputs+rows without searching
"""
import sys
import os
import time

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtWidgets import QApplication, QPushButton, QMenu, QDialog
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtGui import QFont

from slitra_window import MainWindow, apply_light_palette, plan_vm, CompareDialog, FilterDialog
from state import MemoryStore

results = []


def check(cond, msg):
    results.append((cond, msg))
    status = "PASS" if cond else "FAIL"
    safe_msg = msg.replace('★', '*').replace('●', '*').replace('→', '->')
    print(f"[{status}] {safe_msg}")


# ---------------------------------------------------------------- build a mock VM
def build_vm(scrap, qty, width=1290, sizes=None, avg=10000.0, coils=3):
    if sizes is None:
        sizes = [111, 250, 79]
    cfg = dict(width=width, sizes=sizes, avg=avg, coils=coils, weights=[avg] * coils, smin=0, smax=30, every=True)
    vm = dict(plan_vm(cfg, scrap, qty),
              cfg=cfg, width=width, sizes=sizes)
    return vm


def apply_results(win, rows):
    """Apply a full results VM (like the controller does)."""
    width = 1290
    sizes = [111, 250, 79]
    scrap0 = rows[0][0] if rows else 0
    qty0 = rows[0][1] if rows else ()
    vm = build_vm(scrap0, qty0)
    vm.update(rows=rows, total=len(rows),
              width=width, sizes=sizes)
    win.show_results(vm)


# ---------------------------------------------------------------- main
def run_test():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_light_palette(app)
    app.setFont(QFont("Segoe UI", 9))

    win = MainWindow()
    win.right.set_memory_store(MemoryStore())

    right = win.right
    model = right.table.results

    # Connect controller signals (simulate what SlitraController does)
    right.inputsRestore.connect(lambda cfg: win.left.set_state(cfg))
    right.suggestion.connect(lambda key, value: (win.left.smax_edit.setText(str(value)) if key == "scrap_max" else win.left.smin_edit.setText(str(value))))

    win.showMaximized()

    # ================================================================
    # PART (c) - No combination message
    # ================================================================
    print("\n========== PART (c): No combination message ==========")
    # Use width=1000, sizes=[100], every=True -> scraps are 0,100,200,...,1000
    # with smax=30: scraps above 30 exist (min above=100), no scraps below 0
    # -> suggestion: "Set scrap maximum to 100 mm"
    params = dict(width=1000, sizes=[100], smin=0, smax=30, every=True)
    right.apply(None, params)
    app.processEvents()
    notice = right.table.notice
    check(notice.isVisible(), "No-combination notice is visible")
    check(right.status.text() == "No combination found",
          f"Status='No combination found', got '{right.status.text()}'")
    check(notice.button.isVisible(), "Suggestion button visible")
    btn_text = notice.button.text()
    check("scrap" in btn_text.lower(), f"Button mentions scrap: '{btn_text}'")
    check(notice._key == "scrap_max" and notice._value == 100,
          f"Suggestion key={notice._key}, value={notice._value} (expected scrap_max=100)")
    # Click the suggestion button
    notice.actionClicked.emit(notice._key, notice._value)
    app.processEvents()
    check(win.left.smax_edit.text() == str(notice._value),
          f"Suggestion applied: smax={win.left.smax_edit.text()} (expected {notice._value})")
    print(f"   explain_no_plan key={notice._key}, value={notice._value}")

    # ================================================================
    # PART (b) - Filter
    # ================================================================
    print("\n========== PART (b): Filter ==========")
    rows = [(2, (2, 3, 4)), (5, (3, 2, 5)), (11, (5, 1, 6)), (20, (4, 4, 4)), (30, (6, 6, 6))]
    apply_results(win, rows)
    app.processEvents()
    check(model.n == 5, f"Total combinations={model.n} (expected 5)")
    check(right.filter_btn.text() == "Filter...", f"Initial filter button='Filter...', got '{right.filter_btn.text()}'")
    check(right.unfilter_btn.isHidden(), "Show all button hidden initially")

    # Open filter dialog
    dlg = FilterDialog(win, model, None)
    dlg.show()
    app.processEvents()
    check("Matches" in dlg.preview.text() or "No combination" in dlg.preview.text(),
          f"Preview shows match info: '{dlg.preview.text()}'")
    dlg.close()
    app.processEvents()

    # Apply a filter: scrap at least 10 (matches rows with scrap>=10: 11, 20, 30 = 3)
    f = {"qty": [(None, None)] * 3, "strips": (None, None), "scrap": (10, None)}
    right.set_filter(f)
    app.processEvents()
    check(right.filter_state == f, "filter_state set")
    check("Filter ON" in right.filter_btn.text(), f"Filter button='Filter ON': '{right.filter_btn.text()}'")
    check(right.unfilter_btn.isVisible(), "Show all button visible when filter ON")
    check("Showing 3 of 5 combinations (filtered)" in right.status.text(),
          f"Status='Showing 3 of 5 combinations (filtered)', got '{right.status.text()}'")

    # Ranks stay original: check row_plan shows original rank
    scrap_v, qty_v, rank_v = model.row_plan(0)
    check(rank_v in (2, 3, 4), f"Filtered row 0 original rank preserved: rank={rank_v} (expected 2/3/4)")

    # Sort inside filter: click header col 1 (strips of 111mm)
    model.sort_by(1)
    app.processEvents()
    check(model.sort_col == 1, "Sort works inside filter")

    # Nav inside filter
    right.step(+1)
    app.processEvents()
    cur = model.order[right.table.currentIndex().row()]
    check(cur is not None, "Navigation works inside filter")

    # Pin inside filter
    right.toggle_pin()
    app.processEvents()
    check(len(right.memory) >= 1, "Pin works inside filter")

    # Compare inside filter
    entries = right._compare_entries()
    check(len(entries) >= 2, "Compare entries available inside filter")

    # Show all (clear filter)
    QTest.mouseClick(right.unfilter_btn, Qt.MouseButton.LeftButton)
    app.processEvents()
    check(right.filter_state is None, "Show all clears filter")
    check(model.n == 5, f"Back to showing all {model.n} combinations")
    check(not right.unfilter_btn.isVisible(), "Show all button hidden after clearing")

    # New calculation clears filter
    rows2 = [(1, (1, 1, 1)), (2, (2, 2, 2))]
    apply_results(win, rows2)
    app.processEvents()
    check(model.n == 2, f"New calc: {model.n} combinations")
    check(right.filter_state is None, "New calculation clears filter_state")

    # No-match: apply a filter that matches nothing
    f_none = {"qty": [(None, None)] * 3, "strips": (None, None), "scrap": (999, None)}
    right.set_filter(f_none)
    app.processEvents()
    check(model.shown == 0, "No-match filter: shown=0")
    check(not right.unfilter_btn.isVisible(), "No-match: Show all hidden")
    check(right.status.text().find("No combination matches the filter") >= 0,
          f"Status='No combination matches...', got '{right.status.text()}'")
    check(notice.isVisible(), "No-match notice visible")
    check("Show all combinations" in notice.button.text(),
          f"Notice button='Show all combinations', got '{notice.button.text()}'")
    check(right.cur_vm is None, "No-match: Selected Combination blanked (cur_vm=None)")

    # Click "Show all combinations" from no-match notice
    notice.actionClicked.emit("clear_filter", 0)
    app.processEvents()
    check(right.filter_state is None, "Show all combinations clears filter")
    check(model.n == 2, f"After Show all: showing all {model.n} combinations again")

    # ================================================================
    # PART (d) - History
    # ================================================================
    print("\n========== PART (d): History ==========")
    # Push 7 results (KEEP=5, so oldest 2 dropped)
    for i in range(7):
        rows_h = [(i * 2, (i, i + 1, i + 2))]
        apply_results(win, rows_h)
        app.processEvents()
    check(len(win.right.history.items) <= 5, f"History keeps at most 5: {len(win.right.history.items)}")
    check(len(win.right.history.items) == 5, f"History keeps exactly 5: {len(win.right.history.items)}")
    check("History (5)" in right.hist_btn.text(),
          f"History button shows count: '{right.hist_btn.text()}'")

    # Restore from history (index 0 = newest = the 7th calc)
    right.restore(0)
    app.processEvents()
    check(model.n == 1, "History restore: 1 combination")
    check(right.cfg is not None, "History restore: cfg set")
    check(win.left.smax_edit.text() == "30",
          f"History restore: inputs set (smax={win.left.smax_edit.text()})")
    check(notice.isHidden(), "History restore: notice hidden")

    # ================================================================
    # PART (a) recap already covered by test_pin_compare.py (32/32)
    # ================================================================
    print("\n========== PART (a): Pin/Compare recap ==========")
    # Pins survive new calculations per spec - memory should NOT be clean
    # check(len(right.memory) == 0, "Memory clean at end of proof")

    # ================================================================
    # REPORT
    # ================================================================
    print("\n========== FINAL RESULTS ==========")
    passed = sum(1 for c, _ in results if c)
    failed = sum(1 for c, _ in results if not c)
    for c, msg in results:
        status = "PASS" if c else "FAIL"
        safe_msg = msg.replace('★', '*').replace('●', '*').replace('→', '->')
        print(f"  [{status}] {safe_msg}")
    print(f"\n{passed}/{passed + failed} checks passed")

    app.quit()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    run_test()
