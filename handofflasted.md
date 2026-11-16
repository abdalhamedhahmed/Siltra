# Slitra Coil Slitting Optimizer — Phase 2 Implementation Handoff

**Project:** Slitra v4.1.1 (ZAT AL-EMAD FACTORY)  
**Branch:** `job-order`  
**Date:** 2026-11-16  
**Status:** Phase 2 complete, Phase 3 deferred

---

## Overview

All Phase 2 features of the Slitra Feature Implementation Plan have been implemented following the Skeleton Design Language. Phase 1 (Core Stability) was previously completed. Phase 3 (Job Order PDF Design) remains deferred pending a separate PDF mockup design.

## Files Modified

| File | Changes |
|------|---------|
| `src/slitra_window.py` | Added all Phase 2 UI dialogs, calendar picker, auto coil names, TopBar reorder |
| `src/slitra_controller.py` | Added controller handlers for job orders, coil stock, add coils to stock |
| `src/slitra_db.py` | Added `recent_consignments()` and `stock_status()` DB methods |

## Phase 2 Features Implemented

### 1. Keyboard Shortcuts Help Overlay (F1)

**File:** `src/slitra_window.py` — class `KeyboardShortcutsHelp(QDialog)`

- Non-blocking modal dialog triggered by **F1** key
- Follows skeleton design language: `SectionTitle` header, skeleton color palette (INK/MUTED), `PRIMARY_QSS` close button
- Shortcuts listed: Insert/F2 (coil weights), Enter (calculate), Esc (cancel), F1 (help), F7 (CASE W demo), F10 (Final Job Order), Up/Down (navigate results), column header sort, row click select, Pin, Compare up to 4, Ctrl+V (paste Excel), Ctrl+Return (apply coil weights)
- Wired via `QShortcut(QKeySequence("F1"), self)` → `_show_shortcuts_help()`

### 2. Recent Consignments Dropdown

**Files:** `src/slitra_db.py`, `src/slitra_controller.py`, `src/slitra_window.py`

- **DB:** New method `recent_consignments(limit=10)` returns most recent consignment names ordered by ID DESC
- **Controller:** `on_consignment_focused()` loads recent consignments when consignment field gains focus
- **UI:** `InputPanel.consignment_focused` signal emitted on focusIn; `set_recent_consignments()` attaches a `QCompleter` with `QStringListModel` (case-insensitive, contains matching)
- Consignment field auto-completes from historical consignment names

### 3. Job Order List View

**Files:** `src/slitra_window.py`, `src/slitra_controller.py`

- New dialog class `JobOrdersDialog(QDialog)` — table browsing past jobs from `jobs` table
- Columns: Job Number, Date, Status (color-coded badges: planned=green, done=blue, cancelled=red), Consignment, Formula, Total (kg)
- Follows skeleton design language: `SectionTitle` header, card-style table with alternating row colors
- New **"View Job Orders"** button on TopBar
- Controller: `on_show_job_orders()` queries `db.jobs(limit=100)` and shows the dialog

### 4. Coil Stock Dashboard

**Files:** `src/slitra_db.py`, `src/slitra_window.py`, `src/slitra_controller.py`

- **DB:** New method `stock_status()` returns all coils with remaining kg, color-coded status (full/low/empty based on remaining weight ratio), grouped by consignment
- New dialog class `CoilStockDashboard(QDialog)` — card-based grid view of all coils
- Header shows summary stats: Total coils, Full, Low, Empty, Total Remaining (kg)
- Each card shows: coil code, consignment, thickness, width, original weight, remaining-stock progress bar, remaining kg + status badge
- Color-coded: green=full, blue=low, red=empty
- New **"View Coil Stock"** button on TopBar
- Controller: `on_show_coil_stock()` queries `db.stock_status()` and shows the dialog

### 5. Add Coils to Stock (Enhanced)

**Files:** `src/slitra_window.py`, `src/slitra_controller.py`

- New dialog class `AddCoilsToStockDialog(QDialog)` — receive new coils into stock via `db.add_consignment()`
- **Calendar date picker:** `QDateEdit` with `calendarPopup=True` replaces plain text field; defaults to today (2026-11-16), format `yyyy-MM-dd`
- **Auto coil names:** Read-only first column generates `{MATERIAL}-{SEQ}` (e.g., `HR-1`, `HR-2`, `CR-1`). Auto-updates when adding/removing rows or changing material type
- Info card: Consignment name, Supplier (optional), Material Type (MaterialCombo), Received On (calendar)
- Coils table card: add/remove rows, Thickness (mm), Width (mm), Weight (kg), Notes columns
- Validates all inputs (positive numbers, all fields required) before inserting
- New **"Add Coils to Stock"** button on TopBar
- Controller: `on_add_coils_to_stock()` opens the dialog; on accept sets status "Coils added to stock"

### TopBar Reorder (per user request)

**Removed:** View Log button and its signal/controller connection

**New button order:**
1. Calculate, Cancel, Clear, Export Job Order (main actions)
2. View Job Orders, View Coil Stock, Add Coils to Stock (stock/job management)
3. Save Preset, Load Preset (presets last)

## Existing Features (Previously Implemented)

- Dynamic DB path (ProgramData for frozen EXE, hardcoded for dev)
- Auto-update check via GitHub raw file (24h interval)
- Consignment naming: `{MATERIAL}-{YYMMDD}-{SEQ}` (e.g., `HR-261116-001`)
- Job Order: Initial (editable, no job number) vs Final (locked, JO-YYYY-NNNN allocated on Final)
- MaterialCombo replaces MaterialChips (no truncation, alignment fixed)
- All input parses guarded (try/except)
- closeEvent cleans up calc threads and update timer
- Inno Setup installer script with template database copy (onlyifdoesntexist)

## Verification

- App launches cleanly: `python src/slitra_window.py`
- All new dialog classes instantiate successfully
- Layout self-check passes: `python src/slitra_window.py --check` (only pre-existing min-width issue at 1280px)
- End-to-end test: coils insert correctly with auto-generated names, calendar date captured, stock status reflects remaining kg
- Import verification: `python -c "import sys; sys.path.insert(0,'src'); import slitra_window, slitra_controller"` — OK

## Deferred

**Phase 3 — Job Order PDF Design:** No code committed. Awaiting separate PDF mockup design before implementation.

**Build & Installer:** Ready (`slitra_setup.iss`, `make_template_db.py`) but deferred until after PDF design per plan.

## Next Steps (if continuing)

1. Design Job Order PDF mockup (Phase 3)
2. Build MSI installer with template database
3. Consider coil stock dashboard links to consignment and ledger (Phase 2.4 item)
