# 23 Extraction Improvements — Implementation Plan

**File:** `ml/tender_extractor.py`

## Already Applied (#1-#4)
- ✅ #1: pending_desc false positives — section headers and label-only rows now skipped
- ✅ #2: Header detection — expanded keywords, scan range 15→30 rows
- ✅ #3: Qty/Price column ordering — leftmost numeric = qty, rightmost = price, header-refined
- ✅ #4: Merged cells — `_fill_merged_cells()` helper fills None cells from top-left anchor

## Batch 2: PDF Extraction Fixes

### #7 Remove MAX_ITEMS×4 row cap (line 219, 2286)
**Change:** Remove early-break `if sum(len(t) for t in all_tables) >= MAX_ITEMS * 4: break`
- Line 219: Delete the `if` block (lines 218-220)
- Line 2286: Same deletion in `detect_document_type()`
**Why:** Caps extraction at ~80 items, truncating legitimate large tenders.

### #8 Better scanned PDF detection (line 271)
**Change:** Lower text threshold from `< 20` to `< 100`
```python
# Before:
if not items and len(combined_text.strip()) < 20 and FITZ_AVAILABLE:
# After:
if not items and len(combined_text.strip()) < 100 and FITZ_AVAILABLE:
```
**Why:** Some PDFs with 20-50 chars of extractable text (headers/footers only) still need OCR.

### #9 OCR preprocessing for direct image uploads (line 962-999)
**Change:** Apply preprocessing pipeline before OCR in `_extract_from_image()`:
```python
def _extract_from_image(file_stream, diagnostics=None):
    try:
        file_stream.seek(0)
        img = Image.open(file_stream)
        img = _deskew_image(img)
        # NEW: preprocess for better OCR
        img = _preprocess_for_ocr(img, diagnostics)
        img = img.convert("L")
        # ... rest unchanged
```
Add `_preprocess_for_ocr()` helper:
```python
def _preprocess_for_ocr(pil_image, diagnostics=None):
    """Apply denoise, threshold, contrast for better OCR accuracy."""
    if not CV2_AVAILABLE:
        return pil_image
    try:
        import cv2
        import numpy as np
        arr = np.array(pil_image.convert("L"))
        # Adaptive threshold for uneven lighting
        arr = cv2.adaptiveThreshold(arr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 31, 10)
        # Light denoise
        arr = cv2.medianBlur(arr, 3)
        return Image.fromarray(arr)
    except Exception:
        return pil_image
```

### #10 Better table column-count merging (line 244-256)
**Change:** Add tolerance of ±1 column when merging tables:
```python
# Before (line 246):
if combined_grid and cols != last_col_count:
# After:
if combined_grid and abs(cols - last_col_count) > 1:
```
Same tolerance in `_merge_headerless_continuations()` (line 2394):
```python
# Before:
if header_idx is None and cols > 0 and cols == prev_cols:
# After:
if header_idx is None and cols > 0 and abs(cols - prev_cols) <= 1:
```
**Why:** pdfplumber can return ±1 blank columns depending on border detection.

### #11 Increase deskew tolerance (line 1273)
**Change:** `max_angle=15` → `max_angle=30`
```python
def _deskew_image(pil_image, max_angle=30):
```
**Why:** Phone-photographed tenders can skew up to 20°.

## Batch 3: AI Extraction Fixes

### #12 Gemini: chunk large PDFs
**Change:** In the Gemini extraction section, if pdf has >20 pages, split into chunks of 15 pages:
```python
# Find the Gemini PDF processing section
# If len(fitz_doc) > 20: chunk into groups of 15 pages
# Process each chunk separately, merge results
```

### #13 Groq: increase vision page count (line ~480-490)
**Change:** Replace `pdf.pages[:1]` with `pdf.pages[:3]` in Groq extraction:
```python
# Before:
for i, page in enumerate(pdf.pages[:1]):
# After:
for i, page in enumerate(pdf.pages[:3]):
```
Also increase DPI for Groq images:
```python
# Before: 100 DPI
# After: 250 DPI
```

