from slitra.core import find_all_combinations_bounded, calculate_combination_details

# Test with CASE M
coil_width = 1250
strip_sizes = [111, 250]
min_scrap = 0
max_scrap = 10
at_least_once = True
num_coils = 1

combos, stopped_early, total_combinations = find_all_combinations_bounded(
    coil_width, strip_sizes, min_scrap, max_scrap, at_least_once
)
for c in combos:
    c['details'] = calculate_combination_details(tuple(c['qs']), coil_width, 10000, num_coils, strip_sizes)
    c['coil_width'] = coil_width
    c['num_coils'] = num_coils
    c['strip_sizes'] = strip_sizes
    c['min_scrap'] = min_scrap
    c['max_scrap'] = max_scrap
    c['at_least_once'] = at_least_once

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
    'total_coil_weight': 10000,
}

from slitra.reports import build_report_data, export_pdf, export_excel
report_data = build_report_data(result, 0, settings)

success = export_pdf(report_data, 'test_CASE_M_final.pdf', version='3.7.1')
print(f'PDF export: {success}')

success = export_excel(report_data, 'test_CASE_M_final.xlsx', version='3.7.1')
print(f'Excel export: {success}')