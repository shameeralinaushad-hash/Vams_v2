import os
import re
import sys
import io
import json
import base64
import threading
import tempfile
import pdfplumber
import openpyxl
try:
    import xlrd
    XLRD_AVAILABLE = True
except ImportError:
    XLRD_AVAILABLE = False
from PIL import Image
import pytesseract
import docx
# Lazy top-level import; PyMuPDF is only needed for image extraction /
# AI-vision page rendering, so a missing install shouldn't break text-only
# extraction for users who never call those code paths.
try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False
# Try importing Groq SDK
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

import hashlib
import time
import bisect

# Try importing Gemini SDK.
# NOTE: `google-generativeai` (the old `import google.generativeai as genai`
# / `genai.GenerativeModel(...)` API) is fully deprecated and reached
# end-of-life on Nov 30, 2025 — the repo is archived and no longer receives
# updates or bug fixes. This uses the current, actively-maintained
# `google-genai` package (`pip install google-genai`), imported as
# `from google import genai` and driven through a `genai.Client(...)`.
try:
    from google import genai
    from google.genai import types as genai_types
    GEMINI_AVAILABLE = True
    _gemini_client = None
    _gemini_client_lock = threading.Lock()
    def _get_gemini_client():
        global _gemini_client
        if _gemini_client is None:
            api_key = os.environ.get("GEMINI_API_KEY")
            if api_key:
                with _gemini_client_lock:
                    if _gemini_client is None:
                        _gemini_client = genai.Client(api_key=api_key)
        return _gemini_client
except ImportError:
    GEMINI_AVAILABLE = False
    _gemini_client = None
    _get_gemini_client = None

# Try importing gmft (table extraction toolkit built on Microsoft's
# Table Transformer) — heavier dependency, optional. Falls back to the
# existing Tesseract-based reconstruction in _reconstruct_table_from_ocr
# if this isn't installed.
# NOTE: replaces the previous PaddleOCR/PP-StructureV3 integration.
# PP-StructureV3 chains five separate deep-learning stages (orientation
# classifier, layout detection, OCR, table structure recognition,
# post-processing) and documented CPU memory use of 1-4GB+ per call
# (with reported regressions far above that) — too heavy for constrained
# hardware. gmft/Table Transformer is a single detection model, MIT
# licensed, and reads a PDF's existing text layer directly when
# available instead of always re-OCRing.
try:
    from gmft.auto import AutoTableDetector, AutoTableFormatter
    from gmft.pdf_bindings import PyPDFium2Document
    GMFT_AVAILABLE = True
except ImportError:
    GMFT_AVAILABLE = False

_gmft_detector = None
_gmft_formatter = None

# Explicitly set Tesseract executable path for Windows environments
if sys.platform.startswith("win"):
    default_win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(default_win_path):
        pytesseract.pytesseract.tesseract_cmd = default_win_path
# =========================================================================
# PERFORMANCE: pre-compiled regex / shared constants
# Compiling these once at import time (instead of inside every _parse_*
# call) avoids re-compiling the same pattern for every row/line, which
# matters a lot on large multi-page tenders (50-100+ pages of text).
# =========================================================================
MAX_ITEMS = 500
# Serializes extraction end-to-end (one document at a time). This box has
# 4GB RAM and 4 old cores - Tesseract/pdfplumber/PyMuPDF all spike memory
# and CPU per page, and running two documents through them concurrently
# risks swapping or an OOM kill rather than just being slower. A single
# global lock trades away concurrency the hardware can't actually support
# for predictable, crash-free behaviour: extra requests queue instead of
# competing for the same limited RAM.
_EXTRACTION_LOCK = threading.Lock()
_error_lock = threading.Lock()
# Tracks the last extraction error message so routes can surface the real
# cause to the UI (e.g. network failure vs "no items found").
_last_extraction_error = None

# Singleton Groq client (avoid recreating per-request)
_groq_client = None
_groq_client_lock = threading.Lock()

def _get_groq_client():
    global _groq_client
    if _groq_client is not None:
        return _groq_client
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    with _groq_client_lock:
        if _groq_client is None:
            from groq import Groq
            _groq_client = Groq(api_key=api_key)
    return _groq_client

def _set_extraction_error(msg):
    """Thread-safe setter for _last_extraction_error."""
    global _last_extraction_error
    with _error_lock:
        _last_extraction_error = msg


def _normalize_text(text):
    """Normalize extracted text before parsing. Handles Unicode quirks,
    line-break hyphenation repair, page number removal, and whitespace
    normalization — critical preprocessing for reliable regex matching."""
    if not text:
        return ""
    import unicodedata
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r'-\n(\w)', r'\1', text)          # repair line-break hyphenation
    text = re.sub(r'\n\s*\d+\s*\n', '\n', text)    # remove page numbers between lines
    text = re.sub(r'[ \t]+', ' ', text)              # collapse horizontal whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)           # limit consecutive newlines
    return text.strip()


