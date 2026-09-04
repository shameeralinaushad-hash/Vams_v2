from io import BytesIO
from ml.tender_extractor import extract_items_from_file

with open(r'C:\Users\haide\Downloads\Technical_Offer_Annexures_A_B_C (1).xlsx', 'rb') as f:
    data = f.read()

result = extract_items_from_file(BytesIO(data), 'Technical_Offer.xlsx', include_photos=True, return_diagnostics=True)
items = result['items']
print(f'Total items extracted: {len(items)}')
print(f'Warnings: {result.get("warnings", [])}')
print()

for i, item in enumerate(items[:15]):
    has_photo = 'YES' if item.get('photo_bytes') else 'NO'
    annex = item.get('annexure', '')
    print(f'{i+1}. [{annex}] {item["description"]} | part_no={item.get("part_no", "")} | unit={item["unit"]} | price={item["unit_price"]} | photo={has_photo}')

from collections import Counter
annex_counts = Counter(item.get('annexure', 'none') for item in items)
print(f'\nBy annexure: {dict(annex_counts)}')

photo_count = sum(1 for item in items if item.get('photo_bytes'))
print(f'Items with photos: {photo_count}/{len(items)}')

# Show units
units = Counter(item['unit'] for item in items)
print(f'Units found: {dict(units)}')
