import sys
sys.path.insert(0, r'C:\Users\Abdalhamed Ahmed\Desktop\fac-1327')
from slitra.core import find_all_combinations_bounded, calculate_combination_details
from slitra.reports import build_report_data, export_pdf, export_excel
import os

# Test case: 8 coils, same as user request
coil_width = 1250
strip_sizes = [111, 250]
min_scrap = 0
max_scrap = 10
at_least_once = True
num_coils = 8
total_coil_weight = 80000  # 10000 per coil * 8

combos, stopped_early, total_combinations = find_all_combinations_bounded(
    coil_width, strip_sizes, min_scrap, max_scrap, at_least_once
)

print(f'Found {len(combos)} combinations (stopped_early={stopped_early}, total={total_combinations})')

# Add details to each combo
for c in combos:
    c['details'] = calculate_combination_details(tuple(c['qs']), coil_width, total_coil_weight, num_coils, strip_sizes)
    c['coil_width'] = coil_width
    c['num_coils'] = num_coils
    c['strip_sizes'] = strip_sizes
    c['min_scrap'] = min_scrap
    c['max_scrap'] = max_scrap
    c['at_least_once'] = at_least_once
    c['total_coil_weight'] = total_coil_weight

result = {
    'all_combinations': combos,
    'filtered_combinations': combos,
    'total_combinations': total_combinations,
    'stopped_early': stopped_early,
}

settings = {
    'coil_width': coil_width,
    'num_coils': num_coils,
    'strip_sizes': strip_sizes,
    'min_scrap': min_scrap,
    'max_scrap': max_scrap,
    'at_least_once': at_least_once,
    'total_coil_weight': total_coil_weight,
}

# Build report data
report_data = build_report_data(result, 0, settings)

print(f'Selected combo: {report_data["selected_combination"]["qs"]}')
print(f'Scrap: {report_data["selected_combination"].get("scrap_mm", 0):.1f}mm ({report_data["selected_combination"].get("scrap_pct", 0):.2f}%)')
print(f'Weight verification: diff={report_data["weight_verification"]["difference"]:.6f}kg, passes={report_data["weight_verification"]["passes"]}')

# Check strip data
print(f'\nStrip data:')
for s in report_data['strip_data']:
    print(f"  Size: {s['size']}mm, Qty/coil: {s['qty_per_coil']}, Total qty: {s['qty_total']}")

# Export PDF
pdf_file = r'test_8coils.pdf'
success = export_pdf(report_data, pdf_file, version='3.7.1')
print(f'\nPDF export: {success}')
if success and os.path.exists(pdf_file):
    print(f'  PDF size: {os.path.getsize(pdf_file)} bytes')
    # os.remove(pdf_file)

# Export Excel
xlsx_file = r'test_8coils.xlsx'
success = export_excel(report_data, xlsx_file, version='3.7.1')
print(f'Excel export: {success}')
if success and os.path.exists(xlsx_file):
    print(f'  Excel size: {os.path.getsize(xlsx_file)} bytes')
    # os.remove(xlsx_file)

print('\nTest completed successfully!')