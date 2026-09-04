import zipfile, io, re

f = open(r'C:\Users\haide\Downloads\Technical_Offer_Annexures_A_B_C (1).xlsx', 'rb')
data = f.read()
f.close()

with zipfile.ZipFile(io.BytesIO(data)) as zf:
    sheet_rels = sorted([n for n in zf.namelist() if 'worksheets/_rels' in n])
    print('Sheet rels:', sheet_rels)
    for rf in sheet_rels:
        xml = zf.read(rf).decode('utf-8', errors='ignore')
        draws = re.findall(r'Target="([^"]*drawing[^"]*)"', xml)
        print(f'  {rf} -> {draws}')

    # Now check: which rId in the rels maps to which drawing
    # Then check which sheet references which rId
    print()
    for rf in sheet_rels:
        xml = zf.read(rf).decode('utf-8', errors='ignore')
        print(f'\n--- {rf} ---')
        print(xml[:1500])
