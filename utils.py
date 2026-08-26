import os
from werkzeug.utils import secure_filename


def get_order_folder(app, order):
    """Generates a unique folder path using the order ID and sanitized title."""
    safe_title = secure_filename(order.title) if order.title else "untitled"
    folder_name = f"{order.id}_{safe_title}"

    folder_path = os.path.join(app.root_path, "static", "documents", f"company_{order.company_id}", folder_name)
    os.makedirs(folder_path, exist_ok=True)
    return folder_path

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
ALLOWED_DOC_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
ALLOWED_COMPANY_DOC_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "doc", "docx"}


def _get_extension(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def validate_upload(file_storage, allowed_extensions):
    """Returns True if the uploaded file has an allowed extension, False otherwise."""
    if not file_storage or not file_storage.filename:
        return False
    ext = _get_extension(file_storage.filename)
    return ext in allowed_extensions

from difflib import SequenceMatcher
import re


def _normalize_for_matching(text):
    """Strips punctuation/extra spaces and lowercases, so 'I.O.M Islamabad' and 'IOM Islamabad' compare as near-identical."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fuzzy_similarity(a, b):
    """Returns a 0.0–1.0 similarity score between two strings, tolerant of punctuation/spacing differences."""
    return SequenceMatcher(None, _normalize_for_matching(a), _normalize_for_matching(b)).ratio()


def find_fuzzy_matches(query, candidates, get_text, threshold=0.72, limit=5):
    """
    candidates: list of objects
    get_text: function(obj) -> string to compare against
    Returns list of (obj, score) sorted by score desc, above threshold.
    """
    scored = []
    for obj in candidates:
        score = fuzzy_similarity(query, get_text(obj))
        if score >= threshold:
            scored.append((obj, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]

def delete_file_if_exists(folder, filename=None):
    """If called as `delete_file_if_exists(path)`, deletes that path.
    If called as `delete_file_if_exists(folder, filename)`, joins and deletes.
    Never raises — a locked or missing file shouldn't block the request."""
    if filename is None:
        path = folder
    else:
        if not filename:
            return
        path = os.path.join(folder, filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def parse_float(value, default=0.0):
    """Safely converts form input to a float. Returns `default` (instead of
    raising) for blank, malformed, or non-numeric input, so a stray typo in a
    quantity/price/amount field produces a friendly validation message instead
    of an unhandled 500 error."""
    if value is None:
        return default
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return default