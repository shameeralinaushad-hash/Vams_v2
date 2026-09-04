from io import BytesIO
from ml.tender_extractor import _extract_images_from_excel

with open(r'C:\Users\haide\Downloads\Technical_Offer_Annexures_A_B_C (1).xlsx', 'rb') as f:
    data = f.read()

photos = _extract_images_from_excel(BytesIO(data))
print(f"Photos returned: type={type(photos)}")
for sheet, pics in photos.items():
    print(f"\n  Sheet '{sheet}': {len(pics)} images")
    for p in pics[:3]:
        print(f"    row_index={p['row_index']}, ext={p['ext']}, size={p['width']}x{p['height']}")
