# siltra - Coil Slitting Optimizer

**A professional PySide6 desktop application for optimizing coil slitting patterns to minimize scrap waste.**

Slitra helps steel service centers and slitting operations calculate the optimal way to cut master coils into narrower strips. Given a coil width, available strip sizes, and quantity requirements, it finds all valid cutting combinations — ranked by scrap percentage — so operators can choose the most material-efficient pattern.

**Target users:** Steel service centers, coil slitting operations, production planners  
**Tech stack:** Python 3.7+, PySide6, reportlab, pandas, openpyxl  
**License:** Proprietary (ZAT AL-EMAD FACTORY)

---

## Key Features

### Core Calculation
- **Exhaustive combination search** — finds all valid slitting patterns for given constraints
- **Bounded search (STEP 2B)** — when combinations exceed 1,000,000, returns the lowest-scrap 1M with clear notification
- **Coil weight & strip size independence** — changing coil count no longer affects strip fields (and vice versa)
- **Configurable scrap limits** — min/max scrap (mm), at-least-once constraint per size

### Professional UI (PySide6 v4.1.1)
- **Fixed-layout panels** — input panel, 1px separator, expanding results panel
- **Dark/Light theme switching** — instant, no restart
- **Background calculations** — QThread prevents UI freeze during large searches
- **Progress indication** — live combination count, cancelable operations

### Results & Comparison
- **Formula naming** — results shown as "Formula F1", "F2", "F3", "F4" (not "Rank 1/2/3")
- **4-way Compare Dialog** — pin up to 4 formulas side-by-side for detailed comparison
- **Per-row export** — export any selected formula to PDF/Excel
- **1M-row notification** — "Showing lowest-scrap 1,000,000 of N combinations" when bounded

### History & Suggestions
- **Persistent history** (SQLite) — stores calculation inputs & results
- **One-click suggestions** — "Explain no plan" proposes scrap min/max adjustments
- **Input restore** — reload any history entry directly into the input panel

### Export & Reporting
- **PDF reports** — professional formatted reports with formula details, knife positions, weights
- **Excel export** — structured data for further analysis
- **Preset system** — save/load complete input configurations as JSON

### Testing & Quality
- **Golden test fixtures** — test cases with expected outputs (PDF/Excel)
- **Baseline verification** — ensures calculation parity with original engine

---

## Architecture

```
src/slitra/
├── __init__.py          # Package entry point
├── app_info.py          # Version, factory name, constants, feature flags
├── core.py              # Calculation engine (find_all_combinations, bounded search)
├── reports.py           # PDF/Excel generation (reportlab, pandas)
├── slitra_window.py     # Pure UI (PySide6) — signals, widgets, layout
├── slitra_controller.py # All business logic — connects UI signals, drives calculations
├── state.py             # MemoryStore (pinned formulas, history)
└── view_models.py       # Plan view model (quantities, knives, weights, scrap)
```

**Separation of concerns:**
- `slitra_window.py` = **zero logic**, only UI + signals
- `slitra_controller.py` = **all logic**, subscribes to UI signals
- `core.py` = pure math, no Qt dependencies
- `reports.py` = export formatting, no UI dependencies

---

## Installation & Usage

### From Source

```bash
cd slitra
export PYTHONPATH=src
python -m slitra.slitra_controller
```

### Requirements
- Python 3.7+
- PySide6
- reportlab (PDF export)
- pandas + openpyxl (Excel export)

### Command Line
```bash
export PYTHONPATH=src
python -m slitra.slitra_controller   # Run application
python -m slitra.slitra_window --check  # UI skeleton self-test
```

---

## Development

### Run Tests
```bash
export PYTHONPATH=src
python -m pytest tests/
# Or run the full verification suite directly:
python tests/test_all.py
```

### Project Structure
```
├── src/slitra/           # Main package (8 Python files)
├── tests/                # Test suite + fixtures + golden files
├── dev_tools/            # UI checks, parity audits, screenshot tools
├── README.md             # This file
```

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 4.1.1   | 2024 | PySide6 rewrite complete; fixed layout; dark/light themes; background calc; Formula F1-F4 naming; 4-way compare; history suggestions |
| 3.x     | —    | Tkinter-based legacy version (archived in git history) |

---

## License & Attribution

**ZAT AL-EMAD FACTORY** — Internal tool for coil slitting optimization.