### #14 Retry on HTTP 429/500
**Change:** Add retry decorator or manual retry logic around AI API calls:
```python
import time
def _retry_api_call(func, max_retries=2, *args, **kwargs):
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries or not any(code in str(e) for code in ["429", "500", "503"]):
                raise
            time.sleep(2 ** attempt)
```

### #15 Reuse Gemini client
**Change:** In the Gemini extraction section, create the client once and reuse:
```python
# Before: new client per call
# After: module-level or cached client
_genai_client = None
def _get_genai_client():
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client()
    return _genai_client
```

## Batch 4: Photo Extraction Fixes

### #16 Remove unnecessary PyMuPDF gate
**Change:** The `.xlsx` photo extraction already works with openpyxl. Remove the comment/gate that suggests PyMuPDF is needed:
```python
# Line ~2040-2045: Remove any "requires PyMuPDF" gate for xlsx extraction
# openpyxl handles xlsx images fine
```

### #17 DOCX photo-item pairing
**Change:** In DOCX extraction, pair photos with items by finding the nearest heading before each image:
```python
# In _extract_from_docx(), after extracting photos:
# Find headings (paragraphs with style containing 'Heading')
# Pair each photo with the nearest preceding heading
```

### #18 Stable image dedup hash (line ~2070)
**Change:** Replace `hash()` with `hashlib.md5()`:
```python
# Before:
photo_id = hash(img_bytes) % 100000
# After:
import hashlib
photo_id = int(hashlib.md5(img_bytes).hexdigest()[:8], 16) % 100000
```

### #19 Support absoluteAnchor (line ~2050)
**Change:** Add `absoluteAnchor` to the regex:
```python
# Before:
r'<(?:xdr:)?(?:one|two)CellAnchor[^>]*>'
# After:
r'<(?:xdr:)?(?:one|two)CellAnchor[^>]*>|<absoluteAnchor[^>]*>'
```

## Batch 5: Classification Fixes

### #20 Fix strict "ser" header match (line 2122)
**Change:** Allow "sno" and "sl.no" as alternatives:
```python
# Before:
has_ser = any(c in ("ser", "ser.", "s.") for c in cells)
# After:
has_ser = any(c in ("ser", "ser.", "s.", "sno", "sl.no", "sl.no.", "s.no", "sr.no", "sr.") for c in cells)
```

### #21 Excel tender classification (line ~2240-2250)
**Change:** Add Excel-specific detection in `detect_document_type()`:
```python
if ext in {"xlsx", "xls"}:
    # Check if any sheet looks like a schedule
    for sheet_name in workbook.sheetnames:
        sheet = workbook[sheet_name]
        rows = _fill_merged_cells(sheet)
        for row in rows[:5]:
            if _looks_like_schedule_header(row):
                return "tender_dual_table"
    return "quotation"
```

### #22 Spec table: scan all columns (line 2176-2183)
**Change:** Scan first 3 columns instead of just the first:
```python
def _count_spec_markers_in_first_column(table):
    found = set()
    for row in table[:8]:
        if not row:
            continue
        # Check first 3 columns
        for col_idx in range(min(3, len(row))):
            cell = str(row[col_idx] or "").strip().lower()
            for w in _SPEC_TABLE_MARKERS:
                if cell == w or cell.startswith(w + " ") or cell.startswith(w + ":"):
                    found.add(w)
    return len(found)
```

## Batch 6: Cross-cutting

### #6 Thread-safe error state
**Change:** Use `threading.Lock()` around any shared mutable state in extraction functions.

## Verification
After implementation, verify with:
```powershell
.\.venv\Scripts\python.exe -c "from ml.tender_extractor import extract_items_from_file; print('import ok')"
.\.venv\Scripts\python.exe -m pytest tests -q
```
Test with:
- `Dummy_Technical_Offer.xlsx` (15 items, 15 photos)
- `IT No-13 FY-2025-26.xls` (290KB, 6 JPEG images)
- `Technical_Offer_Annexures_A_B_C.xlsx` (61 images)
