from io import BytesIO
from ml.tender_extractor import _extract_images_from_excel, _MIN_IMG_DIM

with open(r'C:\Users\haide\Downloads\Technical_Offer_Annexures_A_B_C (1).xlsx', 'rb') as f:
    data = f.read()

photos = _extract_images_from_excel(BytesIO(data), _MIN_IMG_DIM)
for sheet, pics in photos.items():
    print(f"Sheet '{sheet}': {len(pics)} images")
    for p in pics[:5]:
        print(f"  row_index={p['row_index']}, ext={p['ext']}, size={p['width']}x{p['height']}")
    if len(pics) > 5:
        print(f"  ... and {len(pics)-5} more")
