import tkinter as tk
root = tk.Tk()
root.withdraw()

# Import using new architecture
from slitra.slitra_window import MainWindow
from slitra.slitra_controller import SlitraController
from slitra.core import find_all_combinations, calculate_combination_details
from slitra.app_info import VERSION

app = MainWindow()
controller = SlitraController(app)

# Create mock combo data like what the app would have
combos, _ = find_all_combinations(1250, [111, 250], 0, 10, True)
for c in combos:
    c['details'] = calculate_combination_details(c['qs'], 1250, 10000, 1, [111, 250])

# Set app state like after calculation
app.all_combinations = combos
app.filtered_combinations = combos
app.current_num_coils = 1
app.current_total_weight = 10000
app.current_coil_width = 1250
app.current_strip_sizes = [111, 250]
app.current_min_scrap_mm = 0
app.current_max_scrap_mm = 10

# Create mock combos_tree with selection
import tempfile
with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
    pdf_path = f.name

print('Testing export_pdf...')
try:
    app.export_pdf()
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()

root.destroy()