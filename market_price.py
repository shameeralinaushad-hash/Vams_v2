import re
import statistics
import requests
from collections import defaultdict

# Flexible number matcher
NUM = r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?'

# Currency symbol mapping for UI/Display
CURRENCY_SYMBOLS = {
    "PKR": "Rs. ",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
}

# Supported currency patterns with realistic price boundaries
PATTERNS = [
    # (regex_pattern, currency_code, min_value, max_value)
    (re.compile(rf'(?:Rs\.?|PKR|₨)\s*({NUM})', re.IGNORECASE), "PKR", 50, 50_000_000),
    (re.compile(rf'({NUM})\s*(?:Rs\.?|PKR|₨|Rupees)', re.IGNORECASE), "PKR", 50, 50_000_000),
    (re.compile(rf'\$\s*({NUM})'), "USD", 0.5, 100_000),
    (re.compile(rf'({NUM})\s*(?:USD|usd)', re.IGNORECASE), "USD", 0.5, 100_000),
    (re.compile(rf'€\s*({NUM})'), "EUR", 0.5, 100_000),
    (re.compile(rf'({NUM})\s*(?:EUR|eur)', re.IGNORECASE), "EUR", 0.5, 100_000),
    (re.compile(rf'£\s*({NUM})'), "GBP", 0.5, 100_000),
    (re.compile(rf'({NUM})\s*(?:GBP|gbp)', re.IGNORECASE), "GBP", 0.5, 100_000),
]


def format_price(value, currency):
    """
    Formats numeric prices into human-readable strings with currency symbols.
    e.g., 45000.0, "PKR" -> "Rs. 45,000"
    e.g., 299.99, "USD"  -> "$299.99"
    """
    if value is None or not currency:
        return "N/A"

    symbol = CURRENCY_SYMBOLS.get(currency, f"{currency} ")
    formatted_num = f"{value:,.2f}" if value % 1 != 0 else f"{int(value):,}"
    return f"{symbol}{formatted_num}"


def extract_prices_from_text(text):
    """
    Extracts price mentions and tags them with currency symbol and formatted string.
    """
    if not text:
        return []

    candidates = []  # (start, end, value, currency)
    for pattern, curr_code, min_val, max_val in PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(1).replace(",", "")
            try:
                val = float(raw)
            except ValueError:
                continue
            if min_val <= val <= max_val:
                candidates.append((match.start(1), match.end(1), val, curr_code))

    # Deduplicate overlapping spans
    candidates.sort(key=lambda c: c[0])
    accepted = []
    last_end = -1
    for start, end, val, curr in candidates:
        if start >= last_end:
            accepted.append({
                "value": val,
                "currency": curr,
                "formatted": format_price(val, curr)
            })
            last_end = end

    return accepted


def summarize_prices(price_list):
    """Aggregates prices into a suggested median figure."""
    if not price_list:
        return None, []

    if len(price_list) >= 4:
        sorted_prices = sorted(price_list)
        trim = max(1, len(sorted_prices) // 10)
        trimmed = sorted_prices[trim:-trim] if len(sorted_prices) > trim * 2 else sorted_prices
    else:
        trimmed = price_list

    suggested = statistics.median(trimmed)
    return round(suggested, 2), trimmed


def tavily_search(query, api_key, num_results=10):
    """Calls Tavily search API."""
    resp = requests.post(
        "https://api.tavily.com/search",
        headers={"Content-Type": "application/json"},
        json={
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": num_results,
        },
        timeout=8,
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        {"title": r.get("title"), "snippet": r.get("content"), "link": r.get("url")}
        for r in data.get("results", [])
    ]


def check_market_price(item_description, api_key):
    """
    Full Search Pipeline.
    Returns formatted strings with currency symbols for UI rendering.
    """
    if not api_key:
        return {
            "suggested_price": None,
            "currency": None,
            "formatted_suggested_price": "N/A",
            "num_data_points": 0,
            "sources": [],
            "error": "Tavily isn't configured yet (missing API key).",
        }

    query = f"{item_description} price"
    try:
        results = tavily_search(query, api_key)
    except requests.exceptions.RequestException as e:
        return {
            "suggested_price": None,
            "currency": None,
            "formatted_suggested_price": "N/A",
            "num_data_points": 0,
            "sources": [],
            "error": f"Search failed: {e}",
        }

    sources = []
    prices_by_currency = defaultdict(list)

    for r in results:
        text = f"{r.get('title', '')} {r.get('snippet', '')}"
        extracted = extract_prices_from_text(text)

        for item in extracted:
            prices_by_currency[item["currency"]].append(item["value"])

        sources.append({
            "title": r.get("title"),
            "snippet": r.get("snippet"),
            "link": r.get("link"),
            "extracted_prices": extracted,  # Contains {"value": ..., "currency": ..., "formatted": "Rs. 45,000"}
        })

    # Selection Hierarchy: PKR -> USD -> EUR -> GBP -> Any other found
    if "PKR" in prices_by_currency:
        selected_currency = "PKR"
    elif "USD" in prices_by_currency:
        selected_currency = "USD"
    elif prices_by_currency:
        selected_currency = max(prices_by_currency.keys(), key=lambda c: len(prices_by_currency[c]))
    else:
        selected_currency = None

    if selected_currency:
        suggested, used_prices = summarize_prices(prices_by_currency[selected_currency])
    else:
        suggested, used_prices = None, []

    return {
        "suggested_price": suggested,
        "currency": selected_currency,
        "formatted_suggested_price": format_price(suggested, selected_currency),
        "num_data_points": len(used_prices),
        "sources": sources,
        "error": None,
    }