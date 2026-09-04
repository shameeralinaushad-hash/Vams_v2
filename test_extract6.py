from io import BytesIO
import zipfile, re

with open(r'C:\Users\haide\Downloads\Technical_Offer_Annexures_A_B_C (1).xlsx', 'rb') as f:
    data = f.read()

with zipfile.ZipFile(BytesIO(data)) as zf:
    rels_xml = zf.read("xl/drawings/_rels/drawing1.xml.rels").decode("utf-8", errors="ignore")
    print("Full rels XML:")
    print(rels_xml[:2000])
    print()
    
    # Try different regex patterns
    p1 = re.findall(r'Id="(rId\d+)"[^>]*Target="(/?xl/media/[^"]+)"', rels_xml)
    print(f"Pattern 1: {p1[:3]}")
    
    p2 = re.findall(r'Target="(/?xl/media/[^"]+)"', rels_xml)
    print(f"Pattern 2 (target only): {p2[:3]}")
    
    p3 = re.findall(r'Id="(rId\d+)"', rels_xml)
    print(f"Pattern 3 (id only): {p3[:3]}")
    
    # Check the actual format
    print("\nFirst 500 chars raw:")
    for i, ch in enumerate(rels_xml[:500]):
        if i < 200:
            pass  # skip
    print(rels_xml[:500])
