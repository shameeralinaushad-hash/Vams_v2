# Extraction Robustness Improvements — Round 2

**File:** `ml/tender_extractor.py`

## Completed (10/10)

### #1: Per-iteration error isolation (CRITICAL)
- **Excel**: Wrapped each sheet iteration in `try/except` — one bad sheet no longer kills all items
- **PDF**: Wrapped each table parsing call in `try/except` — one bad table continues processing
- **DOCX**: Wrapped each table read and parse in `try/except`

### #2: Encrypted PDF detection (HIGH)
- Added specific detection for password/encrypted/decrypt keywords in exception messages
- Emits clear diagnostic: "PDF appears to be password-protected or encrypted"

### #3: Formula cell fallback (HIGH)
- After processing, checks if formula cells returned all None (uncached workbook)
- Emits warning: "Re-save the file in Excel to cache values"

### #4: Excel error cell filtering (HIGH)
- Added `_safe_cell_str()` helper that filters out `openpyxl.cell.error.Error` objects
- Replaced raw `str(cell).strip()` calls in both `_extract_text_content_for_llm` and `_extract_from_excel`

### #5: Truncated JSON recovery (HIGH)
- Added progressive truncation recovery for broken JSON from Gemini/Groq
- Tries removing trailing incomplete entries before giving up
- Increased Groq `max_tokens` from 4096 to 8192

### #6: gmft thread-safe init (MEDIUM)
- Added `_gmft_lock = threading.Lock()` with double-checked locking pattern
- Prevents simultaneous ~200MB model weight loading on constrained hardware

### #7: Bisect for OCR column lookup (MEDIUM)
- Replaced O(n) linear scan in `_col_index()` with O(log n) `bisect.bisect_left()`
- Added `import bisect` at module level

### #8: Table merging tolerance increase (MEDIUM)
- Changed column-count diff threshold from >1 to >2 in both `_parse_table` grid merging and `_merge_headerless_continuations`
- Handles pdfplumber returning ±2 blank columns

### #9: Photo attachment optimization (MEDIUM)
- Pre-builds inverted text→page index before the item loop
- Reduces O(items × pages) text searches to O(pages + items × matched_pages)

### #10: File size guard (MEDIUM)
- Added 100MB file size warning in `extract_items_from_file`
- Emits diagnostic: "File is very large; extraction may be slow"

## Verification
```powershell
.\.venv\Scripts\python.exe -c "from ml.tender_extractor import extract_items_from_file; print('ok')"
# Dummy .xlsx: 15 items, 10 photos
# IT No-13 .xls: 6 items
```
