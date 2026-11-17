import sys
sys.path.insert(0, 'src')

# Test the material calculator integration with StripTable
from slitra_window import StripTable

# Create a mock view model with material data
vm = {
    'width': 1250,
    'sizes': [300, 400, 500],
    'qty': [1, 1, 1],
    'total_qty': [1, 1, 1],
    'wps': [2400.0, 3200.0, 4000.0],
    'total_w': [2400.0, 3200.0, 4000.0],
    'scrap': 50,
    'scrap_per': 400.0,
    'scrap_total': 400.0,
    'material_type': 'HR',
    'thickness_mm': 0.5,
    'theoretical_length_m': 2038.2,
}

table = StripTable()
table.show_vm(vm)
print(f'Row count: {table.rowCount()}')
print(f'Column count: {table.columnCount()}')
for r in range(table.rowCount()):
    row_data = []
    for c in range(table.columnCount()):
        item = table.item(r, c)
        row_data.append(item.text() if item else 'None')
    print(f'Row {r}: {row_data}')