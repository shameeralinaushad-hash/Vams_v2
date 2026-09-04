import zipfile, re
from io import BytesIO

with open(r'C:\Users\haide\Downloads\Technical_Offer_Annexures_A_B_C (1).xlsx', 'rb') as f:
    data = f.read()

with zipfile.ZipFile(BytesIO(data)) as zf:
    # Check workbook.xml for sheet names
    wb_xml = zf.read("xl/workbook.xml").decode("utf-8", errors="ignore")
    print("workbook.xml (first 1500 chars):")
    print(wb_xml[:1500])
    print()
    
    # Find sheet names
    sheets = re.findall(r'<sheet\s+name="([^"]+)"', wb_xml)
    print(f"Sheet names from workbook.xml: {sheets}")
    
    # Check sheet rels
    sheet_rels = sorted([n for n in zf.namelist() if 'worksheets/_rels' in n])
    print(f"Sheet rels files: {sheet_rels}")
    
    for rf in sheet_rels:
        xml = zf.read(rf).decode("utf-8", errors="ignore")
        draws = re.findall(r'Target="(/?xl/drawings/drawing\d+\.xml)"', xml)
        print(f"  {rf} -> {draws}")
