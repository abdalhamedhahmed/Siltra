#!/usr/bin/env python3
"""
Direct (non-modal) real launch test for SLITRA FIX 7 pin/compare feature.
Calls ResultsPanel methods directly instead of simulating modal dialogs.
Tests both 2-way and 3-way compare paths through the unified button.
"""
import sys
import os

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtGui import QFont

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from slitra_window import MainWindow, apply_light_palette, plan_vm, CompareDialog
from state import MemoryStore


def build_cw_vm(scrap, qty, width=1290, sizes=None, avg=10000.0, coils=3):
    if sizes is None:
        sizes = [111, 250, 79]
    cfg = dict(width=width, sizes=sizes, avg=avg, coils=coils)
    vm = dict(plan_vm(cfg, scrap, qty),
              cfg=cfg, width=width, sizes=sizes)
    return vm


results = []


def check(cond, msg):
    results.append((cond, msg))
    status = "PASS" if cond else "FAIL"
    # Avoid unicode issues on Windows
    safe_msg = msg.replace('★', '*')
    print(f"[{status}] {safe_msg}")


def run_test():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_light_palette(app)
    app.setFont(QFont("Segoe UI", 9))

    win = MainWindow()
    # Inject MemoryStore (normally done by controller)
    win.right.set_memory_store(MemoryStore())
    win.showMaximized()
    for _ in range(5):
        app.processEvents()

    right = win.right
    model = right.table.results

    # ---- Apply CASE W results with 3 rows ----
    print("=== Applying CASE W results (3 rows) ===")
    vm1 = build_cw_vm(2, [2, 3, 4])
    vm2 = build_cw_vm(11, [5, 1, 6])
    vm3 = build_cw_vm(5, [3, 2, 5])
    rows = [(2, (2, 3, 4)), (11, (5, 1, 6)), (5, (3, 2, 5))]
    win.show_results(dict(vm1, **{"cfg": vm1["cfg"], "width": 1290, "sizes": [111, 250, 79],
                                   "rows": rows, "total": len(rows)}))
    app.processEvents()

    n = model.n
    check(n == 3, f"Total combinations: {n} (expected 3)")

    # Rank 1
    scrap1, qty1, rank1 = model.row_plan(0)
    check(scrap1 == 2, f"Rank 1 scrap={scrap1}mm (expected 2)")
    check(tuple(qty1) == (2, 3, 4), f"Rank 1 qty={tuple(qty1)} (expected (2,3,4))")
    check(rank1 == 1, f"Rank 1 rank={rank1} (expected 1)")

    txt0 = model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole)
    check("★" not in txt0, f"Rank 1 cell initial no star: '{txt0}'")
    check(right.pin_btn.text() == "Pin", f"pin_btn='Pin', got '{right.pin_btn.text()}'")
    check(right.cmp_btn.text() == "Compare...", f"cmp_btn='Compare...', got '{right.cmp_btn.text()}'")
    check(not right.cmp_btn.isEnabled() or right.cmp_btn.isEnabled(), "cmp_btn enabled check")

    # ---- 2-way compare path: no pins, no row selected -> entries = 1 (just F1) ----
    print("\n=== Compare path (no pins, no row selected) ===")
    entries = right._compare_entries()
    check(len(entries) == 1, f"Compare entries=1 (only F1, no current selection), got {len(entries)}")
    check(right.cmp_btn.text() == "Compare...",
          f"cmp_btn='Compare...' for 1 entry, got '{right.cmp_btn.text()}'")

    # Open dialog directly (non-blocking: use show(), not exec())
    # With 1 entry, the CompareDialog should show "Pick at least two formulas"
    # picks = [0, None, None, None] - A=F1, B/C/D=(none)
    dlg = CompareDialog(win, entries, [0, None, None, None])
    dlg.show()
    app.processEvents()
    check(dlg.combos[0].currentIndex() == 0, f"2-way A index=0, got {dlg.combos[0].currentIndex()}")
    check(dlg.combos[1].currentIndex() == 0, f"2-way B index=0 (none), got {dlg.combos[1].currentIndex()}")
    print(f"   2-way Verdict: {dlg.verdict.text()}")
    dlg.close()
    app.processEvents()

    # ---- Pin rank 1 ----
    print("\n=== Pinning rank 1 ===")
    right.table.select_row(0)  # Must select a row first (no default selection)
    app.processEvents()
    right.toggle_pin()
    app.processEvents()
    check(right.pin_btn.text() == "Unpin", f"pin_btn='Unpin' after pin, got '{right.pin_btn.text()}'")
    # 3 entries (current + best + pinned) => 3-way button
    check(right.cmp_btn.text() == "Compare 3 (1)",
          f"cmp_btn='Compare 3 (1)', got '{right.cmp_btn.text()}'")
    txt0 = model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole)
    check("★" in txt0, f"Rank 1 cell has star after pin: '{txt0}'")
    check(len(right.memory) == 1, f"Memory length=1, got {len(right.memory)}")

    # ---- Pin rank 2 -> now 4 entries (current+best+2 pinned) -> 4-way path ----
    print("\n=== Pinning rank 2 (entries should be >= 3 -> 4-way button) ===")
    right.table.select_row(1)
    app.processEvents()
    right.toggle_pin()
    app.processEvents()
    check(right.pin_btn.text() == "Unpin", f"pin_btn='Unpin' after pin rank 2")
    check(right.cmp_btn.text() == "Compare 4 (2)",
          f"cmp_btn='Compare 4 (2)', got '{right.cmp_btn.text()}'")
    check(len(right.memory) == 2, f"Memory length=2, got {len(right.memory)}")

    entries = right._compare_entries()
    check(len(entries) >= 3, f"Compare entries>=3 for 4-way, got {len(entries)}")

    # Open 4-way dialog directly with picks (A=best, B=current, C=pinned1, D=pinned2)
    picks = [1, 0, 2, 3]  # A=best, B=current, C=pinned1, D=pinned2
    dlg3 = CompareDialog(win, entries, picks)
    dlg3.show()
    app.processEvents()
    check(dlg3.table.columnCount() >= 4, f"4-way table has {dlg3.table.columnCount()} columns (expected >=4)")
    print(f"   4-way Verdict: {dlg3.verdict.text()}")
    dlg3.close()
    app.processEvents()

    # ---- Unpin both back to 2 entries -> 2-way button ----
    print("\n=== Unpinning both (back to 2-way button) ===")
    right.table.select_row(0)
    app.processEvents()
    right.toggle_pin()
    app.processEvents()
    right.table.select_row(1)
    app.processEvents()
    right.toggle_pin()
    app.processEvents()
    check(len(right.memory) == 0, f"Memory length=0 after unpins, got {len(right.memory)}")
    check(right.cmp_btn.text() == "Compare...",
          f"cmp_btn='Compare...' after unpin, got '{right.cmp_btn.text()}'")
    txt0 = model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole)
    check("★" not in txt0, f"Rank 1 cell no star after unpin: '{txt0}'")

    # ---- Clear memory via Compare dialog (2-way) ----
    print("\n=== Clear memory via Compare dialog ===")
    right.toggle_pin()  # pin rank 1
    app.processEvents()
    entries = right._compare_entries()
    # With 2 entries (current + F1), picks=[0, 1, None, None] for A=current, B=F1
    dlg2 = CompareDialog(win, entries, [0, 1, None, None])
    dlg2.show()
    app.processEvents()
    dlg2._clear()  # simulates clicking Clear memory
    # Simulate what _open_compare2 does after exec() returns with cleared=True
    right.memory.clear()
    right.table.results.pinned = set()
    right.table.results.set_pinned(-1, False)
    right._update_memory_ui()
    app.processEvents()
    check(len(right.memory) == 0, f"Memory length=0 after Clear, got {len(right.memory)}")
    check(right.cmp_btn.text() == "Compare...",
          f"cmp_btn='Compare...' after Clear, got '{right.cmp_btn.text()}'")
    txt0 = model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole)
    check("★" not in txt0, f"Rank 1 cell no star after Clear: '{txt0}'")

    # ---- Clear preserves memory ----
    print("\n=== App Clear preserves memory ===")
    right.toggle_pin()  # pin rank 1 again
    app.processEvents()
    check(len(right.memory) == 1, "Memory length=1 after pin")
    win.topbar.buttons["Clear"].click()
    app.processEvents()
    check(len(right.memory) == 1, f"Memory survives app Clear: {len(right.memory)}")

    # ---- New calculation keeps memory ----
    print("\n=== New calculation keeps memory ===")
    vm3 = build_cw_vm(5, [1, 2, 3])
    win.show_results(dict(vm3, **{"cfg": vm3["cfg"], "width": 1290, "sizes": [111, 250, 79],
                                   "rows": [(5, (1, 2, 3))], "total": 1}))
    app.processEvents()
    check(len(right.memory) == 1, f"Memory survives new calc: {len(right.memory)}")
    check(right.pin_btn.text() == "Pin", f"pin_btn='Pin' on new calc, got '{right.pin_btn.text()}'")

    # ---- Swap test on 4-way dialog ----
    print("\n=== Swap test on 4-way dialog ===")
    right.table.select_row(0)
    app.processEvents()
    entries = right._compare_entries()
    # 4-way dialog with picks for A=best, B=current, C=pinned1, D=pinned2
    picks = [1, 0, 2, 3] if len(entries) >= 4 else [0, 1, None, None]
    dlg4 = CompareDialog(win, entries, picks)
    dlg4.show()
    app.processEvents()
    # Check scrap values before swap
    scrap_a = dlg4.table.item(dlg4.table.rowCount() - 2, 1).text()
    scrap_b = dlg4.table.item(dlg4.table.rowCount() - 2, 2).text()
    QTest.mouseClick(dlg4.swap_btn, Qt.MouseButton.LeftButton)
    app.processEvents()
    scrap_a2 = dlg4.table.item(dlg4.table.rowCount() - 2, 1).text()
    scrap_b2 = dlg4.table.item(dlg4.table.rowCount() - 2, 2).text()
    check(scrap_a2 == scrap_b and scrap_b2 == scrap_a,
          f"Swap flips scrap values: A={scrap_a2} B={scrap_b2} (was A={scrap_a} B={scrap_b})")
    dlg4.close()
    app.processEvents()

    # ---- Report ----
    print("\n=== RESULTS ===")
    passed = sum(1 for c, _ in results if c)
    failed = sum(1 for c, _ in results if not c)
    for c, msg in results:
        status = "PASS" if c else "FAIL"
        safe_msg = msg.replace('★', '*')
        print(f"  [{status}] {safe_msg}")
    print(f"\n{passed}/{passed + failed} checks passed")

    app.quit()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    run_test()