# Tesseract engine/segmentation tuning - free accuracy wins, no extra
# dependencies or compute cost. `--oem 1` selects the LSTM-only engine
# (generally more accurate than the legacy engine on modern Tesseract
# installs). `--psm` (page segmentation mode) is picked per use case:
# table pages read better as one uniform block, sparse text-detection
# passes (used only to build a text/non-text pixel mask, not to actually
# transcribe) do better assuming no particular layout at all, and a
# general uploaded image's layout is unknown so full auto-detection is
# safest.
_TESS_CONFIG_TABLE = "--oem 1 --psm 6"
_TESS_CONFIG_SPARSE = "--oem 1 --psm 11"
_TESS_CONFIG_GENERAL = "--oem 1 --psm 3"
_NUMBER_RE = re.compile(r"(\d+(?:,\d{3})*(?:\.\d+)?)")
_LINE_NUMBERS_RE = re.compile(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b")
_UNIT_RE = re.compile(r"\b(nos|pcs|set|sets|kg|kgs|m|mtr|mt|box|pack|pkt|ea|each|ream|roll|ft|btl|can|ltr|l|gm|g|ton|mt|cu|sq|pair|doz|bag|drum|bdle|roll|roll|unit|a/u|au)\b", re.IGNORECASE)
_UNIT_STRIP_RE = re.compile(r"\b(nos|pcs|set|sets|kg|kgs|m|mtr|mt|box|pack|pkt|ea|each|ream|roll|ft|btl|can|ltr|l|gm|g|ton|mt|cu|sq|pair|doz|bag|drum|bdle|roll|roll|unit|a/u|au)\b.*$", re.IGNORECASE)
_NUMBER_STRIP_RE = re.compile(r"[\d,]+(?:\.\d+)?.*$")
_PURE_NUMBER_RE = re.compile(r"^\d+(\.\d+)?$")
_PURE_SNO_RE = re.compile(r"^(s|sl|sr)?\.?\s*no\.?\s*\d+$", re.IGNORECASE)
_LEADING_SNO_RE = re.compile(r"^(?:s|sl|sr)?\.?\s*no\.?\s*\d+\s*", re.IGNORECASE)
_LEADING_INDEX_RE = re.compile(r"^\d+[\.\)]?\s*")
_WHITESPACE_RE = re.compile(r"\s+")
_PLAIN_TEXT_IGNORE_KEYWORDS = [
    "quotation", "procurement", "organization", "islamabad", "subject:", "date:",
    "ref #", "sr. no", "unit price", "grand total", "subtotal", "particulars",
    "description", "quantity", "vision enterprises",
]
# Words that mark a table as a per-item TECHNICAL SPECIFICATION sheet
# (as opposed to a flat quotation-style item table). Seen in Invitation-toTender packets, e.g. HIT's "Appx-II to Anx A" style parameter tables that
# break each item down into General / Performance / Critical rows.
_SPEC_TABLE_MARKERS = {"general", "performance", "critical", "parameters"}

# Annexure detection pattern - matches lines like "Annexure A", "Anx-B", "Annexure 1", etc.
_ANNEXURE_RE = re.compile(
    r"^\s*(?:annexure|annex|anx)\s*['\"\-]?\s*([A-Za-z0-9]+)",
    re.IGNORECASE,
)
# Words that mark a table as a "Schedule of Requirement" summary table —
# short list of items with Ser/Description/A-U/Qty/DP columns, typically
# with NO prices (a tender inquiry, not a priced quotation).
# NOTE: schedule-table detection is done cell-by-cell in
# _looks_like_schedule_header() below, not via substring matching on a text
# blob — "ser" as a loose substring also matches ordinary prose ("Supplier",
# "reserves", etc.), which caused false positives across a document's legal
# boilerplate in earlier testing.


def extract_items_from_file(
    file_stream,
    filename="",
    force_ai=False,
    use_groq_fallback=False,
    force_groq=False,
    use_gemini_fallback=False,
    force_gemini=False,
    include_photos=False,
    return_diagnostics=False,
    **kwargs
):
    """
    Extracts line items from Word (.docx), Excel (.xlsx/.xls), PDF, or Image.
    Returns a list of dicts: {description, unit, qty, unit_price}
    :param file_stream: BytesIO or file-like object of the uploaded file.
    :param filename: Original filename to determine file extension.
    :param force_ai: If True, bypasses local parsing and calls Groq AI directly.
    :param use_groq_fallback: If True, falls back to Groq AI if local parsing finds no items.
    :param force_groq: Alias for force_ai.
    :param include_photos: If True (PDF only), best-effort pairs each item with an
        embedded photo found on the same page as its item heading (see
        _attach_photos_to_items). Adds "photo_bytes"/"photo_ext" keys to matched
        items. Caller is responsible for saving photo_bytes somewhere servable
        (e.g. static/uploads/...) and swapping it for a URL/path before this
        dict goes anywhere that expects JSON (raw bytes aren't serializable).
    :param return_diagnostics: If True, returns {"items": [...], "warnings": [...],
        "low_confidence_pages": [...]} instead of a bare list. Warnings surface
        things that previously only went to stdout via print() - low-confidence
        OCR passes, scanned pages that had no text layer, flattened photo
        blocks that got pixel-split - so a caller can flag results for human
        review instead of trusting everything silently. Default False keeps
        the return type unchanged for existing callers.
    """
    diagnostics = {"warnings": [], "low_confidence_pages": []}

    # File size guard
    try:
        file_stream.seek(0)
        file_size = len(file_stream.read())
        file_stream.seek(0)
        if file_size > 100 * 1024 * 1024:
            diagnostics["warnings"].append(
                f"File is very large ({file_size / (1024*1024):.0f}MB); extraction may be slow or fail due to memory constraints."
            )
    except Exception:
        pass

    is_force_ai = force_ai or force_groq or force_gemini
    # 1. EXPLICIT AI EXTRACTION (Triggered when user clicks 'Extract with Groq AI'
    #    or 'Extract with Gemini AI'). Routed through _run_ai_extraction so the
    #    requested provider is actually the one that runs — force_gemini must
    #    call Gemini, not silently fall through to Groq.
    if is_force_ai:
        provider = "gemini" if force_gemini else ("groq" if (force_groq or force_ai) else None)
        print(f"[Extractor]: Running explicit AI extraction (provider={provider or 'auto'})...")
        ai_items = _run_ai_extraction(file_stream, filename, provider=provider)
        result = ai_items[:MAX_ITEMS] if ai_items else []
        return {"items": result, **diagnostics} if return_diagnostics else result
    # 2. LOCAL RULE-BASED EXTRACTION
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    image_extensions = {"png", "jpg", "jpeg", "webp", "bmp"}
    excel_extensions = {"xlsx", "xls"}
    word_extensions = {"docx", "doc"}
    items = []
    # Word Document Processing (.docx)
    if ext in word_extensions or filename == "":
        items = _extract_from_docx(file_stream)
    # Excel File Processing
    elif ext in excel_extensions:
        items = _extract_from_excel(file_stream, include_photos=include_photos, diagnostics=diagnostics)
    # Image OCR Processing
    elif ext in image_extensions:
        items = _extract_from_image(file_stream, diagnostics=diagnostics)
    # PDF Processing
    else:
        try:
            file_stream.seek(0)
            with pdfplumber.open(file_stream) as pdf:
                # Single pass: pull every table off every page once. We reuse
                # this same list both to classify the document (flat quotation
                # vs a dual-table tender packet) and to actually parse it,
                # instead of re-opening/re-walking the PDF a second time.
                all_tables = []
                for page in pdf.pages:
                    all_tables.extend(_collapse_blank_columns(t) for t in page.extract_tables() if t)
                doc_type = _classify_tables(all_tables)
                if doc_type == "tender_dual_table":
                    items = _extract_dual_table_tender(all_tables)
                else:
                    # Prefer a genuinely identified Schedule of Requirement
                    # table if one exists, even without a paired per-item
                    # spec table (many tenders only have the flat schedule,
                    # no separate spec sheet per item). Without this, a
                    # large multi-section ITB/SBD packet (Bid Data Sheet,
                    # Evaluation Criteria, Checklist, NDA, blank price
                    # templates, etc. - all real tables) gets its dozens of
                    # unrelated legal/administrative tables all parsed as if
                    # they were line-item tables, burying the real items in
                    # noise.
                    schedule_tables = [t for t in all_tables if _classify_table(t) == "schedule_table"]
                    if schedule_tables:
                        for t in schedule_tables:
                            try:
                                items.extend(_parse_single_table_block(t))
                            except Exception as e:
                                print(f"[PDF Warning]: Schedule table parsing failed: {e}")
                                continue
                            if len(items) >= MAX_ITEMS:
                                break
                    else:
                        combined_grid = []
                        last_col_count = None
                        for table in all_tables:
                            try:
                                cols = len(table[0]) if table else 0
                                if combined_grid and abs(cols - last_col_count) > 2:
                                    items.extend(_parse_table(combined_grid))
                                    combined_grid = []
                                    if len(items) >= MAX_ITEMS:
                                        break
                                combined_grid.extend(table)
                                last_col_count = cols
                            except Exception as e:
                                print(f"[PDF Warning]: Table processing failed: {e}")
                                continue
                        if combined_grid and len(items) < MAX_ITEMS:
                            try:
                                items.extend(_parse_table(combined_grid))
                            except Exception as e:
                                print(f"[PDF Warning]: Combined grid parsing failed: {e}")
                if not items:
                    full_text_parts = []
                    for page in pdf.pages:
                        full_text_parts.append(page.extract_text() or "")
                    combined_text = "\n".join(full_text_parts)
                    items.extend(_parse_plain_text(combined_text))
                    # Scanned page fallback: if there's still nothing AND
                    # the PDF has essentially no extractable text layer at
                    # all (a straight scan/photo of a paper document, not
                    # a text-based PDF), pdfplumber's extract_tables()/
                    # extract_text() were never going to find anything -
                    # there's no text object for them to find. Rasterize
                    # each page and reconstruct a table grid from Tesseract
                    # OCR instead, then run it through the SAME parsers
                    # used for real tables so nothing downstream needs to
                    # know the source was a scan.
                    if not items and len(combined_text.strip()) < 100 and FITZ_AVAILABLE:
                        diagnostics["warnings"].append(
                            "No extractable text layer found - treating this PDF as a scan "
                            "and reconstructing tables from OCR instead."
                        )
                        file_stream.seek(0)
                        fitz_doc = fitz.open(stream=file_stream.read(), filetype="pdf")
                        # gmft's PyPDFium2Document binding only accepts a
                        # real file path (no in-memory stream support), so
                        # when gmft is available we spill the same bytes to
                        # one temp file for this whole document, open it
                        # once, and reuse it for every page in the loop
                        # below - then clean up when we're done with it.
                        gmft_doc = None
                        gmft_tmp_path = None
                        if GMFT_AVAILABLE:
                            try:
                                file_stream.seek(0)
                                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                                    tmp.write(file_stream.read())
                                    gmft_tmp_path = tmp.name
                                gmft_doc = PyPDFium2Document(gmft_tmp_path)
                            except Exception as e:
                                diagnostics["warnings"].append(f"Could not open document for gmft: {e}")
                                gmft_doc = None
                        try:
                            for page_no in range(len(fitz_doc)):
                                gmft_page = gmft_doc.get_page(page_no) if gmft_doc is not None else None
                                grid = (
                                    _reconstruct_table_from_gmft(
                                        gmft_page, diagnostics=diagnostics, page_no=page_no
                                    ) if gmft_page is not None else None
                                ) or _reconstruct_table_from_ocr(
                                    fitz_doc[page_no], diagnostics=diagnostics, page_no=page_no
                                )
                                if grid:
                                    items.extend(_parse_table(grid))
                                if len(items) >= MAX_ITEMS:
                                    break
                        finally:
                            fitz_doc.close()
                            if gmft_doc is not None:
                                gmft_doc.close()
                            if gmft_tmp_path and os.path.exists(gmft_tmp_path):
                                try:
                                    os.remove(gmft_tmp_path)
                                except OSError:
                                    pass
        except Exception as e:
            err_str = str(e).lower()
            if any(kw in err_str for kw in ["password", "encrypted", "permissions", "decrypt"]):
                diagnostics["warnings"].append(
                    "PDF appears to be password-protected or encrypted. "
                    "Please provide an unlocked copy for extraction."
                )
            else:
                print(f"[PDF Extract Error]: {e}")
                diagnostics["warnings"].append(f"PDF extraction error: {e}")

        if include_photos and items:
            try:
                # Position-based matching runs FIRST: it's per-item precise
                # (matches each item's own Part No / description text) and
                # correctly handles multiple items sharing one page/table,
                # which the older heading-based pass below cannot - it
                # keys off a single "N. ITEM NAME" heading per page, so on
                # a page with several items it would either miss later
                # ones or (worse) hand every item the same photo. Running
                # heading-based matching first would let its wrong/
                # duplicate guesses block this more accurate pass, since
                # both passes skip items that already have a photo.
                file_stream.seek(0)
                _attach_photos_by_position(items, file_stream, diagnostics=diagnostics)
                if any(not it.get("photo_bytes") for it in items):
                    file_stream.seek(0)
                    photos = _extract_images_from_pdf(file_stream, _MIN_IMG_DIM, None, True)
                    _attach_photos_to_items(items, photos)
                still_missing = sum(1 for it in items if not it.get("photo_bytes"))
                if still_missing:
                    diagnostics["warnings"].append(
                        f"{still_missing} of {len(items)} item(s) could not be paired with a photo."
                    )
            except Exception as e:
                print(f"[Photo Pairing Error]: {e}")
                diagnostics["warnings"].append(f"Photo pairing error: {e}")
        # 3. OPTIONAL AI FALLBACK IF LOCAL PARSING FOUND NOTHING
        if not items and (use_groq_fallback or use_gemini_fallback):
            print("[Extractor]: Local extraction yielded no items. Attempting AI fallback (Gemini -> Groq)...")
            ai_items = _run_ai_extraction(file_stream, filename, provider=None)
            if ai_items:
                result = ai_items[:MAX_ITEMS]
                return {"items": result, **diagnostics} if return_diagnostics else result
    # Apply amendment precedence (amendments supersede base document)
    items = _apply_amendment_precedence(items)
    result = items[:MAX_ITEMS]
    return {"items": result, **diagnostics} if return_diagnostics else result


def extract_items_from_pdf(file_stream, filename=""):
    """Backward-compatibility wrapper."""
    return extract_items_from_file(file_stream, filename)


def extract_items_from_files(file_streams, filenames, **kwargs):
    """Extract items from multiple files, cross-referencing across them.
    Useful for multi-file tender packets (main PDF + annexures).

    :param file_streams: list of BytesIO/file-like objects.
    :param filenames: list of original filenames (for extension detection).
    :param kwargs: passed through to extract_items_from_file.
    :return: combined and deduplicated list of items.
    """
    all_items = []
    seen_keys = set()
    for stream, name in zip(file_streams, filenames):
        try:
            items = extract_items_from_file(stream, name, **kwargs)
            if isinstance(items, dict):
                items = items.get("items", [])
            for item in items:
                key = (
                    (item.get("description") or "").strip().lower()[:80],
                    (item.get("part_no") or "").strip().lower(),
                )
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_items.append(item)
        except Exception as e:
            print(f"[Batch Extract Warning]: File '{name}' failed: {e}")
            continue
    return all_items[:MAX_ITEMS]
# =========================================================================
# GROQ AI EXTRACTION HELPER
# =========================================================================


# =========================================================================
# AI EXTRACTION — TOKEN BUDGETING (protects the Groq path from repeating
# the same oversized request; Gemini's free tier has enough TPM headroom
# that a normal tender document rarely needs this, but it's here as a
# safety net either way).
# =========================================================================
_GROQ_TPM_BUDGET = int(os.environ.get("GROQ_TPM_BUDGET", "6000"))
_GROQ_PROMPT_OVERHEAD_TOKENS = 300
_GROQ_RESPONSE_RESERVE_TOKENS = 2000


def _estimate_tokens(text):
    return max(1, len(text) // 4)


def _max_text_tokens_per_call():
    return max(500, _GROQ_TPM_BUDGET - _GROQ_PROMPT_OVERHEAD_TOKENS - _GROQ_RESPONSE_RESERVE_TOKENS)


_SECTION_HEADER_RE = re.compile(
    r'(?:Annexure|Anx|Schedule|Section|Chapter|Part|Clause)\s+[\w\d\-]+',
    re.IGNORECASE
)

def _chunk_text_by_tokens(text, max_tokens):
    """Split text into chunks that fit within max_tokens, preferring to split
    at section boundaries (Annexure, Schedule, Section, etc.) to preserve
    document structure for the AI model."""
    max_chars = max_tokens * 4
    # Find section boundaries
    section_matches = list(_SECTION_HEADER_RE.finditer(text))
    if section_matches and len(text) > max_chars:
        chunks = []
        for i, match in enumerate(section_matches):
            start = match.start()
            end = section_matches[i + 1].start() if i + 1 < len(section_matches) else len(text)
            section_text = text[start:end]
            if len(section_text) <= max_chars:
                chunks.append(section_text)
            else:
                # Section too large — fall back to line-based splitting
                lines = section_text.split("\n")
                current, current_len = [], 0
                for line in lines:
                    line_len = len(line) + 1
                    if current_len + line_len > max_chars and current:
                        chunks.append("\n".join(current))
                        current, current_len = [], 0
                    current.append(line)
                    current_len += line_len
                if current:
                    chunks.append("\n".join(current))
        return chunks
    # No sections found or text fits — simple line-based splitting
    lines = text.split("\n")
    chunks, current, current_len = [], [], 0
    for line in lines:
        line_len = len(line) + 1
        if current_len + line_len > max_chars and current:
            chunks.append("\n".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return chunks


_AI_SYSTEM_PROMPT = (
    "You are an expert procurement assistant. Extract all line items, goods, or services from "
    "all tables present in the provided document.\n"
    "IMPORTANT: If the document is organized into annexures (sections labeled 'Annexure A', 'Annexure B', "
    "'Anx-1', etc.), include the annexure name in each item's 'annexure' field.\n"
    "CRITICAL: Return ONLY a valid raw JSON object matching this exact structure, with NO markdown formatting, NO backticks, and NO extra text:\n"
    "{\n"
    '  "items": [\n'
    '    {"description": "Item description", "part_no": "", "unit": "Nos", "qty": 1.0, "unit_price": 0.0, "annexure": ""}\n'
    "  ]\n"
    "}\n"
    "If a row has a separate Part No / Stock No / P/N column, put ONLY that value in "
    "'part_no' - do NOT prepend or mix it into 'description'. Leave 'part_no' as an empty "
    "string if the document has no such column. Default unit to 'Nos' if unspecified, "
    "qty to 1.0, unit_price to 0.0, and annexure to '' if no annexure grouping is detected.\n\n"
    "EXAMPLE INPUT:\n"
    "Annexure A - Electrical Items\n"
    "S.No | Part No | Description | A/U | Qty | Rate\n"
    "1 | CW-250 | Copper Wire 2.5 sq mm | Mtr | 100 | 45.50\n"
    "2 | PVT-100 | PVC Insulation Tape | Roll | 50 | 12.00\n\n"
    "EXAMPLE OUTPUT:\n"
    '{"items": ['
    '{"description": "Copper Wire 2.5 sq mm", "part_no": "CW-250", "unit": "Mtr", "qty": 100.0, "unit_price": 45.50, "annexure": "Annexure A"},'
    '{"description": "PVC Insulation Tape", "part_no": "PVT-100", "unit": "Roll", "qty": 50.0, "unit_price": 12.00, "annexure": "Annexure A"}'
    ']}\n\n'
    "Output the JSON object and NOTHING else - no preamble, no explanation, no closing remarks."
)


def _format_and_dedupe_items(raw_items):
    formatted, seen = [], set()
    for item in raw_items:
        desc = str(item.get("description", ""))[:250]
        if not desc:
            continue
        key = (desc.strip().lower(), str(item.get("part_no", "")).strip().lower())
        if key in seen:
            continue
        seen.add(key)
        formatted.append({
            "description": desc,
            "part_no": str(item.get("part_no", "") or "").strip(),
            "unit": str(item.get("unit", "Nos")).strip() or "Nos",
            "qty": float(item.get("qty", 1.0) or 1.0),
            "unit_price": float(item.get("unit_price", 0.0) or 0.0),
            "annexure": str(item.get("annexure", "") or "").strip(),
        })
    return formatted


def _verify_arithmetic(items):
    """Check qty * unit_price against amount/total where available.
    Flags mismatches by reducing confidence and adding a warning."""
    for item in items:
        qty = item.get("qty")
        price = item.get("unit_price")
        total = item.get("total") or item.get("amount")
        if qty and price and total and qty > 0 and price > 0 and total > 0:
            expected = qty * price
            if abs(expected - total) > max(0.01 * total, 1.0):
                item["confidence"] = max(item.get("confidence", 0.5) - 0.2, 0.1)
                item["warning"] = f"Arithmetic mismatch: {qty}x{price}={expected:.2f} != {total:.2f}"
    return items


# =========================================================================
# GEMINI AI EXTRACTION (primary AI fallback — huge free-tier TPM headroom,
# accepts a raw PDF natively so no rasterizing/chunking is normally needed)
# =========================================================================

def _extract_with_gemini(file_stream, filename=""):
    """Sends the native PDF/image bytes (or extracted text for Word/Excel)
    to Gemini. Preferred AI provider — see GROQ vs GEMINI note in
    _run_ai_extraction() below."""
    _set_extraction_error(None)
    if not GEMINI_AVAILABLE:
        msg = "`google-genai` not installed. Run `pip install google-genai`."
        _set_extraction_error(msg)
        print(f"[Gemini Error]: {msg}")
        return []
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        msg = "`GEMINI_API_KEY` environment variable is missing."
        _set_extraction_error(msg)
        print(f"[Gemini Error]: {msg}")
        return []

    import socket
    _MAX_RETRIES = 2
    _RETRY_DELAY = 2.0
    last_exc = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            client = _get_gemini_client()
            if client is None:
                msg = "Failed to create Gemini client — check GEMINI_API_KEY."
                _set_extraction_error(msg)
                print(f"[Gemini Error]: {msg}")
                return []
            # gemini-2.5-flash is deprecated for new users as of 2026 (returns
            # a 404). gemini-3.6-flash is the current GA workhorse model.
            model_name = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

            ext = filename.lower().split(".")[-1] if "." in filename else ""
            file_stream.seek(0)

            if ext in {"pdf", "png", "jpg", "jpeg", "webp", "bmp"}:
                file_bytes = file_stream.read()
                mime = {
                    "pdf": "application/pdf", "png": "image/png",
                    "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "webp": "image/webp", "bmp": "image/bmp",
                }.get(ext, "application/pdf")

                # For large PDFs (>20 pages), chunk into 15-page segments
                # to avoid hitting API context limits
                all_items = []
                if ext == "pdf" and FITZ_AVAILABLE:
                    import io
                    fitz_doc = fitz.open(stream=file_bytes, filetype="pdf")
                    total_pages = len(fitz_doc)
                    fitz_doc.close()
                    if total_pages > 20:
                        chunk_size = 15
                        for start in range(0, total_pages, chunk_size):
                            end = min(start + chunk_size, total_pages)
                            import PyPDF2
                            reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
                            writer = PyPDF2.PdfWriter()
                            for pg in range(start, end):
                                writer.add_page(reader.pages[pg])
                            chunk_buf = io.BytesIO()
                            writer.write(chunk_buf)
                            chunk_bytes = chunk_buf.getvalue()
                            contents = [
                                genai_types.Part.from_bytes(data=chunk_bytes, mime_type=mime),
                                _AI_SYSTEM_PROMPT,
                            ]
                            try:
                                response = client.models.generate_content(
                                    model=model_name,
                                    contents=contents,
                                    config=genai_types.GenerateContentConfig(
                                        temperature=0.1,
                                        response_mime_type="application/json",
                                    ),
                                )
                                raw_json = response.text.strip()
                                if raw_json.startswith("```"):
                                    parts_split = raw_json.split("```")
                                    raw_json = parts_split[1].strip() if len(parts_split) >= 2 else raw_json
                                    if raw_json.startswith("json"):
                                        raw_json = raw_json[4:].strip()
                                try:
                                    data = json.loads(raw_json)
                                except json.JSONDecodeError:
                                    match = re.search(r"\{.*\}", raw_json, re.DOTALL)
                                    if not match:
                                        continue
                                    attempt = match.group(0)
                                    data = None
                                    for fix in [
                                        re.sub(r',\s*\{[^}]*$', '', attempt),
                                        re.sub(r',\s*"[^"]*$', '', attempt),
                                        attempt + '}',
                                        attempt + '"}',
                                    ]:
                                        try:
                                            data = json.loads(fix)
                                            break
                                        except json.JSONDecodeError:
                                            continue
                                    if data is None:
                                        continue
                                all_items.extend(data.get("items", []))
                            except Exception as e:
                                print(f"[Gemini]: chunk {start+1}-{end} failed: {e}")
                                continue
                            if end < total_pages:
                                time.sleep(1)
                        return _format_and_dedupe_items(all_items)

                contents = [
                    genai_types.Part.from_bytes(data=file_bytes, mime_type=mime),
                    _AI_SYSTEM_PROMPT,
                ]
            else:
                doc_text = _extract_text_content_for_llm(file_stream, ext)
                contents = [f"{_AI_SYSTEM_PROMPT}\n\n--- DOCUMENT CONTENT ---\n{doc_text}"]

            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            raw_json = response.text.strip()
            if raw_json.startswith("```"):
                parts_split = raw_json.split("```")
                raw_json = parts_split[1].strip() if len(parts_split) >= 2 else raw_json
                if raw_json.startswith("json"):
                    raw_json = raw_json[4:].strip()

            try:
                data = json.loads(raw_json)
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", raw_json, re.DOTALL)
                if not match:
                    raise
                attempt = match.group(0)
                data = None
                for fix in [
                    re.sub(r',\s*\{[^}]*$', '', attempt),
                    re.sub(r',\s*"[^"]*$', '', attempt),
                    attempt + '}',
                    attempt + '"}',
                ]:
                    try:
                        data = json.loads(fix)
                        break
                    except json.JSONDecodeError:
                        continue
                if data is None:
                    raise

            return _format_and_dedupe_items(data.get("items", []))

        except (socket.gaierror, socket.timeout, ConnectionError, OSError) as e:
            last_exc = e
            if attempt < _MAX_RETRIES:
                print(f"[Gemini]: Network error (attempt {attempt+1}/{_MAX_RETRIES+1}): {e}. Retrying in {_RETRY_DELAY}s...")
                time.sleep(_RETRY_DELAY)
                continue
        except Exception as e:
            _set_extraction_error(str(e))
            print(f"[Gemini Extraction Error]: {e}")
            return []

    msg = f"Gemini API unreachable (network error after {_MAX_RETRIES+1} attempts): {last_exc}"
    _set_extraction_error(msg)
    print(f"[Gemini Extraction Error]: {msg}")
    return []


# =========================================================================
# GROQ AI EXTRACTION (backup provider — chunked so a large document can't
# repeat the same oversized request against the free-tier TPM ceiling)
# =========================================================================

def _call_groq_json(client, model_name, content_payload):
    _MAX_API_RETRIES = 2
    _API_TIMEOUT = 60  # seconds
    for attempt in range(_MAX_API_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": content_payload}],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=8192,
                timeout=_API_TIMEOUT,
            )
            break
        except Exception as e:
            err_str = str(e)
            if any(code in err_str for code in ["429", "500", "503", "rate_limit_exceeded", "tokens_per_minute"]):
                if attempt < _MAX_API_RETRIES:
                    wait = 2 ** (attempt + 1)
                    print(f"[Groq]: Rate/server error (attempt {attempt+1}/{_MAX_API_RETRIES+1}): {e}. Retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                raise
            print(f"[Groq Extraction Warning]: JSON mode request failed ({e}); retrying without response_format...")
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": content_payload}],
                temperature=0.1,
                max_tokens=8192,
                timeout=_API_TIMEOUT,
            )
            break

    raw_json = response.choices[0].message.content.strip()
    if raw_json.startswith("```"):
        parts = raw_json.split("```")
        if len(parts) >= 2:
            raw_json = parts[1]
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]
            raw_json = raw_json.strip()
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_json, re.DOTALL)
        if not match:
            raise
        attempt = match.group(0)
        # Try progressive truncation to recover from max_tokens cutoff
        for fix in [
            re.sub(r',\s*\{[^}]*$', '', attempt),
            re.sub(r',\s*"[^"]*$', '', attempt),
            attempt + '}',
            attempt + '"}',
            attempt + '"}}',
        ]:
            try:
                data = json.loads(fix)
                break
            except json.JSONDecodeError:
                continue
        else:
            raise
    return data.get("items", [])


def _extract_with_groq(file_stream, filename=""):
    """Text-first, chunked-if-needed. Only rasterizes to page images
    (the old, token-expensive path) when there is truly no text layer."""
    _set_extraction_error(None)
    if not GROQ_AVAILABLE:
        msg = "`groq` SDK is not installed. Run `pip install groq`."
        _set_extraction_error(msg)
        print(f"[Groq Error]: {msg}")
        return []
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        msg = "`GROQ_API_KEY` environment variable is missing."
        _set_extraction_error(msg)
        print(f"[Groq Error]: {msg}")
        return []

    client = _get_groq_client()
    if not client:
        msg = "Failed to initialize Groq client."
        _set_extraction_error(msg)
        return []
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    model_name = os.environ.get("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
    max_tokens_per_call = _max_text_tokens_per_call()

    try:
        doc_text = ""
        if ext == "pdf":
            file_stream.seek(0)
            with pdfplumber.open(file_stream) as pdf:
                doc_text = _normalize_text("\n".join((p.extract_text() or "") for p in pdf.pages))
            import gc; gc.collect()
        elif ext in {"docx", "doc", "xlsx", "xls"}:
            doc_text = _extract_text_content_for_llm(file_stream, ext)

        if doc_text.strip():
            estimated = _estimate_tokens(doc_text)
            chunks = [doc_text] if estimated <= max_tokens_per_call else _chunk_text_by_tokens(doc_text, max_tokens_per_call)
            if len(chunks) > 1:
                print(f"[Groq Extraction]: ~{estimated} tokens > {max_tokens_per_call}/call budget — splitting into {len(chunks)} chunk(s).")

            all_raw_items = []
            for i, chunk in enumerate(chunks):
                content_payload = f"{_AI_SYSTEM_PROMPT}\n\n--- DOCUMENT CONTENT (part {i+1}/{len(chunks)}) ---\n{chunk}"
                try:
                    all_raw_items.extend(_call_groq_json(client, model_name, content_payload))
                except Exception as e:
                    print(f"[Groq Extraction Error]: chunk {i+1}/{len(chunks)} failed: {e}")
                    continue
                if i < len(chunks) - 1:
                    time.sleep(2)
            return _format_and_dedupe_items(all_raw_items)

        # No text layer at all — genuine scan, fall back to a SMALL vision request
        if ext in {"pdf", "png", "jpg", "jpeg", "webp", "bmp"}:
            images_b64 = _file_stream_to_base64_images(file_stream, ext, max_pages=3, dpi=250)
            all_raw_items = []
            for i, img_url in enumerate(images_b64):
                content_payload = [
                    {"type": "text", "text": _AI_SYSTEM_PROMPT},
                    {"type": "image_url", "image_url": {"url": img_url}},
                ]
                try:
                    all_raw_items.extend(_call_groq_json(client, model_name, content_payload))
                except Exception as e:
                    print(f"[Groq Extraction Error]: vision page {i+1} failed: {e}")
                    continue
                if i < len(images_b64) - 1:
                    time.sleep(2)
            del images_b64
            import gc; gc.collect()
            return _format_and_dedupe_items(all_raw_items)

        return []
    except Exception as e:
        _set_extraction_error(str(e))
        print(f"[Groq Extraction Error]: {e}")
        return []


def _run_ai_extraction(file_stream, filename="", provider=None):
    """
    Central AI dispatcher. provider="gemini" or "groq" forces that engine
    explicitly (used by the two dedicated buttons). provider=None runs the
    automatic waterfall: Gemini first (far more TPM headroom, so it's the
    better default when the caller doesn't care which engine runs), then
    Groq if Gemini is unavailable/misconfigured/empty.
    """
    if provider == "gemini":
        return _extract_with_gemini(file_stream, filename)
    if provider == "groq":
        return _extract_with_groq(file_stream, filename)

    items = _extract_with_gemini(file_stream, filename)
    if items:
        return items
    print("[Extractor]: Gemini returned nothing — trying Groq...")
    return _extract_with_groq(file_stream, filename)


def _file_stream_to_base64_images(file_stream, ext):
    """Converts uploaded PDFs or image files into a list of base64 data URLs."""
    file_bytes = file_stream.read()
    file_stream.seek(0)
    images_b64 = []
    if ext == "pdf":
        import fitz  # PyMuPDF — lazy import to avoid venv conflicts
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page_num in range(min(len(doc), 3)):  # Process up to first 3 pages
            page = doc[page_num]
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            b64_str = base64.b64encode(img_bytes).decode("utf-8")
            images_b64.append(f"data:image/png;base64,{b64_str}")
        doc.close()
    else:
        b64_str = base64.b64encode(file_bytes).decode("utf-8")
        mime = "image/jpeg" if ext in ["jpg", "jpeg"] else f"image/{ext}"
        images_b64.append(f"data:{mime};base64,{b64_str}")
    return images_b64


def _extract_text_content_for_llm(file_stream, ext):
    """Converts Word (.docx) or Excel (.xlsx/.xls) files to plain text."""
    file_stream.seek(0)
    text_content = []
    if ext in {"docx", "doc"}:
        try:
            doc = docx.Document(file_stream)
            for p in doc.paragraphs:
                if p.text.strip():
                    text_content.append(p.text.strip())
            for t in doc.tables:
                for r in t.rows:
                    row_txt = " | ".join([cell.text.strip() for cell in r.cells])
                    text_content.append(row_txt)
        except Exception as e:
            print(f"[Text Read Error docx]: {e}")
    elif ext in {"xlsx", "xls"}:
        try:
            file_stream.seek(0)
            file_bytes = file_stream.read()
            # Check if it's an older .xls format (OLE2)
            if ext == 'xls' and file_bytes[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
                if not XLRD_AVAILABLE:
                    raise ImportError("xlrd is required to extract .xls files. Please install it: pip install xlrd")
                file_stream = io.BytesIO(file_bytes)
                workbook = xlrd.open_workbook(fileobj=file_stream)
                for sheet_name in workbook.sheet_names():
                    sheet = workbook.sheet_by_name(sheet_name)
                    text_content.append(f"=== {sheet_name} ===")
                    for row_idx in range(sheet.nrows):
                        row_vals = []
                        for col_idx in range(sheet.ncols):
                            cell = sheet.cell_value(row_idx, col_idx)
                            if cell is not None:
                                row_vals.append(str(cell).strip())
                        if row_vals:
                            text_content.append(" | ".join(row_vals))
            else:
                file_stream = io.BytesIO(file_bytes)
                wb = openpyxl.load_workbook(file_stream, data_only=True)
                for sheet_name in wb.sheetnames:
                    sheet = wb[sheet_name]
                    text_content.append(f"=== {sheet_name} ===")
                    for row in sheet.iter_rows(values_only=True):
                        row_vals = [_safe_cell_str(c) for c in row]
                        if row_vals:
                            text_content.append(" | ".join(row_vals))
        except Exception as e:
            print(f"[Text Read Error excel]: {e}")
    return _normalize_text("\n".join(text_content))
# =========================================================================
# LOCAL RULE-BASED EXTRACTION HELPERS
# =========================================================================


def _extract_from_docx(file_stream):
    items = []
    try:
        file_stream.seek(0)
        doc = docx.Document(file_stream)
        raw_tables = []
        for table in doc.tables:
            try:
                table_grid = []
                for row in table.rows:
                    row_vals = [" ".join(cell.text.split()).strip() for cell in row.cells]
                    if any(row_vals):
                        table_grid.append(row_vals)
                if table_grid:
                    raw_tables.append(_collapse_blank_columns(table_grid))
            except Exception as e:
                print(f"[DOCX Warning]: Table read failed: {e}")
                continue
        raw_tables = _merge_headerless_continuations(raw_tables)
        if _classify_tables(raw_tables) == "tender_dual_table":
            items = _extract_dual_table_tender(raw_tables)
        else:
            schedule_tables = [t for t in raw_tables if _classify_table(t) == "schedule_table"]
            tables_to_parse = schedule_tables if schedule_tables else raw_tables
            for table_grid in tables_to_parse:
                try:
                    extracted = _parse_single_table_block(table_grid) if schedule_tables else _parse_table(table_grid)
                    if extracted:
                        items.extend(extracted)
                except Exception as e:
                    print(f"[DOCX Warning]: Table parsing failed: {e}")
                    continue
                if len(items) >= MAX_ITEMS:
                    break
        if not items:
            full_text = _normalize_text("\n".join([p.text.strip() for p in doc.paragraphs if p.text.strip()]))
            items.extend(_parse_plain_text(full_text))
    except Exception as e:
        print(f"[Word Extract Error]: {e}")
    return items


def _fill_merged_cells(sheet):
    """Return a 2D list where merged cell regions are filled with the
    top-left cell's value (openpyxl returns None for non-anchor cells)."""
    rows = []
    for row in sheet.iter_rows(values_only=True):
        rows.append(list(row))
    for rng in sheet.merged_cells.ranges:
        val = sheet.cell(rng.min_row, rng.min_col).value
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                if r - 1 < len(rows) and c - 1 < len(rows[r - 1]):
                    if rows[r - 1][c - 1] is None:
                        rows[r - 1][c - 1] = val
    return rows


def _safe_cell_str(cell):
    """Convert cell to string, filtering out Excel error values (#REF!, #N/A, etc.)."""
    if cell is None:
        return ""
    try:
        from openpyxl.cell.error import Error
        if isinstance(cell, Error):
            return ""
    except ImportError:
        pass
    return str(cell).strip()


def _extract_from_excel(file_stream, include_photos=False, diagnostics=None):
    """
    Extracts line items from an Excel workbook (.xlsx/.xls).

    Processes ALL sheets (not just the active one) so multi-sheet tenders
    with separate annexures are handled correctly. Detects annexure sheets
    by their tab name and propagates the annexure label to each item.

    Excel embedded images are also extracted and paired with items by
    their row position when include_photos=True (used for technical offers).
    """
    _set_extraction_error(None)

    try:
        file_stream.seek(0)
        file_bytes = file_stream.read()

        # Detect file format from header bytes (more reliable than extension)
        # OLE2 header: \xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1
        is_old_xls = file_bytes[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'

        if is_old_xls:
            if not XLRD_AVAILABLE:
                raise ImportError("xlrd is required to extract .xls files. Please install it: pip install xlrd")
            file_stream = io.BytesIO(file_bytes)
            workbook = xlrd.open_workbook(file_contents=file_bytes)
        else:
            # .xlsx or new-style .xls (ZIP-based) - use openpyxl
            file_stream = io.BytesIO(file_bytes)
            workbook = openpyxl.load_workbook(file_stream, data_only=True)

        all_items = []
        photos_by_sheet = {}  # sheet_name -> list of photo dicts

        # --- Extract embedded images (per-sheet dict) ---
        if include_photos:
            try:
                file_stream.seek(0)
                photos_by_sheet = _extract_images_from_excel(file_stream, _MIN_IMG_DIM)
                if photos_by_sheet:
                    total_photos = sum(len(v) for v in photos_by_sheet.values())
                    if diagnostics is not None:
                        diagnostics["warnings"].append(
                            f"Found {total_photos} embedded image(s) across {len(photos_by_sheet)} sheet(s) in Excel file."
                        )
            except Exception as photo_e:
                if diagnostics is not None:
                    diagnostics["warnings"].append(f"Excel photo extraction skipped: {photo_e}")

        # --- Process every sheet ---
        if XLRD_AVAILABLE and hasattr(workbook, 'sheet_names'):
            # xlrd interface
            sheet_names = workbook.sheet_names()
        elif hasattr(workbook, 'sheetnames'):
            # openpyxl interface
            sheet_names = workbook.sheetnames
        else:
            # Fallback for other workbook types
            sheet_names = []

        for sheet_name in sheet_names:
            try:
                # Detect annexure sheet by name: "Annexure A", "Anx-B", "A", "1", "Sheet2" etc.
                sheet_name_clean = sheet_name.strip()
                sheet_name_lower = sheet_name_clean.lower()

                is_annexure_sheet = False
                annexure_label = ""

                # Heuristic: single-letter, "annexure/anx/anx-" prefix, or numeric suffix
                if re.match(r"^(annexure|anx|anx-)\s*['\"]?([A-Za-z0-9])$", sheet_name_lower):
                    m = re.match(r"^(annexure|anx|anx-)\s*['\"]?([A-Za-z0-9])$", sheet_name_lower)
                    annexure_label = m.group(2).upper() if m else sheet_name_clean
                    is_annexure_sheet = True
                elif re.match(r"^[A-Za-z]$", sheet_name_clean) and sheet_name_clean.upper() not in ("A", "I", "V"):
                    annexure_label = sheet_name_clean.upper()
                    is_annexure_sheet = True
                elif re.match(r"^[A-Za-z]\s*\d+$", sheet_name_clean):
                    annexure_label = re.match(r"^([A-Za-z])", sheet_name_clean).group(1).upper()
                    is_annexure_sheet = True
                elif "annexure" in sheet_name_lower or "anx" in sheet_name_lower:
                    annexure_label = sheet_name_clean
                    is_annexure_sheet = True

                if XLRD_AVAILABLE and hasattr(workbook, 'sheet_names'):
                    sheet = workbook.sheet_by_name(sheet_name)
                    # Convert xlrd sheet to list of rows (xlrd provides cell values directly)
                    table = []
                    excel_row_map = []
                    for excel_row_num in range(1, sheet.nrows + 1):
                        row_vals = []
                        for col in range(sheet.ncols):
                            cell = sheet.cell_value(excel_row_num - 1, col)
                            if cell is not None:
                                row_vals.append(str(cell).strip())
                            else:
                                row_vals.append("")
                        if any(v for v in row_vals if v):
                            table.append(row_vals)
                            excel_row_map.append(excel_row_num)
                else:
                    # openpyxl interface — fill merged cells first
                    sheet = workbook[sheet_name]
                    raw_rows = _fill_merged_cells(sheet)
                    table = []
                    excel_row_map = []
                    for excel_row_num, row_vals_raw in enumerate(raw_rows, start=1):
                        row_vals = [_safe_cell_str(cell) for cell in row_vals_raw]
                        if any(v for v in row_vals if v):
                            table.append(row_vals)
                            excel_row_map.append(excel_row_num)

                if not table:
                    continue  # skip empty sheets

                sheet_items = _parse_table(table)

                # Tag each item with the annexure label
                for item in sheet_items:
                    if is_annexure_sheet and annexure_label:
                        existing_annexure = item.get("annexure", "").strip()
                        if existing_annexure:
                            item["annexure"] = f"{annexure_label} - {existing_annexure}"
                        else:
                            item["annexure"] = annexure_label

                # Pair photos with items by row index (sheet-keyed dict)
                # Images are anchored to Excel rows (1-based). Data items start
                # after the header row, so find the header offset to compute
                # the correct mapping from Excel row to sheet_items index.
                sheet_photos = photos_by_sheet.get(sheet_name, [])
                if sheet_photos and sheet_items:
                    h_idx, _ = _find_header_row(table)
                    data_start_row = (h_idx + 1) if h_idx is not None else 0
                    for photo in sheet_photos:
                        excel_row = photo.get("row_index", 1)  # 1-based Excel row
                        # Map Excel row to table index (table skips empty rows)
                        try:
                            table_idx = excel_row_map.index(excel_row)
                        except ValueError:
                            continue  # This Excel row was empty, no item here
                        item_idx = table_idx - data_start_row  # 0-based into sheet_items
                        if 0 <= item_idx < len(sheet_items):
                            target_item = sheet_items[item_idx]
                            if not target_item.get("photo_bytes"):
                                target_item["photo_bytes"] = photo.get("bytes")
                                target_item["photo_ext"] = photo.get("ext", "jpg")

                all_items.extend(sheet_items)
                if len(all_items) >= MAX_ITEMS:
                    break

            except Exception as e:
                print(f"[Excel Warning]: Sheet '{sheet_name}' failed: {e}")
                if diagnostics is not None:
                    diagnostics["warnings"].append(f"Sheet '{sheet_name}' skipped: {e}")
                continue

        # Check for uncached formula cells (all None values)
        if diagnostics is not None and not all_items:
            try:
                for sn in (workbook.sheetnames if hasattr(workbook, 'sheetnames') else []):
                    ws = workbook[sn]
                    non_none = sum(1 for row in ws.iter_rows(max_row=5) for c in row if c.value is not None)
                    if non_none == 0:
                        diagnostics["warnings"].append(
                            f"Sheet '{sn}': all formula cells appear uncached (None). "
                            f"Results may be incomplete. Re-save the file in Excel to cache values."
                        )
                        break
            except Exception:
                pass

        return all_items

    except Exception as e:
        _set_extraction_error(str(e))
        print(f"[Excel Extract Error]: {e}")
        return []


def _extract_from_image(file_stream, diagnostics=None):
    try:
        file_stream.seek(0)
        img = Image.open(file_stream)
        img = _deskew_image(img)
        img = _preprocess_for_ocr(img)
        img = img.convert("L")
        # Auto-select PSM: use PSM 6 (single uniform block) for better
        # table/structured text recognition on full-page images
        psm_config = "--psm 6"
        try:
            from pytesseract import Output
            data = pytesseract.image_to_data(img, output_type=Output.DICT, config=psm_config)
            confs = [int(float(c)) for c in data["conf"] if str(c).strip() not in ("", "-1")]
            if confs and diagnostics is not None:
                avg_conf = sum(confs) / len(confs)
                if avg_conf < 50:
                    diagnostics["warnings"].append(
                        f"Image OCR average confidence low ({avg_conf:.0f}%) - "
                        f"extracted text/quantities may be inaccurate, likely due to "
                        f"image resolution, skew, or handwriting."
                    )
            raw_lines = {}
            for i, t in enumerate(data["text"]):
                if not t.strip():
                    continue
                line_key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                raw_lines.setdefault(line_key, []).append(t)
            raw_text = "\n".join(" ".join(words) for words in raw_lines.values())
        except Exception:
            raw_text = pytesseract.image_to_string(img, config=psm_config)
        return _parse_plain_text(raw_text)
    except pytesseract.TesseractNotFoundError:
        print("[OCR Error] Tesseract is not installed or not added to system PATH.")
        if diagnostics is not None:
            diagnostics["warnings"].append("Tesseract OCR is not installed - image could not be processed.")
        return []
    except Exception as e:
        print(f"[OCR Error] Failed to process image: {e}")
        if diagnostics is not None:
            diagnostics["warnings"].append(f"Image OCR failed: {e}")
        return []
# =========================================================================
# AMENDMENT / ADDENDUM PRECEDENCE
#
# Tender documents often have amendments or addenda that supersede the base
# document. When items appear in both the base and an amendment, the
# amendment version should take precedence.
# =========================================================================

_AMENDMENT_RE = re.compile(
    r'(?:Amendment|Addendum|Revision|Corrigendum)\s+(\d+)', re.IGNORECASE
)

def _apply_amendment_precedence(items):
    """When items appear in both a base document and an amendment/addendum,
    the amendment version takes precedence. Items from amendments are tagged
    with their amendment number; if a base item has the same description
    but a later amendment overrides it, the amendment version wins."""
    if not items:
        return items
    # Group items by description key
    by_key = {}
    for item in items:
        desc = (item.get("description") or "").strip().lower()[:80]
        part = (item.get("part_no") or "").strip().lower()
        key = (desc, part)
        by_key.setdefault(key, []).append(item)
    # For each group, prefer the amendment version
    result = []
    for key, group in by_key.items():
        if len(group) == 1:
            result.append(group[0])
            continue
        # Check if any item mentions an amendment
        amendment_items = []
        base_items = []
        for item in group:
            annexure = (item.get("annexure") or "").lower()
            source = (item.get("source_text") or "").lower()
            if _AMENDMENT_RE.search(annexure) or _AMENDMENT_RE.search(source):
                amendment_items.append(item)
            else:
                base_items.append(item)
        if amendment_items:
            # Prefer the last amendment (highest number)
            amendment_items.sort(
                key=lambda x: int(
                    (_AMENDMENT_RE.search((x.get("annexure") or "") + " " + (x.get("source_text") or "")).group(1) or "0")
                ),
                reverse=True
            )
            result.append(amendment_items[0])
        else:
            result.append(base_items[0])
    return result


# =========================================================================
# PHOTO / IMAGE EXTRACTION
#
# Tender packets (esp. HIT-style ITB/SBD documents) embed a product photo
# next to each item's spec table (see Appx-II to Anx A). This pulls those
# embedded images out as real image files, filters out tiny logos/icons/
# watermarks by pixel size, and — since each item's photo sits on the same
# PDF page as its item heading in this document family — pairs each photo
# with the item heading found on that page, so callers can line photos up
# with the line items returned by extract_items_from_file().
# =========================================================================

_MIN_IMG_DIM = 80  # px; filters out small logos/bullets/icons/watermarks
_ITEM_HEADING_RE = re.compile(
    r"^\s*(\d{1,2})\.\s+([A-Z][A-Z0-9 /\-\(\)&,.]{3,80})", re.MULTILINE
)


def _attach_photos_to_items(items, photos):
    """Pairs extracted line items with extracted photos by heading NUMBER,
    not position. Some items in a tender packet have no photo at all (a
    text-only spec block), so a naive positional zip() silently shifts
    every later photo onto the wrong item the moment one is missing —
    tested against a real 13-item HIT tender where items 2-8 had no photo
    and this exact bug misattributed the LCR meter's photo to the FPGA
    board. Matching on the "N." heading number instead is immune to gaps,
    as long as that number lines up with the item's 1-based position in
    the Schedule of Requirement (true for this tender family; verify for
    others before trusting the pairing blindly).
    """
    for photo in photos:
        idx = photo.get("item_index")
        if idx is None:
            continue
        pos = idx - 1  # headings are 1-based ("1. MICROSCOPE" -> items[0])
        if 0 <= pos < len(items) and not items[pos].get("photo_bytes"):
            items[pos]["photo_bytes"] = photo["bytes"]
            items[pos]["photo_ext"] = photo["ext"]


def _classify_photo_layout(plumber_page, fitz_page, min_dim=_MIN_IMG_DIM):
    """Classifies how photos relate to table structure on a single PDF
    page, so the photo-pairing pipeline can pick the ONE matching
    strategy directly instead of trying each in a fixed order and
    inferring success from "did the bytes change" (which is how earlier
    versions of this module worked, and how a wrong-table match once
    produced silently blank crops - see _crop_photos_from_table_geometry's
    docstring). Returns one of:
      - "scanned_page"    : no real text layer at all (a straight scan) -
                             pdfplumber table/text geometry is meaningless
                             here; the scanned-page OCR path
                             (_reconstruct_table_from_ocr) is what
                             actually applies, not photo-table pairing.
      - "cell_embedded"    : pdfplumber found a real table AND at least
                             one sizeable image overlaps it - the photo
                             lives inside a table cell, so precise
                             geometry-based cropping
                             (_crop_photos_from_table_geometry) is
                             trustworthy and should be tried first.
      - "flattened_block"  : there's at least one large embedded image but
                             NO real pdfplumber table overlaps it - the
                             photo(s) and surrounding text were flattened
                             into one picture with no extractable table
                             structure at all (e.g. HIT-style Annexure A
                             packets); route straight to the pixel/OCR-
                             based splitter (_split_shared_photo_across_
                             items) rather than wasting a geometry attempt
                             that's guaranteed to find nothing relevant.
      - "proximity"        : normal case - real text layer, no big image
                             sitting inside/overlapping a table; photos
                             (if any) are separate objects positioned near
                             a heading, handled by the existing
                             proximity-based pairing.
    This is advisory, not a hard gate - callers can still fall back if a
    chosen strategy's output looks unusable, since even a good classifier
    can misjudge a layout it hasn't seen before."""
    text = plumber_page.extract_text() or ""
    if len(text.strip()) < 20:
        return "scanned_page"
    big_image_bboxes = []
    for img in fitz_page.get_images(full=True):
        xref = img[0]
        for r in fitz_page.get_image_rects(xref):
            if r.width >= min_dim and r.height >= min_dim:
                big_image_bboxes.append((r.x0, r.y0, r.x1, r.y1))
    if not big_image_bboxes:
        return "proximity"
    for t in plumber_page.find_tables():
        for ib in big_image_bboxes:
            if _rects_overlap_area(t.bbox, ib) > 0:
                return "cell_embedded"
    return "flattened_block"


def _attach_photos_by_position(items, file_stream, min_dim=_MIN_IMG_DIM, diagnostics=None):
    """
    General-purpose fallback pairing that works for tender layouts
    _attach_photos_to_items() can't handle: a flat schedule/spec TABLE with
    several items (and several photos) sharing the same page, whether the
    photo sits inside the item's own cell (e.g. HIT's "Technical
    Specification" table, Annexure A) or just above/below the table as a
    standalone picture. The single-heading-per-page approach above assumes
    one "N. ITEM NAME" heading per page and silently misattributes photos
    the moment two items land on the same page - this fixes that by
    matching on POSITION instead of a shared page-level heading:
      1. Find each item's identifying text (its Part No if it has one,
         else the first few words of its description) on the page using
         PyMuPDF text search.
      2. Claim the nearest not-yet-claimed image on that page - preferring
         one below the matched text (a photo normally sits inside or under
         its own row/cell) and falling back to the closest one overall.
    Each image can only be claimed once, so two items can never end up
    sharing (or fighting over) the same photo. Only fills in items that
    don't already have a photo, so it's safe to run after
    _attach_photos_to_items() as a supplement rather than a replacement.
    """
    if not FITZ_AVAILABLE or not items:
        return
    file_stream.seek(0)
    file_bytes = file_stream.read()
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        plumber_pdf = pdfplumber.open(io.BytesIO(file_bytes))
    except Exception as e:
        print(f"[Photo Layout Classify Warning]: pdfplumber unavailable, skipping layout routing: {e}")
        plumber_pdf = None
    try:
        seen_hashes = set()
        images_by_page = {}
        page_layout = {}  # pno -> "scanned_page" | "cell_embedded" | "flattened_block" | "proximity"
        for pno in range(len(doc)):
            page = doc[pno]
            if plumber_pdf is not None and pno < len(plumber_pdf.pages):
                try:
                    page_layout[pno] = _classify_photo_layout(plumber_pdf.pages[pno], page)
                except Exception as e:
                    print(f"[Photo Layout Classify Warning]: page {pno}: {e}")
            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    base_img = doc.extract_image(xref)
                except Exception:
                    continue
                width, height = base_img.get("width", 0), base_img.get("height", 0)
                if width < min_dim or height < min_dim:
                    continue  # icons/bullets/logos
                digest = hash(base_img["image"])
                if digest in seen_hashes:
                    continue  # repeated letterhead/crest
                seen_hashes.add(digest)
                rects = page.get_image_rects(xref)
                if not rects:
                    continue
                images_by_page.setdefault(pno, []).append({
                    "bytes": base_img["image"],
                    "ext": base_img.get("ext", "png"),
                    "bbox": rects[0],
                    "claimed": False,
                })
        # cand id -> ordered list of items that matched it. Some source
        # PDFs paste several items' photos as ONE flattened screenshot
        # spanning multiple table rows (common when a table is authored by
        # pasting a screenshot rather than inserting separate pictures) -
        # PyMuPDF then only ever sees a single image object for all of
        # them. We detect that below and crop it into per-item slices
        # instead of silently giving every item a copy of the whole thing.
        shared_claims = {}
        # Pre-build inverted index: key -> set of page numbers (avoids O(items*pages) text searches)
        text_to_pages = {}
        for item in items:
            if item.get("photo_bytes"):
                continue
            key = (item.get("part_no") or "").strip()
            if not key:
                desc_words = (item.get("description") or "").strip().split()
                key = " ".join(desc_words[:3])
            if not key:
                continue
            for pno in range(len(doc)):
                if page_layout.get(pno) == "scanned_page":
                    continue
                if doc[pno].search_for(key):
                    text_to_pages.setdefault(key, set()).add(pno)
        for item in items:
            if item.get("photo_bytes"):
                continue  # already paired by heading-based matching
            key = (item.get("part_no") or "").strip()
            if not key:
                desc_words = (item.get("description") or "").strip().split()
                key = " ".join(desc_words[:3])
            if not key:
                continue
            matched_pages = text_to_pages.get(key, set())
            for pno in sorted(matched_pages):
                if page_layout.get(pno) == "scanned_page":
                    continue  # no text layer here - search_for() below can never match
                candidates = images_by_page.get(pno)
                if not candidates:
                    continue
                hits = doc[pno].search_for(key)
                if not hits:
                    continue
                text_rect = hits[0]
                best, best_dist = None, None
                for cand in candidates:
                    # Favour an image below the matched text (its own
                    # row/cell); penalise ones above it so an earlier
                    # item's caption doesn't steal a later item's photo.
                    # Already-claimed candidates are still eligible here -
                    # if they turn out to be the nearest match, that's the
                    # "shared flattened screenshot" case handled below.
                    dy = cand["bbox"].y0 - text_rect.y1
                    dist = dy if dy >= -5 else abs(dy) + 1000
                    if best is None or dist < best_dist:
                        best, best_dist = cand, dist
                if best is not None:
                    best["claimed"] = True
                    item["photo_bytes"] = best["bytes"]
                    item["photo_ext"] = best["ext"]
                    claim = shared_claims.setdefault(
                        id(best), {"page_no": pno, "image_bbox": best["bbox"], "items": []}
                    )
                    claim["items"].append(item)
                break  # found the item's text on this page; stop scanning
        for claim in shared_claims.values():
            claimants = claim["items"]
            if len(claimants) < 2:
                continue
            layout = page_layout.get(claim["page_no"])
            # Route deterministically off the page's classified layout
            # instead of "try geometry, check if bytes changed, try
            # pixel-split" - a flattened_block page is GUARANTEED to have
            # no matching pdfplumber table (that's the definition), so
            # attempting geometry-based cropping on it would only waste
            # work before falling through anyway. Going straight to the
            # pixel/OCR splitter is both faster and removes the earlier
            # implicit "wrong table matched" failure mode entirely, since
            # geometry cropping is never even attempted where it can't
            # apply.
            if layout == "cell_embedded":
                original_bytes = claimants[0]["photo_bytes"]
                _crop_photos_from_table_geometry(claimants, claim["page_no"], claim["image_bbox"], file_stream)
                leftover = [it for it in claimants if it["photo_bytes"] == original_bytes]
                if len(leftover) >= 2:
                    _split_shared_photo_across_items(leftover)
            else:
                # flattened_block, proximity (multiple items somehow
                # sharing one image), or layout unknown (pdfplumber
                # unavailable) - all land here as the safest general
                # handler.
                _split_shared_photo_across_items(claimants)
                if diagnostics is not None and layout == "flattened_block":
                    diagnostics["warnings"].append(
                        f"Page {claim['page_no']}: {len(claimants)} items shared one flattened "
                        f"image with no real table structure - photos were pixel/OCR-split and "
                        f"are worth a quick visual check."
                    )
    finally:
        doc.close()
        if plumber_pdf is not None:
            plumber_pdf.close()


def _preprocess_for_ocr(pil_image):
    """Adaptive preprocessing before Tesseract: detects whether the page has
    uneven lighting (phone photos, spine shadows) and applies the right
    binarization method accordingly. Clean scans get Otsu (preserves edges);
    uneven pages get adaptive threshold (handles gradients). Also applies
    CLAHE for contrast normalization. Falls back to plain grayscale if
    OpenCV is unavailable."""
    try:
        import cv2
        import numpy as np
        arr = np.array(pil_image.convert("L"))
        # Detect uneven lighting by comparing tile means
        h, w = arr.shape
        tile_size = max(h // 4, 1), max(w // 4, 1)
        means = []
        for y in range(0, h - tile_size[0] + 1, tile_size[0]):
            for x in range(0, w - tile_size[1] + 1, tile_size[1]):
                tile = arr[y:y+tile_size[0], x:x+tile_size[1]]
                means.append(tile.mean())
        uneven = (max(means) - min(means)) > 40 if means else False
        # CLAHE for contrast normalization
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        contrasted = clahe.apply(arr)
        if uneven:
            binarized = cv2.adaptiveThreshold(
                contrasted, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
            )
        else:
            _, binarized = cv2.threshold(contrasted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return Image.fromarray(binarized)
    except Exception as e:
        print(f"[OCR Preprocess Warning]: {e}")
        return pil_image.convert("L")


def _deskew_image(pil_image, max_angle=30):
    """Detects and corrects small rotation (skew) in a scanned/photographed
    page before OCR. A tilted scan - common with phone-photographed
    tenders, or a paper document fed slightly crooked into a scanner -
    measurably degrades both Tesseract's text accuracy and the row/column
    gap-detection heuristics used elsewhere in this module, since "blank
    row" detection assumes real content runs horizontally.
    Uses OpenCV's minAreaRect over thresholded dark pixels to estimate the
    dominant skew angle, then rotates to level it. Deliberately capped at
    max_angle degrees: small angles are skew worth correcting, but a
    larger detected angle is more likely a genuinely rotated page (e.g.
    landscape content scanned in portrait orientation) where forcing a
    "correction" would make OCR worse, not better - that case needs an
    actual 90/180/270 rotation decision, not a skew fix.
    Returns the original image unchanged if OpenCV is unavailable, there's
    not enough content to estimate a reliable angle, or the estimated
    angle is negligible (<0.1 degrees) or exceeds max_angle."""
    try:
        import cv2
        import numpy as np
        arr = np.array(pil_image.convert("L"))
        thresh = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thresh > 0))
        if len(coords) < 50:
            return pil_image  # not enough content to trust an angle estimate
        angle = cv2.minAreaRect(coords)[-1]
        # cv2.minAreaRect's angle convention is [-90, 0); normalize to the
        # small rotation actually needed to level the page.
        angle = -(90 + angle) if angle < -45 else -angle
        if abs(angle) < 0.1 or abs(angle) > max_angle:
            return pil_image
        rgb_arr = np.array(pil_image.convert("RGB"))
        h, w = rgb_arr.shape[:2]
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        rotated = cv2.warpAffine(
            rgb_arr, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )
        return Image.fromarray(rotated)
    except Exception as e:
        print(f"[Deskew Warning]: {e}")
        return pil_image


def _ocr_text_mask(pil_image, min_conf=40):
    """Runs Tesseract's word-level OCR over `pil_image` and returns the
    bounding boxes of words it's actually confident about. This is a far
    more reliable "is this pixel region text?" signal than a raw pixel-
    darkness threshold: a shaded/colored header cell or a faint diagonal
    watermark is still "dark" by brightness alone, but Tesseract either
    reads real glyphs there (confident -> counts as text) or doesn't
    (low/no confidence, e.g. on a watermark's broken letterforms -> NOT
    counted as text, but also correctly excluded from being mistaken for
    a solid photo block later since real photo pixels form much denser,
    more contiguous regions than scattered low-confidence OCR noise).
    Returns [] (caller then behaves as if no text was found) if Tesseract
    isn't installed/reachable - a missing OCR engine should degrade to
    the pre-OCR darkness-only behaviour, not break extraction."""
    try:
        from pytesseract import Output
        ocr_input = _preprocess_for_ocr(pil_image)
        data = pytesseract.image_to_data(ocr_input, output_type=Output.DICT, config=_TESS_CONFIG_SPARSE)
    except Exception as e:
        print(f"[OCR Mask Warning]: Tesseract unavailable, falling back to darkness-only detection: {e}")
        return []
    boxes = []
    for i in range(len(data["text"])):
        if not data["text"][i].strip():
            continue
        try:
            conf = int(float(data["conf"][i]))
        except (ValueError, TypeError):
            continue
        if conf < min_conf:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        boxes.append((x, y, x + w, y + h))
    return boxes


def _text_mask_array(shape, text_boxes):
    """Boolean HxW array, True wherever an OCR text box (from
    _ocr_text_mask) lands. Used to zero those pixels out of the
    photo-column/row detectors below, so confidently-OCR'd text never
    gets counted as "photo" no matter how dark or dense it looks."""
    import numpy as np
    h, w = shape[0], shape[1]
    mask = np.zeros((h, w), dtype=bool)
    for x0, y0, x1, y1 in text_boxes:
        xa, ya = max(0, int(x0)), max(0, int(y0))
        xb, yb = min(w, int(x1)), min(h, int(y1))
        if xb > xa and yb > ya:
            mask[ya:yb, xa:xb] = True
    return mask


def _detect_photo_column(arr, text_mask=None, dark_threshold=245, min_col_frac=0.5):
    """Given an HxWx3 uint8 array of the flattened shared image, returns
    the (x0, x1) pixel range most likely to hold the actual photos rather
    than table text. A column is "photo-like" if it's densely non-white
    AFTER subtracting out any pixels Tesseract confidently identified as
    text (`text_mask`, from _ocr_text_mask/_text_mask_array) - so a
    shaded header cell or dense paragraph of real text can't be mistaken
    for a photo just because it isn't literally white. Falls back to a
    plain darkness threshold if no text_mask is supplied (e.g. Tesseract
    unavailable). Returns the widest contiguous run of qualifying
    columns, or the full width if nothing stands out."""
    gray = arr.mean(axis=2)
    dark = gray < dark_threshold
    if text_mask is not None:
        dark = dark & ~text_mask
    col_frac = dark.mean(axis=0)
    cols = col_frac > min_col_frac
    runs, start = [], None
    for x in range(len(cols)):
        if cols[x] and start is None:
            start = x
        elif not cols[x] and start is not None:
            runs.append((start, x))
            start = None
    if start is not None:
        runs.append((start, len(cols)))
    if not runs:
        return 0, arr.shape[1]
    return max(runs, key=lambda r: r[1] - r[0])


def _detect_row_bounds(arr, x0, x1, n_items, text_mask=None, dark_threshold=245, blank_row_frac=0.05, min_content_h=15):
    """Within the photo column (x0, x1) of the flattened shared image,
    finds the top/bottom pixel bounds of each item's own photo by looking
    for near-blank rows (gaps between one item's picture/caption and the
    next's) rather than assuming every item takes an equal share of the
    image height - real per-item photos in these tables are rarely the
    same height as each other. Non-white pixels Tesseract confidently
    read as text (`text_mask`) are excluded first, so a caption line
    doesn't register as "content" the same way a photo does - see
    _detect_photo_column for why that matters. Returns a list of
    n_items (top, bottom) tuples in top-to-bottom order, or None if the
    gaps found don't cleanly separate into exactly n_items content
    blocks (caller should fall back to an equal-height split)."""
    gray = arr.mean(axis=2)
    dark = gray < dark_threshold
    if text_mask is not None:
        dark = dark & ~text_mask
    row_frac = dark[:, x0:x1].mean(axis=1) if x1 > x0 else dark.mean(axis=1)
    height = arr.shape[0]
    is_blank = row_frac < blank_row_frac
    content_runs, start = [], None
    for y in range(height):
        if not is_blank[y] and start is None:
            start = y
        elif is_blank[y] and start is not None:
            if y - start >= min_content_h:
                content_runs.append((start, y))
            start = None
    if start is not None and height - start >= min_content_h:
        content_runs.append((start, height))
    if len(content_runs) != n_items:
        return None
    return content_runs


def _split_shared_photo_across_items(claimants):
    """Several items claimed the exact same source image - almost always
    because the source PDF pasted all of them as one flattened screenshot
    spanning multiple table rows (headers, text columns, and photos all
    baked into one picture) rather than separate embedded pictures per
    item. Rather than blindly slicing that image into equal-height,
    full-width bands (which bled one item's caption/photo into the next
    and kept the unrelated Ser No/Part No/Nomenclature/Tech Specs text
    columns and any page watermark), this auto-detects the actual photo
    region: an OCR text mask (_ocr_text_mask) marks every pixel Tesseract
    confidently read as a glyph, so a shaded cell or a faint watermark
    can't be mistaken for photo content just because it's not literally
    white. _detect_photo_column() then finds the x-range that's densely
    non-text-non-white (a photo), and _detect_row_bounds() finds real
    gaps between items' content within that column instead of assuming
    equal heights. Falls back to an equal-height split of just the
    detected photo column - still far tighter than the old full-width
    behaviour - if the gaps don't cleanly separate into exactly
    len(claimants) blocks, or if Tesseract isn't available at all (the
    OCR mask degrades to empty, and detection falls back to darkness-only,
    same as before OCR was added)."""
    try:
        import numpy as np
        first_bytes = claimants[0]["photo_bytes"]
        ext = claimants[0].get("photo_ext", "png")
        with Image.open(io.BytesIO(first_bytes)) as im:
            rgb = im.convert("RGB")
            arr = np.asarray(rgb)
            height, width = arr.shape[:2]
            text_boxes = _ocr_text_mask(rgb)
            text_mask = _text_mask_array(arr.shape, text_boxes) if text_boxes else None
            x0, x1 = _detect_photo_column(arr, text_mask=text_mask)
            row_bounds = _detect_row_bounds(arr, x0, x1, len(claimants), text_mask=text_mask)
            if row_bounds is None:
                band_h = height // len(claimants)
                if band_h < 10:
                    return  # too thin to usefully split - leave the shared image
                row_bounds = [
                    (i * band_h, height if i == len(claimants) - 1 else (i + 1) * band_h)
                    for i in range(len(claimants))
                ]
            fmt = (im.format or ext or "PNG").upper()
            for item, (top, bottom) in zip(claimants, row_bounds):
                crop = rgb.crop((x0, top, x1, bottom))
                buf = io.BytesIO()
                crop.save(buf, format=fmt if fmt != "JPG" else "JPEG")
                item["photo_bytes"] = buf.getvalue()
                item["photo_ext"] = ext
    except Exception as e:
        print(f"[Photo Split Error]: {e}")


def _cluster_columns(all_x, max_x_dist=25):
    """Groups word x-positions into table columns using proper distance-
    based hierarchical clustering (scipy) instead of one global gap
    threshold. A fixed gap multiplier assumes every column is roughly the
    same width - it breaks on real tender tables where a wide
    "Description" column sits next to narrow "Qty"/"Unit" columns, since
    one gap_threshold can't be right for both at once. Hierarchical
    clustering just groups positions that are genuinely close to each
    other, regardless of how that varies across the page. Returns a list
    of column-start x-positions in left-to-right order. Free (scipy is
    already a dependency) and negligible CPU/RAM cost - safe on
    constrained hardware. Falls back to a single column if scipy is
    unavailable or there's too little data to cluster."""
    if not all_x:
        return []
    if len(all_x) < 2:
        return [all_x[0]]
    try:
        from scipy.cluster.hierarchy import fclusterdata
        import numpy as np
        arr = np.array(all_x, dtype=float).reshape(-1, 1)
        labels = fclusterdata(arr, t=max_x_dist, criterion="distance")
        col_order = sorted(set(labels), key=lambda l: arr[labels == l].mean())
        return [float(arr[labels == l].min()) for l in col_order]
    except Exception as e:
        print(f"[Column Cluster Warning]: falling back to gap-based clustering: {e}")
        sorted_x = sorted(all_x)
        gaps = [b - a for a, b in zip(sorted_x, sorted_x[1:])]
        typical_gap = sorted(gaps)[len(gaps) // 2] if gaps else 0
        gap_threshold = max(typical_gap * 2.5, 20)
        col_starts = [sorted_x[0]]
        for a, b in zip(sorted_x, sorted_x[1:]):
            if b - a > gap_threshold:
                col_starts.append(b)
        return col_starts


def _reconstruct_table_from_ocr(fitz_page, dpi=300, y_tol=6, x_cluster_dist=25, diagnostics=None, page_no=None):
    """Rebuilds a text table grid for a SCANNED page (no extractable text
    layer at all, so pdfplumber's extract_tables()/extract_text() come
    back empty) by rasterizing the page, DESKEWING it and running it
    through _preprocess_for_ocr (a phone-photographed or unevenly-lit
    scan degrades OCR accuracy noticeably otherwise), then running
    Tesseract's word-level OCR over the corrected image and clustering
    the resulting words back into rows and columns the same way a person
    reading the scan would group them:
      1. Rows: words are sorted top-to-bottom and grouped whenever their
         vertical position is within y_tol pixels of the row's start -
         i.e. words that sit on roughly the same text line.
      2. Columns: _cluster_columns() groups every word's left x-position
         across the WHOLE page using proper distance-based clustering
         (not a single fixed gap threshold), so the same logical column
         lines up across different rows even when column widths vary a
         lot on the same page.
    Returns a list-of-lists grid compatible with _parse_table()/
    _parse_single_table_block() - the same shape pdfplumber's
    extract_tables() would have produced, so nothing downstream needs to
    know this table came from OCR instead of the PDF's real text layer.
    If `diagnostics` is supplied, appends a warning when the page's
    average OCR confidence is low, so callers know this page's items are
    worth a human double-check rather than trusting them silently.
    Returns [] if Tesseract is unavailable or the page yields no words."""
    try:
        pix = fitz_page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img = _deskew_image(img)
        img = _preprocess_for_ocr(img)
        from pytesseract import Output
        data = pytesseract.image_to_data(img, output_type=Output.DICT, config=_TESS_CONFIG_TABLE)
    except Exception as e:
        print(f"[OCR Table Reconstruct Error]: {e}")
        if diagnostics is not None:
            diagnostics["warnings"].append(f"Scanned-page OCR failed on page {page_no}: {e}")
        return []
    words = []
    all_confs = []
    for i in range(len(data["text"])):
        txt = data["text"][i].strip()
        if not txt:
            continue
        try:
            conf = int(float(data["conf"][i]))
        except (ValueError, TypeError):
            conf = -1
        if conf >= 0:
            all_confs.append(conf)
        if conf < 30:
            continue
        words.append((data["left"][i], data["top"][i], data["width"][i], txt))
    if diagnostics is not None and all_confs:
        avg_conf = sum(all_confs) / len(all_confs)
        if avg_conf < 50:
            diagnostics["warnings"].append(
                f"Scanned page {page_no}: low average OCR confidence ({avg_conf:.0f}%) - "
                f"items reconstructed from this page may have inaccurate text/numbers."
            )
            diagnostics.setdefault("low_confidence_pages", []).append(page_no)
    if not words:
        return []
    # --- cluster into rows (by y-position) ---
    words.sort(key=lambda w: w[1])
    row_groups, current_row, current_y = [], [], None
    for x, y, w, txt in words:
        if current_y is None or abs(y - current_y) <= y_tol:
            current_row.append((x, w, txt))
            current_y = y if current_y is None else current_y
        else:
            row_groups.append(current_row)
            current_row, current_y = [(x, w, txt)], y
    if current_row:
        row_groups.append(current_row)
    # --- cluster into columns (by x-position, across the whole page) ---
    all_x = [x for row in row_groups for x, w, txt in row]
    col_starts = _cluster_columns(all_x, max_x_dist=x_cluster_dist)
    def _col_index(x):
        i = bisect.bisect_left(col_starts, x)
        candidates = [j for j in (i-1, i, i+1) if 0 <= j < len(col_starts)]
        return min(candidates, key=lambda j: abs(col_starts[j] - x)) if candidates else 0
    # --- build the grid, space-joining words that land in the same cell ---
    grid = []
    for row in sorted(row_groups, key=lambda r: min(x for x, w, txt in r)):
        row.sort(key=lambda cell: cell[0])
        cells = [""] * len(col_starts)
        for x, w, txt in row:
            ci = _col_index(x)
            cells[ci] = f"{cells[ci]} {txt}".strip() if cells[ci] else txt
        grid.append(cells)
    return grid

_gmft_lock = threading.Lock()

def _get_gmft_engine():
    """Lazily creates and caches the gmft detector/formatter pair (mirrors
    the old _get_paddle_engine caching pattern) so the underlying Table
    Transformer model weights are loaded once per process, not once per
    page/document."""
    global _gmft_detector, _gmft_formatter
    if _gmft_detector is None or _gmft_formatter is None:
        with _gmft_lock:
            if _gmft_detector is None:
                _gmft_detector = AutoTableDetector()
            if _gmft_formatter is None:
                _gmft_formatter = AutoTableFormatter()
    return _gmft_detector, _gmft_formatter


def _reconstruct_table_from_gmft(gmft_page, diagnostics=None, page_no=None):
    """Same contract as _reconstruct_table_from_ocr (returns a grid or
    None) but uses Microsoft's Table Transformer (via gmft), which
    handles multi-column tender layouts far better than Tesseract.
    Replaces the previous PaddleOCR/PP-StructureV3 integration - a single
    detection model instead of PP-StructureV3's five-stage pipeline, and
    MIT licensed. gmft_page is a gmft BasePage (see PyPDFium2Document),
    not a raw fitz page."""
    if not GMFT_AVAILABLE or gmft_page is None:
        return None
    try:
        detector, formatter = _get_gmft_engine()
        cropped_tables = detector.extract(gmft_page)
        for cropped in cropped_tables:
            formatted = formatter.extract(cropped)
            grid = _gmft_table_to_grid(formatted)
            if grid:
                return grid
        return None
    except Exception as e:
        if diagnostics is not None:
            diagnostics["warnings"].append(f"gmft failed on page {page_no}: {e}")
        return None


def _gmft_table_to_grid(formatted_table):
    """Converts a gmft FormattedTable's DataFrame into the same
    list-of-rows grid format the rest of this module expects (first row
    is the header row), so every downstream parser - column
    classification, header detection, _parse_table(), etc. - works
    unchanged regardless of which table engine produced the grid."""
    try:
        df = formatted_table.df()
    except Exception:
        return None
    if df is None or df.empty:
        return None
    header = [str(c) for c in df.columns]
    grid = [header]
    for _, row in df.iterrows():
        grid.append(["" if v is None else str(v) for v in row.tolist()])
    return grid


def _find_photo_column(pdf_table):
    """Given a pdfplumber Table object, returns the column index most
    likely to hold a photo rather than text: the column that comes back
    empty as extracted TEXT across the most data rows, since an embedded
    picture yields no text under extract_text()/extract(). Falls back to
    the last column - the layouts this pipeline sees (HIT-style Ser/Part
    No/Nomenclature/Tech Specs schedules) consistently put the photo in
    the final, unlabeled column."""
    rows = pdf_table.extract()
    if not rows or not rows[0]:
        return -1
    num_cols = len(rows[0])
    data_rows = rows[1:] if len(rows) > 1 else rows
    if not data_rows:
        return num_cols - 1
    empty_counts = [0] * num_cols
    for row in data_rows:
        for c in range(min(num_cols, len(row))):
            if not str(row[c] or "").strip():
                empty_counts[c] += 1
    best_col = max(range(num_cols), key=lambda c: empty_counts[c])
    return best_col if empty_counts[best_col] > 0 else num_cols - 1


def _rects_overlap_area(a, b):
    """Intersection area of two (x0, top, x1, bottom)-style boxes (works
    for both plain tuples and fitz.Rect, which supports the same indexing
    via x0/y0/x1/y1 attributes - callers pass tuples here)."""
    ax0, atop, ax1, abottom = a
    bx0, btop, bx1, bbottom = b
    ix0, ix1 = max(ax0, bx0), min(ax1, bx1)
    itop, ibottom = max(atop, btop), min(abottom, bbottom)
    if ix1 <= ix0 or ibottom <= itop:
        return 0.0
    return (ix1 - ix0) * (ibottom - itop)


def _crop_photos_from_table_geometry(item_dicts, page_no, image_bbox, file_stream):
    """Precise, per-row photo crops using a REAL pdfplumber-detected
    table's row and column bounding boxes, rendered fresh from the live
    PDF page (via fitz) - instead of guessing equal-height bands on a
    single flattened embedded image (see _split_shared_photo_across_
    items). That band-split approach had two compounding bugs whenever a
    source table pasted several items' photos - and the text columns
    around them - as ONE screenshot rather than separate pictures:
      1. Real table rows aren't equal height, so an equal-height vertical
         split lands mid-row - one item's caption/photo bleeds down into
         the next item's crop.
      2. The crop kept the FULL WIDTH of the flattened image, which
         already baked in the Ser No/Part No/Nomenclature/Tech Specs text
         columns, the header row, and any page watermark - a vertical-
         only split can never trim that away.
    This instead clips exactly the photo column's real cell bbox for each
    row, straight off the page, so none of the above can leak in.

    IMPORTANT: some source PDFs (e.g. HIT-style Annexure A packets) paste
    the entire per-item photo block as ONE flattened picture with no real
    table lines pdfplumber can detect at all - pdfplumber may still find
    an unrelated table elsewhere on the same page (e.g. a plain-text
    Schedule of Requirement above it) and, without a check, that gets
    mistaken for the photo table, producing blank crops from whatever
    column happens to line up. To guard against that, this only proceeds
    if a candidate table's bbox actually overlaps `image_bbox` - the real
    bbox of the shared image being split - and picks whichever candidate
    overlaps it most, not just whichever has the most rows. If nothing
    overlaps, it does nothing and leaves item_dicts untouched so the
    caller's pixel-based fallback (_split_shared_photo_across_items) can
    take over.

    :param item_dicts: item dicts (same references as the caller's
        `items` list) in the SAME top-to-bottom row order they appear in
        the source table on `page_no`. Mutated in place - matches the
        calling convention of _split_shared_photo_across_items().
    :param page_no: 0-based page index the shared image was found on.
    :param image_bbox: fitz.Rect (or any x0/y0/x1/y1-indexable box) of the
        actual shared image on that page, used for the overlap check.
    :param file_stream: the original uploaded file stream (PDF).
    """
    if not item_dicts:
        return
    try:
        import pdfplumber
    except Exception as e:
        print(f"[Geometry Crop Error]: pdfplumber unavailable: {e}")
        return
    file_stream.seek(0)
    file_bytes = file_stream.read()
    try:
        plumber_pdf = pdfplumber.open(io.BytesIO(file_bytes))
    except Exception as e:
        print(f"[Geometry Crop Error]: could not open with pdfplumber: {e}")
        return
    fitz_doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        if page_no >= len(plumber_pdf.pages) or page_no >= len(fitz_doc):
            return
        plumber_page = plumber_pdf.pages[page_no]
        tables = plumber_page.find_tables()
        if not tables:
            return
        img_box = (image_bbox.x0, image_bbox.y0, image_bbox.x1, image_bbox.y1)
        pdf_table, best_overlap = None, 0.0
        for t in tables:
            overlap = _rects_overlap_area(t.bbox, img_box)
            if overlap > best_overlap:
                pdf_table, best_overlap = t, overlap
        if pdf_table is None:
            # No pdfplumber table spatially corresponds to the actual
            # shared image - it's a flattened picture with no detectable
            # table structure. Bail out rather than grab an unrelated
            # table on the same page.
            return
        photo_col = _find_photo_column(pdf_table)
        data_rows = pdf_table.rows
        # Align the LAST len(item_dicts) rows with the claimant items,
        # since header row(s) sit above the data rows.
        usable_rows = data_rows[-len(item_dicts):] if len(data_rows) >= len(item_dicts) else data_rows
        fitz_page = fitz_doc[page_no]
        for item, row in zip(item_dicts, usable_rows):
            cell = row.cells[photo_col] if 0 <= photo_col < len(row.cells) else None
            bbox = cell if cell else row.bbox
            if not bbox:
                continue
            x0, top, x1, bottom = bbox
            # Small inset so the crop doesn't grab the cell border/grid
            # line running right along the edge.
            clip = fitz.Rect(x0 + 1, top + 1, x1 - 1, bottom - 1)
            if clip.is_empty or clip.width < 5 or clip.height < 5:
                continue
            pix = fitz_page.get_pixmap(clip=clip, dpi=200)
            item["photo_bytes"] = pix.tobytes("png")
            item["photo_ext"] = "png"
    except Exception as e:
        print(f"[Geometry Crop Error]: {e}")
    finally:
        fitz_doc.close()
        plumber_pdf.close()


def extract_images_from_file(file_stream, filename="", min_dim=_MIN_IMG_DIM,
                              output_dir=None, pair_with_headings=True):
    """
    Extracts embedded photos/images from a PDF, Word, or Excel file.

    :param file_stream: BytesIO/file-like object of the uploaded file.
    :param filename: original filename, used to pick the reader.
    :param min_dim: minimum width/height in px; smaller images (logos,
        bullet icons, letterhead crests, watermarks) are skipped.
    :param output_dir: if given, each image is also written to disk there
        (created if missing) and the dict gets a "path" key.
    :param pair_with_headings: if True (PDF only), attaches the nearest
        "N. ITEM NAME" heading found on the same page, so images can be
        matched up with extract_items_from_file() results by "item_index".
    :return: list of dicts, one per extracted image, each with:
        {page, item_index, item_heading, ext, width, height, bytes, path?}
    """
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    file_stream.seek(0)
    if ext in {"docx", "doc"} or (ext == "" and filename == ""):
        return _extract_images_from_docx(file_stream, min_dim, output_dir)
    if ext in {"xlsx", "xls"}:
        return _extract_images_from_excel(file_stream, min_dim, output_dir)
    # default to PDF
    return _extract_images_from_pdf(file_stream, min_dim, output_dir, pair_with_headings)


def _extract_images_from_pdf(file_stream, min_dim, output_dir, pair_with_headings):
    if not FITZ_AVAILABLE:
        print("[Image Extract Error]: PyMuPDF (`fitz`) is not installed. Run `pip install pymupdf`.")
        return []
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    file_stream.seek(0)
    file_bytes = file_stream.read()
    results = []
    seen_hashes = set()  # de-dupe repeated header/footer logos across pages
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        # Build one heading lookup pass ahead of time so we don't re-parse
        # text per image.
        page_headings = {}
        if pair_with_headings:
            for pno in range(len(doc)):
                text = doc[pno].get_text()
                m = _ITEM_HEADING_RE.search(text)
                if m:
                    page_headings[pno] = (int(m.group(1)), m.group(2).strip())

        counter = 0
        for pno in range(len(doc)):
            page = doc[pno]
            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    base_img = doc.extract_image(xref)
                except Exception as e:
                    print(f"[Image Extract Error] page {pno+1}, xref {xref}: {e}")
                    continue
                img_bytes = base_img["image"]
                width, height = base_img.get("width", 0), base_img.get("height", 0)
                if width < min_dim or height < min_dim:
                    continue  # skip icons/bullets/logos
                digest = int(hashlib.md5(img_bytes).hexdigest()[:8], 16)
                if digest in seen_hashes:
                    continue  # skip repeated letterhead/crest across pages
                seen_hashes.add(digest)
                counter += 1
                image_ext = base_img.get("ext", "png")
                item_index, item_heading = page_headings.get(pno, (None, None))
                record = {
                    "page": pno + 1,
                    "item_index": item_index,
                    "item_heading": item_heading,
                    "ext": image_ext,
                    "width": width,
                    "height": height,
                    "bytes": img_bytes,
                }
                if output_dir:
                    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", item_heading or f"page{pno+1}")
                    out_path = os.path.join(
                        output_dir, f"{counter:02d}_{safe_name}.{image_ext}"
                    )
                    with open(out_path, "wb") as f:
                        f.write(img_bytes)
                    record["path"] = out_path
                results.append(record)
    finally:
        doc.close()
    return results


def _extract_images_from_docx(file_stream, min_dim, output_dir):
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    file_stream.seek(0)
    results = []
    try:
        doc = docx.Document(file_stream)

        # Build heading lookup: scan paragraphs for item headings
        # (e.g. "1. Description of Item") so we can pair images with items.
        headings = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            m = _ITEM_HEADING_RE.match(text)
            if m:
                headings.append((int(m.group(1)), m.group(2).strip()))

        # Track which heading index we're currently under
        heading_idx = 0
        counter = 0
        for rel_id, rel in doc.part.rels.items():
            if "image" not in rel.reltype:
                continue
            img_bytes = rel.target_part.blob
            try:
                with Image.open(io.BytesIO(img_bytes)) as im:
                    width, height = im.size
                    image_ext = (im.format or "png").lower()
            except Exception:
                continue
            if width < min_dim or height < min_dim:
                continue

            # Find nearest heading (images typically follow their heading)
            item_index, item_heading = None, None
            if headings:
                # Use the last heading seen before or at current position
                # Since we can't precisely locate images in paragraph order,
                # use the heading that appeared most recently
                if heading_idx < len(headings):
                    item_index, item_heading = headings[heading_idx]
                    heading_idx = min(heading_idx + 1, len(headings) - 1)

            counter += 1
            record = {
                "page": None,
                "item_index": item_index,
                "item_heading": item_heading,
                "ext": image_ext,
                "width": width,
                "height": height,
                "bytes": img_bytes,
            }
            if output_dir:
                safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", item_heading or f"img{counter}")
                out_path = os.path.join(output_dir, f"{counter:02d}_{safe_name}.{image_ext}")
                with open(out_path, "wb") as f:
                    f.write(img_bytes)
                record["path"] = out_path
            results.append(record)
    except Exception as e:
        print(f"[Image Extract Error docx]: {e}")
    return results


def _extract_images_from_excel(file_stream, min_dim=_MIN_IMG_DIM, output_dir=None):
    """
    Extracts embedded images from an Excel workbook (.xlsx/.xls).

    Parses the XLSX as a ZIP to locate xl/media/ images, then maps each
    image to its sheet name and row index via xl/drawings/drawingN.xml
    and the sheet-to-drawing relationship files.

    Returns dict: {sheet_name: [{bytes, ext, row_index, width, height}, ...]}
    keyed by sheet tab name so callers can pair photos per-sheet.
    """

    results_by_sheet = {}
    import zipfile
    import io
    from PIL import Image

    file_stream.seek(0)
    file_bytes = file_stream.read()

    # .xls (OLE2) files embed images in binary Escher streams, not ZIP XML
    if file_bytes[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        print("[Excel Image Extract]: .xls (OLE2) format — images embedded in binary streams, "
              "not extractable via ZIP/XML. Convert to .xlsx first for photo extraction.")
        return {}

    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            media_files = sorted([n for n in zf.namelist() if n.startswith("xl/media/")])
            if not media_files:
                return {}

            # Build media_path -> raw bytes + ext map
            media_map = {}
            for media_path in media_files:
                img_bytes = zf.read(media_path)
                ext = media_path.rsplit(".", 1)[-1].lower()
                if ext not in {"png", "jpg", "jpeg", "gif", "bmp", "tiff", "svg"}:
                    ext = "png"
                try:
                    with Image.open(io.BytesIO(img_bytes)) as im:
                        width, height = im.size
                except Exception:
                    width, height = 0, 0
                if width < min_dim or height < min_dim:
                    continue
                media_map[media_path] = {"bytes": img_bytes, "ext": ext, "width": width, "height": height}

            # --- Map sheet names to drawing XMLs via worksheet rels ---
            # xl/worksheets/_rels/sheetN.xml.rels -> references drawingM.xml
            # xl/workbook.xml.rels maps workbook.xml sheet entries to sheetN.xml
            sheet_rels_files = sorted([n for n in zf.namelist()
                                       if re.match(r"xl/worksheets/_rels/sheet\d+\.xml\.rels$", n)])
            # Also get sheet names from workbook.xml
            wb_xml = zf.read("xl/workbook.xml").decode("utf-8", errors="ignore")
            sheet_name_order = re.findall(r'<sheet\s[^>]*name="([^"]+)"', wb_xml)

            drawing_to_sheet = {}  # drawing_file -> sheet_name
            for idx, rels_path in enumerate(sheet_rels_files):
                rels_xml = zf.read(rels_path).decode("utf-8", errors="ignore")
                draw_match = re.search(r'Target="([^"]*drawing\d+\.xml)"', rels_xml)
                if draw_match:
                    draw_file = draw_match.group(1).lstrip("/")
                    # Resolve relative paths like ../drawings/drawing1.xml -> xl/drawings/drawing1.xml
                    if draw_file.startswith("../"):
                        draw_file = "xl/" + draw_file[3:]
                    sheet_name = sheet_name_order[idx] if idx < len(sheet_name_order) else f"Sheet{idx+1}"
                    drawing_to_sheet[draw_file] = sheet_name

            # --- Parse each drawing XML to get (rId -> row_index) and (rId -> media_path) ---
            drawing_files = sorted([n for n in zf.namelist()
                                    if re.match(r"xl/drawings/drawing\d+\.xml", n)])

            for dr_path in drawing_files:
                sheet_name = drawing_to_sheet.get(dr_path, "Unknown")
                dr_xml = zf.read(dr_path).decode("utf-8", errors="ignore")

                # Parse the rels file for this drawing to map rId -> media_path
                dr_rels_path = f"xl/drawings/_rels/{dr_path.split('/')[-1]}.rels"
                rid_to_media = {}
                if dr_rels_path in zf.namelist():
                    rels_xml = zf.read(dr_rels_path).decode("utf-8", errors="ignore")
                    for rm in re.finditer(r'<Relationship[^>]+>', rels_xml):
                        tag = rm.group(0)
                        id_m = re.search(r'Id="(rId\d+)"', tag)
                        tgt_m = re.search(r'Target="([^"]+)"', tag)
                        if id_m and tgt_m:
                            target = tgt_m.group(1).lstrip("/")
                            # Resolve relative paths like ../media/image1.jpeg -> xl/media/image1.jpeg
                            if target.startswith("../"):
                                # Drawing XML is at xl/drawings/drawingN.xml
                                target = "xl/" + target[3:]
                            rid_to_media[id_m.group(1)] = target

                # Parse anchors: <oneCellAnchor> and <twoCellAnchor> blocks with <from><row>N</row>
                anchors = re.findall(
                    r'<(?:xdr:)?(?:one|two)CellAnchor[^>]*>.*?</(?:xdr:)?(?:one|two)CellAnchor>|<absoluteAnchor[^>]*>.*?</absoluteAnchor>',
                    dr_xml, re.DOTALL
                )
                for anchor_xml in anchors:
                    # Extract rId from r:embed="rIdN"
                    rid_match = re.search(r'r:embed="(rId\d+)"', anchor_xml)
                    # Extract row from <xdr:from><xdr:row>N</xdr:row> (namespace prefix optional)
                    row_match = re.search(r'<(?:xdr:)?from>.*?<(?:xdr:)?row>(\d+)</(?:xdr:)?row>', anchor_xml, re.DOTALL)
                    if not rid_match or not row_match:
                        continue
                    rid = rid_match.group(1)
                    row_0based = int(row_match.group(1))
                    media_path = rid_to_media.get(rid)
                    if not media_path or media_path not in media_map:
                        continue
                    record = dict(media_map[media_path])
                    record["row_index"] = row_0based + 1  # 0-based -> 1-based
                    record["sheet"] = sheet_name
                    results_by_sheet.setdefault(sheet_name, []).append(record)

    except Exception as e:
        print(f"[Excel Image Extract Error]: {e}")
        return {}

    return results_by_sheet


# =========================================================================
# DOCUMENT TYPE DETECTION — flat quotation vs "dual-table" tender packets
#
# Some Invitation-to-Tender documents (e.g. defence/PSU procurement SBDs)
# split their item data across TWO different table shapes instead of one
# flat item table:
#   1. A short "Schedule of Requirement" table   — Ser / Description / A-U /
#      Qty / DP(months) / Remarks — no prices, since it's an inquiry.
#   2. One separate "Parameters" spec table PER ITEM, breaking the item
#      down into General / Performance / Critical attribute rows (the
#      "Appendix" style block with Type, Processor, Memory, etc.)
# The two tables are only linkable by their ORDER (item 1's schedule row
# lines up with the first spec table, item 2's with the second, etc).
# =========================================================================


def _collapse_blank_columns(table):
    """pdfplumber sometimes splits a table's real columns into several extra
    blank sub-columns - an artifact of merged/irregular cell borders in the
    source PDF (a real 6-column "Ser/Part No/Nomenclature/A-U/Qty/Remarks"
    table can come back as 18 columns, most of them None in every row). A
    column that is blank across every single row carries no information and
    only shifts every downstream positional column-index lookup
    (_find_desc_column, _find_column, _infer_columns_from_data) off by
    however many blank columns preceded it. Dropping any all-blank column
    restores the grid to its real column count before any header/column
    logic runs."""
    if not table:
        return table
    num_cols = max((len(r) for r in table), default=0)
    if num_cols == 0:
        return table
    keep = [c for c in range(num_cols)
            if any(str((r[c] if c < len(r) else "") or "").strip() for r in table)]
    if len(keep) == num_cols:
        return table
    return [[r[c] if c < len(r) else None for c in keep] for r in table]


def _table_signature(table):
    """Cheap lower-cased text blob of a table's first few rows, used to
    fingerprint its structure without re-scanning the whole table."""
    sample_rows = table[:6] if table else []
    return " ".join(str(c or "").strip().lower() for row in sample_rows for c in row)


def _looks_like_schedule_header(row):
    """Cell-level (not substring-blob) check for a Ser/A-U/Qty style header.
    Deliberately strict: matching 'ser' as a loose substring would also hit
    ordinary prose words like 'Supplier' or 'reserves', which is exactly
    what caused false positives across a document's legal boilerplate."""
    if not row:
        return False
    cells = [str(c or "").strip().lower() for c in row]
    has_ser = any(c in ("ser", "ser.", "s.", "sno", "sl.no", "sl.no.", "s.no", "sr.no", "sr.") for c in cells)
    has_secondary = any(
        (c == "a/u" or (len(c) < 15 and "a/u" in c))
        or c in ("qty", "quantity")
        or "dp (month" in c
        or "delivery period" in c
        for c in cells
    )
    return has_ser and has_secondary


def _table_has_real_schedule_data(table, header_row_idx):
    """Distinguishes a genuinely filled-in Schedule of Requirement from a
    blank fill-in-the-blanks template (e.g. the empty "Financial Proposal /
    Schedule of Price" annexure, which also has Ser/A-U/Quantity column
    headers but no actual quantities yet, since the bidder fills those in
    later). Checks whether the Qty/Quantity column actually contains a
    numeric value on a genuine numbered item row; if the column can't be
    located we don't block on it."""
    if header_row_idx is None or header_row_idx >= len(table):
        return False
    header = [str(c or "").strip().lower() for c in table[header_row_idx]]
    qty_idx = None
    for idx, cell in enumerate(header):
        if cell in ("qty", "quantity"):
            qty_idx = idx
            break
    if qty_idx is None:
        return True
    for row in table[header_row_idx + 1:]:
        first_cell = str(row[0] or "").strip()
        # Only trust rows whose first cell is a genuine item serial number
        # ("1.", "2.", ...) - summary/total rows ("Total Price without
        # Taxes:", "Details of applicable Taxes:") don't line up with the
        # header's column grid and can spill unrelated text (e.g. "GST/PST")
        # into whatever index the Qty column happens to sit at.
        if not first_cell or not _is_pure_number_or_sno(first_cell):
            continue
        if qty_idx < len(row) and _extract_number(str(row[qty_idx] or "")) is not None:
            return True
    return False


def _count_spec_markers_in_first_column(table):
    """Counts distinct spec-table category markers (General/Performance/
    Critical/Parameters) found in the first 3 columns of a table -
    these category labels can appear in column 0, 1, or 2 depending on
    table layout. Matching anywhere in the table's text (a loose blob match)
    causes false positives on unrelated tables whose headings merely happen
    to contain these words."""
    found = set()
    for row in table[:8]:
        if not row:
            continue
        for col_idx in range(min(3, len(row))):
            cell = str(row[col_idx] or "").strip().lower()
            for w in _SPEC_TABLE_MARKERS:
                if cell == w or cell.startswith(w + " ") or cell.startswith(w + ":"):
                    found.add(w)
    return len(found)


def _classify_table(table):
    """Classifies a single raw table grid as 'schedule_table', 'spec_table',
    or 'item_table' (a generic flat quotation-style item table)."""
    if not table:
        return "empty"
    # Scan the first few rows (not just row 0) for a Ser/A-U/Qty header.
    # pdfplumber frequently produces a blank leading row - or extra blank
    # columns - ahead of the real header row when the source PDF table has
    # merged/irregular cell borders (common in HIT-style Annexure A
    # schedules), which would otherwise hide the header from row-0-only
    # detection entirely.
    for idx, row in enumerate(table[:3]):
        if _looks_like_schedule_header(row):
            if _table_has_real_schedule_data(table, idx):
                return "schedule_table"
            break
    spec_marker_hits = _count_spec_markers_in_first_column(table)
    if spec_marker_hits >= 2:
        return "spec_table"
    return "item_table"


def _merge_spec_table_continuations(tables):
    """pdfplumber extracts tables per PAGE, so a single logical per-item spec
    sheet that spans a page break comes back as two or more separate raw
    tables (the second fragment missing its category/header cells). This
    stitches those fragments back onto the preceding spec_table instead of
    letting them get misread as unrelated tables — recognisable because a
    continuation fragment's leading cell is blank (the category column was
    merged/rotated in the original PDF and doesn't repeat on the new page).
    Returns a list of (kind, table) tuples, one per *logical* table.
    """
    merged = []
    current_kind = None
    current_table = None
    for table in tables:
        kind = _classify_table(table)
        first_cell_blank = bool(table) and bool(table[0]) and not str(table[0][0] or "").strip()
        if current_kind == "spec_table" and kind != "schedule_table" and first_cell_blank:
            current_table.extend(table)
            continue
        if current_table is not None:
            merged.append((current_kind, current_table))
        current_kind = kind
        current_table = list(table)
    if current_table is not None:
        merged.append((current_kind, current_table))
    return merged


def _classify_tables(tables):
    """Classifies a whole document (list of raw table grids) into one of:
    'tender_dual_table', 'quotation', or 'unknown'. Exposed indirectly via
    detect_document_type() for callers that want to label the upload."""
    if not tables:
        return "unknown"
    kinds = [_classify_table(t) for t in tables]
    has_schedule = "schedule_table" in kinds
    has_spec = kinds.count("spec_table") >= 1
    if has_schedule and has_spec:
        return "tender_dual_table"
    if any(k == "item_table" for k in kinds):
        return "quotation"
    return "unknown"


def detect_document_type(file_stream, filename=""):
    """
    Public helper: classifies an uploaded file's table structure so the
    caller can label it / choose how to display it. Returns one of:
      - "tender_dual_table": a Schedule-of-Requirement table PLUS separate
        per-item technical specification tables (e.g. HIT-style ITB/SBD
        tender packets).
      - "quotation": a normal flat item table (description/qty/price).
      - "plain_text": no usable tables found (would fall back to text parsing).
      - "unknown": unsupported file type or nothing recognizable found.
    """
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    try:
        if ext in {"docx", "doc"} or (ext == "" and filename == ""):
            file_stream.seek(0)
            doc = docx.Document(file_stream)
            tables = []
            for table in doc.tables:
                grid = [[" ".join(cell.text.split()) for cell in row.cells] for row in table.rows]
                grid = [r for r in grid if any(r)]
                if grid:
                    tables.append(grid)
            result = _classify_tables(tables)
            return result if result != "unknown" else ("plain_text" if not tables else "unknown")
        if ext in {"xlsx", "xls"}:
            try:
                file_stream.seek(0)
                if ext == "xls" and XLRD_AVAILABLE:
                    wb = xlrd.open_workbook(file_contents=file_stream.read())
                    for sname in wb.sheet_names():
                        sh = wb.sheet_by_name(sname)
                        for r in range(min(5, sh.nrows)):
                            row = [str(sh.cell_value(r, c)).strip().lower() for c in range(sh.ncols)]
                            if _looks_like_schedule_header(row):
                                return "tender_dual_table"
                else:
                    wb = openpyxl.load_workbook(file_stream, read_only=True, data_only=True)
                    for sname in wb.sheetnames:
                        raw = _fill_merged_cells(wb[sname])
                        for row in raw[:5]:
                            if _looks_like_schedule_header(row):
                                wb.close()
                                return "tender_dual_table"
                    wb.close()
            except Exception:
                pass
            return "quotation"
        if ext in {"png", "jpg", "jpeg", "webp", "bmp"}:
            return "plain_text"
        # Default: treat as PDF
        file_stream.seek(0)
        with pdfplumber.open(file_stream) as pdf:
            tables = []
            for page in pdf.pages:
                tables.extend(t for t in page.extract_tables() if t)
            result = _classify_tables(tables)
            return result if result != "unknown" else ("plain_text" if not tables else "unknown")
    except Exception as e:
        print(f"[Doc Type Detection Error]: {e}")
        return "unknown"
    finally:
        try:
            file_stream.seek(0)
        except Exception:
            pass


def _spec_table_description(table):
    """Boils a per-item 'Parameters' spec table down into a single
    description string: prefer the 'Type' row (usually the fullest
    plain-English description of the item), falling back to the longest
    value cell found anywhere in the table."""
    best_type_value = ""
    longest_value = ""
    for row in table:
        cells = [_WHITESPACE_RE.sub(" ", str(c or "")).strip() for c in row]
        if not any(cells):
            continue
        row_lower = [c.lower() for c in cells]
        if "type" in row_lower:
            idx = row_lower.index("type")
            for candidate in cells[idx + 1:]:
                if candidate and len(candidate) > len(best_type_value):
                    best_type_value = candidate
        for cell in cells:
            if cell.lower() not in _SPEC_TABLE_MARKERS and len(cell) > len(longest_value):
                longest_value = cell
    return (best_type_value or longest_value).strip()


def _extract_dual_table_tender(tables):
    """Merges a Schedule-of-Requirement table with its trailing per-item
    spec tables (matched by sequence order) into a single flat item list:
    {description, unit, qty, unit_price}. Since these are tender inquiries
    (not priced quotations), unit_price defaults to 0.0."""
    schedule_rows = []
    spec_tables = []
    for kind, table in _merge_spec_table_continuations(tables):
        if kind == "schedule_table":
            schedule_rows.extend(_parse_single_table_block(table))
        elif kind == "spec_table":
            spec_tables.append(table)
    if not schedule_rows:
        # No schedule found at all — just fall back to whatever the spec
        # tables themselves yield as standalone descriptions.
        return [
            {"description": _spec_table_description(t)[:250] or f"Item {i + 1}",
             "part_no": "", "unit": "Nos", "qty": 1.0, "unit_price": 0.0}
            for i, t in enumerate(spec_tables)
        ][:MAX_ITEMS]
    results = []
    for idx, row in enumerate(schedule_rows):
        if idx >= MAX_ITEMS:
            break
        description = row.get("description", "").strip()
        if idx < len(spec_tables):
            spec_desc = _spec_table_description(spec_tables[idx])
            if spec_desc:
                description = f"{description} — {spec_desc}".strip(" —") if description else spec_desc
        results.append({
            "description": description[:250] or f"Item {idx + 1}",
            "part_no": row.get("part_no", "") or "",
            "unit": row.get("unit", "Nos") or "Nos",
            "qty": row.get("qty") if (row.get("qty") not in (None, 0)) else 1.0,
            "unit_price": row.get("unit_price", 0.0) or 0.0,
        })
    return results


def _merge_headerless_continuations(raw_tables):
    """
    Some documents (this is common when a table is split by Word across a
    page break) end up as SEVERAL separate table objects instead of one
    continuous table — only the first fragment keeps the header row
    ('S.No / Items / Quantity / Unit / Unit Price / Amount'); later
    fragments start straight into data rows with no header at all.

    Without a header, the column-mapping logic in _parse_single_table_block
    has nothing to match against and either misassigns columns (mixing up
    qty/price) or silently produces nothing for that fragment — which is
    exactly why items on a later page can go missing entirely.

    This reattaches any header-less fragment (same column count, no
    detectable header of its own) onto the immediately preceding table, so
    the combined grid parses as one continuous table with its original
    header intact.
    """
    if not raw_tables:
        return raw_tables

    merged = [list(raw_tables[0])]

    for table in raw_tables[1:]:
        if not table:
            continue

        cols = len(table[0]) if table[0] else 0
        prev = merged[-1]
        prev_cols = len(prev[0]) if prev and prev[0] else 0

        header_idx, _ = _find_header_row(table)
        if header_idx is None and cols > 0 and abs(cols - prev_cols) <= 2:
            prev.extend(table)
        else:
            merged.append(list(table))

    return merged


def _parse_table(table):
    results = []
    if not table or len(table) < 1:
        return results
    # Split the grid into sub-tables if repeated headers appear mid-stream
    sub_tables = []
    current_sub = []
    for row in table:
        cleaned_row = [_WHITESPACE_RE.sub(" ", str(c or "")).strip() for c in row]
        row_str = " ".join(cleaned_row).lower()
        # Check if this row is a repeated table header (e.g. contains S.No/Sr.No and Items/Description)
        is_header_row = (
            any(kw in row_str for kw in ["s.no", "sr.no", "sl.no", "item", "particulars"]) and
            any(kw in row_str for kw in ["qty", "quantity", "unit price", "amount"])
        )
        if is_header_row and current_sub:
            sub_tables.append(current_sub)
            current_sub = [row] # Start new sub-table with its header
        else:
            current_sub.append(row)
    if current_sub:
        sub_tables.append(current_sub)
    # Parse each isolated table block independently
    for sub_grid in sub_tables:
        results.extend(_parse_single_table_block(sub_grid))
    return results


def _parse_single_table_block(table):
    results = []
    if not table or len(table) < 1:
        return results
    header_idx, header = _find_header_row(table)
    if header_idx is not None:
        desc_col = _find_desc_column(header)
        unit_col = _find_column(header, ["a/u", "au", "unit", "uom", "measure", "pkg", "pack"])
        qty_col = _find_column(header, ["qty", "quantity", "qnty", "req. qty", "required qty"])
        price_col = _find_column(header, ["unit price", "unit rate", "rate", "rates", "price", "cost", "amount"])
        # Part No / stock number, common in defence-procurement schedules
        # (e.g. "BW123.26.0129"). Not a description, but worth surfacing
        # alongside the Nomenclature rather than silently dropping it.
        part_col = _find_column(header, ["part no", "part number", "part#", "p/n", "ref no"])
        start_row = header_idx + 1
    else:
        desc_col, unit_col, qty_col, price_col = _infer_columns_from_data(table)
        part_col = None
        start_row = 0
    pending_desc = ""
    current_annexure = None
    for row in table[start_row:]:
        if not row or all(not str(c or "").strip() for c in row):
            continue
        cleaned_row = [_WHITESPACE_RE.sub(" ", str(c or "")).strip() for c in row]
        row_str = " ".join(cleaned_row).lower()

        # Detect annexure headers
        annex_match = _ANNEXURE_RE.match(row_str)
        if annex_match:
            current_annexure = " ".join(cleaned_row).strip()
            pending_desc = ""
            continue

        if any(term in row_str for term in ["grand total", "subtotal", "summary", "total for"]) and "description" not in row_str and "name" not in row_str:
            continue
        if any(kw in row_str for kw in ["sr.", "sr. no", "unit price", "rates"]) and any(kw in row_str for kw in ["qty", "quantity", "total", "cost"]):
            continue
        description = ""
        if desc_col is not None and desc_col < len(cleaned_row):
            description = cleaned_row[desc_col]
        if desc_col is None and (not description or _is_pure_number_or_sno(description)):
            # Only guess "the longest cell anywhere in the row" when we
            # truly have no known description column. If desc_col IS known
            # but simply happens to be blank on this row, the real content
            # here almost certainly belongs to some OTHER column (e.g. a
            # wrapped Remarks/Delivery-Period value spilling onto its own
            # continuation line) - guessing from any cell would wrongly
            # attach that text to the description instead.
            candidates = [
                cell for cell in cleaned_row
                if cell and not _is_pure_number_or_sno(cell) and len(cell) > 1
            ]
            description = max(candidates, key=len, default="") if candidates else ""
        elif _is_pure_number_or_sno(description):
            description = ""
        first_cell = cleaned_row[0] if cleaned_row else ""
        has_sno = _is_pure_number_or_sno(first_cell) and bool(first_cell)
        qty = None
        if qty_col is not None and qty_col < len(cleaned_row):
            qty = _extract_number(cleaned_row[qty_col])
        price = 0.0
        if price_col is not None and price_col < len(cleaned_row):
            extracted_price = _extract_number(cleaned_row[price_col])
            if extracted_price is not None:
                price = extracted_price
        has_numbers = (qty is not None and qty > 0) or (price > 0)
        part_no = ""
        if part_col is not None and part_col < len(cleaned_row):
            part_no = cleaned_row[part_col].strip()
        unit = "Nos"
        if unit_col is not None and unit_col < len(cleaned_row):
            raw_unit = cleaned_row[unit_col]
            if raw_unit and len(raw_unit) <= 15 and not _extract_number(raw_unit):
                unit = raw_unit
        desc_lower = description.lower()
        if desc_lower in ("description", "item description", "particulars", "items", "name of item", "name", "total", "grand total", "subtotal"):
            continue
        if not has_numbers:
            if description and not _is_pure_number_or_sno(description):
                desc_l = description.lower()
                _SECTION_HEADER_TERMS = (
                    "note:", "notes:", "instruction", "general:", "scope of",
                    "terms and", "condition", "please note", "as per", "refer",
                    "chapter", "section", "clause", "annexure", "annex", "schedule",
                    "heading", "subject:", "title:",
                )
                _is_section_header = (
                    len(description) < 30
                    and any(term in desc_l for term in _SECTION_HEADER_TERMS)
                )
                _is_label_only = (
                    len(description) < 15
                    and not any(c.isdigit() for c in description)
                    and description.isupper()
                )
                if _is_section_header or _is_label_only:
                    pending_desc = ""
                    continue
                if has_sno:
                    pending_desc = description
                elif results:
                    results[-1]["description"] = f"{results[-1]['description']} {description}".strip()[:250]
                else:
                    pending_desc = f"{pending_desc} {description}".strip()
            continue
        if description or pending_desc:
            full_desc = f"{pending_desc} {description}".strip()
            pending_desc = ""
            if description and pending_desc and pending_desc in description:
                full_desc = description
            # Part No stays in its own column - it is a stock/catalogue
            # number, not part of the human-readable nomenclature, and
            # mixing the two makes both harder to use downstream (sorting,
            # matching against a parts catalogue, Excel column widths).
            clean_part_no = part_no if (part_no and not _is_pure_number_or_sno(part_no)) else ""
            if len(full_desc) > 1 and not _is_pure_number_or_sno(full_desc):
                # Confidence scoring: base + bonuses for each quality signal
                confidence = 0.4  # base for having a description
                if len(full_desc) > 10:
                    confidence += 0.1
                if qty is not None and qty > 0:
                    confidence += 0.15
                if price and price > 0:
                    confidence += 0.15
                if clean_part_no:
                    confidence += 0.05
                if unit and unit != "Nos":
                    confidence += 0.05
                if has_sno:
                    confidence += 0.05
                confidence = min(confidence, 1.0)
                item = {
                    "description": full_desc[:250],
                    "part_no": clean_part_no,
                    "unit": unit,
                    "qty": qty if (qty is not None and qty > 0) else 1.0,
                    "unit_price": price,
                    "confidence": round(confidence, 2),
                    "source_page": None,  # filled by caller if available
                    "source_text": row_str[:200] if len(row_str) > 200 else row_str,
                }
                if current_annexure:
                    item["annexure"] = current_annexure
                results.append(item)
    return results


def _find_header_row(table):
    keywords = [
        "desc", "item", "name", "particular", "specification", "qty", "quantity",
        "price", "rate", "rates", "unit", "amount", "cost", "nomenclature",
        "stores", "part no", "part number", "srl.no", "sr no", "sl no", "sl.no",
        "sr.no", "sr.", "s.no", "sn", "item no", "item no.", "particulars",
        "details", "uom", "measure",
    ]
    best_idx = None
    max_matches = 0
    for idx in range(min(30, len(table))):
        row = [str(c or "").strip().lower() for c in table[idx]]
        non_empty = [c for c in row if c]
        # A merged/repeated summary label ("Total for Stationery Items" in
        # most cells of the row, with just the trailing amount differing)
        # can superficially match several keywords at once ("Items"
        # contains "item") but is never a real header - a genuine header
        # row has distinct column names, not one label copied across most
        # of the cells.
        if len(non_empty) >= 2:
            counts = {}
            for c in non_empty:
                counts[c] = counts.get(c, 0) + 1
            if max(counts.values()) > len(non_empty) / 2:
                continue
        match_count = sum(1 for cell in row if cell and any(kw in cell for kw in keywords))
        if match_count > max_matches:
            max_matches = match_count
            best_idx = idx
    if max_matches >= 2:
        return best_idx, [str(c or "").strip().lower() for c in table[best_idx]]
    return None, []


def _infer_columns_from_data(table):
    if not table:
        return None, None, None, None
    num_cols = max(len(r) for r in table)
    col_text_len = [0] * num_cols
    col_unit_matches = [0] * num_cols
    col_numbers_count = [0] * num_cols
    unit_keywords = {"nos", "pcs", "set", "sets", "kg", "kgs", "m", "mtr", "mt", "box", "pack", "pkt", "ea", "each", "roll", "rolls", "ream", "ft", "btl", "can", "ltr", "l", "gm", "g", "ton", "cu", "sq", "pair", "doz", "bag", "drum", "bdle", "unit", "a/u", "au"}
    for row in table:
        for c_idx, cell in enumerate(row):
            if c_idx >= num_cols:
                continue
            val = str(cell or "").strip()
            if not val or len(val) > 100:
                continue
            num = _extract_number(val)
            if num is not None and not _is_pure_number_or_sno(val):
                col_numbers_count[c_idx] += 1
            elif val.lower() in unit_keywords:
                col_unit_matches[c_idx] += 3
            elif not _is_pure_number_or_sno(val):
                col_text_len[c_idx] += len(val)
    desc_col = max(range(num_cols), key=lambda c: col_text_len[c]) if any(col_text_len) else 1
    unit_col = max(range(num_cols), key=lambda c: col_unit_matches[c]) if max(col_unit_matches) > 0 else None
    numeric_cols = [c for c in range(num_cols) if col_numbers_count[c] > 0 and c != desc_col]
    # Heuristic: qty is typically leftmost numeric column, price is rightmost
    qty_col = numeric_cols[0] if len(numeric_cols) > 0 else None
    price_col = numeric_cols[-1] if len(numeric_cols) > 1 else None
    # Refine: if a numeric col header contains price/rate keywords, prefer it as price
    for c in numeric_cols:
        for row in table[:10]:
            if c < len(row):
                val = str(row[c] or "").lower()
                if any(kw in val for kw in ["price", "rate", "cost", "amount"]):
                    price_col = c
                    if qty_col == c and len(numeric_cols) > 1:
                        qty_col = numeric_cols[0] if numeric_cols[0] != c else numeric_cols[1]
                    break
    return desc_col, unit_col, qty_col, price_col


def _find_desc_column(header):
    high_priority = ["description", "particular", "specification", "details", "name of item", "item name", "nomenclature", "stores", "name", "items", "goods", "services"]
    for idx, col in enumerate(header):
        for kw in high_priority:
            if kw in col and not any(sno in col for sno in ["s.no", "sl.no", "sr.no", "sr.", "no."]):
                return idx
    sno_indicators = ["code", "num", "id", "#", "sn", "sr"]
    for idx, col in enumerate(header):
        if "item" in col or "name" in col:
            if not any(ind in col for ind in sno_indicators):
                return idx
    return None


def _find_column(header, keywords):
    for kw in keywords:
        for idx, col_name in enumerate(header):
            if kw in col_name:
                if kw in ["qty", "quantity"] and any(sno in col_name for sno in ["s.no", "sl.no", "sr.no", "item no"]):
                    continue
                return idx
    return None


def _is_pure_number_or_sno(text):
    cleaned = text.strip().rstrip(".")
    if not cleaned:
        return True
    if _PURE_NUMBER_RE.match(cleaned):
        return True
    if _PURE_SNO_RE.match(text):
        return True
    return False


def _extract_number(text):
    if not text:
        return None
    match = _NUMBER_RE.search(text)
    if match:
        cleaned = match.group(1).replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _parse_plain_text(text):
    text = _normalize_text(text)
    results = []
    buffer_lines = []
    current_annexure = None
    for line in text.split("\n"):
        if len(results) >= MAX_ITEMS:
            break
        cleaned = line.strip()
        if not cleaned or len(cleaned) < 2:
            continue

        # Detect annexure headers
        annex_match = _ANNEXURE_RE.match(cleaned)
        if annex_match:
            current_annexure = cleaned.strip()
            buffer_lines.clear()
            continue

        cleaned_lower = cleaned.lower()
        if any(kw in cleaned_lower for kw in _PLAIN_TEXT_IGNORE_KEYWORDS) and not _UNIT_RE.search(cleaned_lower):
            if "total" in cleaned_lower and len(results) > 0:
                buffer_lines.clear()
            continue
        if _is_pure_number_or_sno(cleaned):
            continue
        numbers = _LINE_NUMBERS_RE.findall(cleaned)
        is_item_row = False
        qty = 1.0
        price = 0.0
        unit = "Nos"
        line_desc = ""
        if numbers:
            unit_match = _UNIT_RE.search(cleaned)
            if unit_match:
                unit = unit_match.group(1).capitalize()
            num_floats = []
            for n in numbers:
                try:
                    num_floats.append(float(n.replace(",", "")))
                except ValueError:
                    pass
            if len(num_floats) >= 2:
                is_item_row = True
                if len(num_floats) >= 3 and abs(num_floats[-3] * num_floats[-2] - num_floats[-1]) < 1.0:
                    qty = num_floats[-3]
                    price = num_floats[-2]
                elif len(num_floats) >= 3:
                    qty = num_floats[-3]
                    price = num_floats[-2]
                else:
                    qty = num_floats[0]
                    price = num_floats[1]
                text_only = _UNIT_STRIP_RE.sub("", cleaned)
                text_only = _NUMBER_STRIP_RE.sub("", text_only).strip(" .-:")
                line_desc = text_only
            elif len(num_floats) == 1 and unit_match:
                is_item_row = True
                qty = num_floats[0]
                text_only = _UNIT_STRIP_RE.sub("", cleaned)
                line_desc = text_only.strip(" .-:")
        if is_item_row:
            full_description = " ".join(buffer_lines + [line_desc]).strip()
            buffer_lines.clear()
            full_description = _LEADING_SNO_RE.sub("", full_description)
            full_description = _LEADING_INDEX_RE.sub("", full_description)
            if len(full_description) > 2 and not _is_pure_number_or_sno(full_description):
                confidence = 0.4
                if len(full_description) > 10:
                    confidence += 0.1
                if qty > 0:
                    confidence += 0.15
                if price > 0:
                    confidence += 0.15
                if unit and unit != "Nos":
                    confidence += 0.05
                confidence = min(confidence, 1.0)
                item = {
                    "description": full_description[:250],
                    "part_no": "",
                    "unit": unit,
                    "qty": qty if qty > 0 else 1.0,
                    "unit_price": price,
                    "confidence": round(confidence, 2),
                    "source_page": None,
                    "source_text": cleaned[:200],
                }
                if current_annexure:
                    item["annexure"] = current_annexure
                results.append(item)
        else:
            if not _is_pure_number_or_sno(cleaned):
                buffer_lines.append(cleaned)
    return results