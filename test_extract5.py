from io import BytesIO
import zipfile, re
from PIL import Image

with open(r'C:\Users\haide\Downloads\Technical_Offer_Annexures_A_B_C (1).xlsx', 'rb') as f:
    data = f.read()

min_dim = 80

with zipfile.ZipFile(BytesIO(data)) as zf:
    media_files = sorted([n for n in zf.namelist() if n.startswith("xl/media/")])
    print(f"Total media files: {len(media_files)}")
    
    # Build media_map
    media_map = {}
    for media_path in media_files:
        img_bytes = zf.read(media_path)
        ext = media_path.rsplit(".", 1)[-1].lower()
        try:
            with Image.open(BytesIO(img_bytes)) as im:
                width, height = im.size
        except Exception:
            width, height = 0, 0
        if width < min_dim or height < min_dim:
            print(f"  SKIP {media_path}: {width}x{height} < {min_dim}")
            continue
        media_map[media_path] = {"bytes": img_bytes, "ext": ext, "width": width, "height": height}
    
    print(f"Media map (after size filter): {len(media_map)} images")
    
    # Check drawing rels
    dr = "xl/drawings/drawing1.xml"
    dr_rels_path = f"xl/drawings/_rels/{dr.split('/')[-1]}.rels"
    print(f"\nLooking for rels: {dr_rels_path}")
    print(f"Exists: {dr_rels_path in zf.namelist()}")
    
    if dr_rels_path in zf.namelist():
        rels_xml = zf.read(dr_rels_path).decode("utf-8", errors="ignore")
        rid_to_media = {}
        for rm in re.finditer(r'Id="(rId\d+)"[^>]*Target="(/?xl/media/[^"]+)"', rels_xml):
            rid_to_media[rm.group(1)] = rm.group(2).lstrip("/")
        print(f"rid_to_media: {len(rid_to_media)} entries")
        for k, v in list(rid_to_media.items())[:3]:
            print(f"  {k} -> {v} (in media_map: {v in media_map})")
