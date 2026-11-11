import tkinter as tk
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox

# Mock filedialog and messagebox to avoid UI blocking
original_asksaveasfilename = filedialog.asksaveasfilename
original_showwarning = messagebox.showwarning
original_showerror = messagebox.showerror
original_showinfo = messagebox.showinfo

import tempfile
temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
temp_file.close()

def mock_asksaveasfilename(*args, **kwargs):
    suffix = kwargs.get('defaultextension', '.pdf')
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.close()
    return f.name

def mock_showwarning(*args, **kwargs):
    print(f"WARNING: {args[1] if len(args) > 1 else args}")

def mock_showerror(*args, **kwargs):
    print(f"ERROR: {args[1] if len(args) > 1 else args}")

def mock_showinfo(*args, **kwargs):
    print(f"INFO: {args[1] if len(args) > 1 else args}")

filedialog.asksaveasfilename = mock_asksaveasfilename
messagebox.showwarning = mock_showwarning
messagebox.showerror = mock_showerror
messagebox.showinfo = mock_showinfo

root = tk.Tk()
root.withdraw()

# Import using new architecture
from slitra.slitra_window import MainWindow
from slitra.slitra_controller import SlitraController
from slitra.core import find_all_combinations, calculate_combination_details

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
class MockTree:
    def selection(self):
        return ['mock_item']
    def item(self, item_id):
        return {'values': [1, 9, 1, 1249.0, 1.0, 0.08, 10]}

app.combos_tree = MockTree()

print('Testing export_pdf...')
try:
    app.export_pdf()
    print("PDF export completed successfully!")
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()

print()
print('Testing export_excel...')
try:
    app.export_excel()
    print("Excel export completed successfully!")
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()

root.destroy()