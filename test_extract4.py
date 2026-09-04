from io import BytesIO
from ml.tender_extractor import _extract_images_from_excel, FITZ_AVAILABLE

print(f"FITZ_AVAILABLE: {FITZ_AVAILABLE}")

with open(r'C:\Users\haide\Downloads\Technical_Offer_Annexures_A_B_C (1).xlsx', 'rb') as f:
    data = f.read()

# Debug: manually check the ZIP
import zipfile, re
with zipfile.ZipFile(BytesIO(data)) as zf:
    media = [n for n in zf.namelist() if n.startswith("xl/media/")]
    print(f"Media files in ZIP: {len(media)}")
    drawings = [n for n in zf.namelist() if re.match(r"xl/drawings/drawing\d+\.xml", n)]
    print(f"Drawing files: {drawings}")
    
    for dr in drawings:
        xml = zf.read(dr).decode("utf-8", errors="ignore")
        anchors = re.findall(r'<oneCellAnchor>.*?</oneCellAnchor>', xml, re.DOTALL)
        print(f"  {dr}: {len(anchors)} anchors")
        for a in anchors[:2]:
            rid = re.search(r'r:embed="(rId\d+)"', a)
            row = re.search(r'<from>.*?<row>(\d+)</row>', a, re.DOTALL)
            print(f"    rid={rid.group(1) if rid else None}, row={row.group(1) if row else None}")

photos = _extract_images_from_excel(BytesIO(data))
print(f"\nPhotos returned: {len(photos)} sheets")
for sheet, pics in photos.items():
    print(f"  Sheet '{sheet}': {len(pics)} images")
