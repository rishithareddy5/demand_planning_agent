import re
from typing import Any, Dict, List, Optional, Tuple

from rapidfuzz import process, fuzz
from app.data.distributor_data import get_distributor_map
from app.data.sku_data import get_sku_map, get_sku_names, get_sku_id_to_name


def clean_email_body(body: str) -> str:
    if not body:
        return ""

    text = body.replace("\r", "\n")

    stop_patterns = [
        r"^on .+ wrote:$",
        r"^from:.*$",
        r"^subject:.*$",
        r"^sent:.*$",
        r"^to:.*$",
        r"^cc:.*$",
        r"^-+original message-+$",
    ]

    cleaned_lines = []

    for line in text.split("\n"):
        stripped = line.strip()

        if not stripped:
            cleaned_lines.append("")
            continue

        if stripped.startswith(">"):
            continue

        should_break = False
        for pattern in stop_patterns:
            if re.match(pattern, stripped, flags=re.IGNORECASE):
                should_break = True
                break

        if should_break:
            break

        cleaned_lines.append(stripped)

    text = "\n".join(cleaned_lines)
    text = text.replace(":", " - ").replace("=", " - ").replace("\t", " ")
    text = re.sub(r"\{2,}", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def split_reply_into_lines(body: str) -> List[str]:
    """
    Split WhatsApp/email messages into separate demand lines
    """

    if not body:
        return []

    normalized = body.replace(";", "\n").replace("|", "\n")

    lines: List[str] = []

    for raw_line in normalized.splitlines():

        cleaned = raw_line.strip()

        if cleaned:
            lines.append(cleaned)

    return lines


def get_distributor_id(from_email: str, body: str) -> str:
    distributor_map = get_distributor_map()
    normalized_email = (from_email or "").strip().lower()

    if normalized_email in distributor_map:
        return distributor_map[normalized_email]

    match = re.search(r"\b(d\d{2})\b", body.lower())
    if match:
        return match.group(1).upper()

    return "UNKNOWN"


def classify_reply(body: str) -> str:
    text = (body or "").lower()

    informational_keywords = [
        "will send",
        "send later",
        "send soon",
        "i will share",
        "will update",
        "later",
        "soon",
        "i will send it soon",
        "i will send later",
    ]

    reference_keywords = [
        "same as last month",
        "same as previous",
        "same as last",
        "repeat last month",
    ]

    negative_keywords = [
        "no demand",
        "not required",
        "no requirement",
        "not needed",
        "nil",
        "zero",
        "nothing required",
    ]

    if any(keyword in text for keyword in informational_keywords):
        return "informational"

    if any(keyword in text for keyword in reference_keywords):
        return "reference"

    if any(keyword in text for keyword in negative_keywords):
        return "negative"

    if any(char.isdigit() for char in text):
        return "demand"

    return "ambiguous"


UNIT_PATTERNS = [
    "pieces", "piece", "pcs", "pc",
    "boxes", "box", "cartons", "carton",
    "cases", "case", "units", "unit",
    "packs", "pack"
]


def strip_list_numbering(text: str) -> str:
    """
    Removes leading list numbering like:
    1. Product - 100
    2) Product - 200
    3 Product - 300
    """
    if not text:
        return ""

    text = text.strip()
    text = re.sub(r"^\d+\s*[\.\)]\s*", "", text)
    return text.strip()


def extract_quantity_and_unit(text: str) -> Tuple[Optional[int], Optional[str]]:
    if not text:
        return None, None

    cleaned = strip_list_numbering(text)

    # find all numbers, take the LAST one as quantity
    numbers = re.findall(r"\d+", cleaned)
    if not numbers:
        return None, None

    quantity = int(numbers[-1])

    unit_match = re.search(
        r"\b(" + "|".join(UNIT_PATTERNS) + r")\b",
        cleaned.lower()
    )
    unit = unit_match.group(1).lower() if unit_match else None

    return quantity, unit


def normalize_product_text(text: str) -> str:
    return " ".join((text or "").lower().strip().split())


def remove_quantity_words(text: str) -> str:
    removable_words = [
        "pieces", "piece", "pcs", "pc",
        "boxes", "box", "cartons", "carton",
        "cases", "case", "units", "unit",
        "packs", "pack", "need", "required",
        "qty", "quantity", "-", "of"
    ]

    cleaned = strip_list_numbering(text)
    cleaned = normalize_product_text(cleaned)

    for word in removable_words:
        cleaned = cleaned.replace(word, " ")

    # remove all numeric tokens
    cleaned = " ".join(token for token in cleaned.split() if not token.isdigit())
    return " ".join(cleaned.split())


def match_sku(text: str, min_score: int = 75) -> Tuple[Optional[str], Optional[str], int]:
    sku_map = get_sku_map()
    sku_names = get_sku_names()
    sku_id_to_name = get_sku_id_to_name()

    cleaned_for_match = strip_list_numbering(text)
    normalized_text = normalize_product_text(cleaned_for_match)

    sku_code_match = re.search(r"\bsku\d{1,3}\b", normalized_text)
    if sku_code_match:
        sku_code = sku_code_match.group(0).upper()
        if sku_code in sku_id_to_name:
            return sku_code, sku_id_to_name[sku_code], 100
        return sku_code, None, 100

    cleaned_text = remove_quantity_words(cleaned_for_match)
    if not cleaned_text or not sku_names:
        return None, None, 0

    best_match = process.extractOne(
    cleaned_text,
    sku_names,
    scorer=fuzz.partial_ratio
)
    if not best_match:
        return None, None, 0

    matched_name, score, _ = best_match

    if score < min_score:
        return None, None, score

    matched_value = sku_map.get(matched_name)

    if isinstance(matched_value, str):
        return matched_value, matched_name, score

    if isinstance(matched_value, dict):
        return (
            matched_value.get("sku_id"),
            matched_value.get("sku_name") or matched_name,
            score
        )

    return None, matched_name, score


def parse_demand_lines(lines: List[str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []

    for line in lines:

        quantity, unit = extract_quantity_and_unit(line)

        if quantity is None:
            continue

        sku_id, sku_name, match_score = match_sku(line)

        # Fallback name extraction
        if not sku_name:
            cleaned_name = remove_quantity_words(line)
            sku_name = cleaned_name.title()

        # STILL append even without sku_id
        items.append({
            "sku_id": sku_id,
            "sku_name": sku_name,
            "quantity": quantity,
            "unit": unit,
            "matched_text": line.strip(),
            "match_score": match_score,
            "source": "email_body",
            "sheet_name": None,
        })

    return items


def calculate_confidence(
    distributor_id: str,
    matched_items: List[Dict[str, Any]],
    reply_type: str
) -> float:

    if reply_type != "demand":
        return _non_demand_confidence(distributor_id)

    if not matched_items:
        return _empty_items_confidence(distributor_id)

    total_score = 0.0

    for item in matched_items:
        score = _calculate_item_score(item, distributor_id)
        total_score += min(score, 1.0)

    return round(total_score / len(matched_items), 2)

def _non_demand_confidence(distributor_id):
    return 0.9 if distributor_id != "UNKNOWN" else 0.6

def _empty_items_confidence(distributor_id):
    return 0.2 if distributor_id != "UNKNOWN" else 0.1


def _calculate_item_score(item, distributor_id):
    score = 0.0

    if distributor_id != "UNKNOWN":
        score += 0.20

    if item.get("sku_id"):
        score += 0.35

    if item.get("quantity") is not None:
        score += 0.25

    score += _fuzzy_score_bonus(item.get("match_score", 0))

    return score

def _fuzzy_score_bonus(fuzz_score):
    if fuzz_score >= 90:
        return 0.20
    elif fuzz_score >= 80:
        return 0.15
    elif fuzz_score >= 75:
        return 0.10
    return 0.0


def aggregate_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    aggregated: Dict[str, Dict[str, Any]] = {}

    for item in items:
        sku_id = item["sku_id"]

        if sku_id not in aggregated:
            aggregated[sku_id] = item.copy()
        else:
            aggregated[sku_id]["quantity"] += item["quantity"]

    return list(aggregated.values())


def parse_reply(from_email: str, body: str) -> Dict[str, Any]:
    raw_body = body or ""
    cleaned_body = clean_email_body(raw_body)

    distributor_id = get_distributor_id(from_email, cleaned_body)
    reply_type = classify_reply(cleaned_body)

    result: Dict[str, Any] = {
        "distributor_id": distributor_id,
        "from_email": from_email,
        "reply_type": reply_type,
        "confidence": 0.0,
        "items": [],
        "notes": None,
        "needs_followup": False,
        "raw_body": raw_body,
        "cleaned_body": cleaned_body,
    }

    if reply_type == "informational":
        result["notes"] = "Distributor said they will send details later."
        result["needs_followup"] = True
        result["confidence"] = calculate_confidence(distributor_id, [], reply_type)
        return result

    if reply_type == "reference":
        result["notes"] = "Distributor referred to previous month or previous order."
        result["needs_followup"] = True
        result["confidence"] = calculate_confidence(distributor_id, [], reply_type)
        return result

    if reply_type == "negative":
        result["notes"] = "Distributor indicated no requirement."
        result["needs_followup"] = False
        result["confidence"] = calculate_confidence(distributor_id, [], reply_type)
        return result

    if reply_type == "ambiguous":
        result["notes"] = "Could not determine whether the reply contains demand details."
        result["needs_followup"] = True
        result["confidence"] = calculate_confidence(distributor_id, [], reply_type)
        return result

    lines = split_reply_into_lines(cleaned_body)
    parsed_items = parse_demand_lines(lines)

    if not parsed_items:
        parsed_items = parse_demand_lines([cleaned_body])

    if not parsed_items:
        result["confidence"] = calculate_confidence(distributor_id, [], reply_type)
        result["notes"] = "Demand-like reply detected, but SKU/quantity could not be confidently extracted."
        result["needs_followup"] = True
        return result

    parsed_items = aggregate_items(parsed_items)

    result["items"] = parsed_items
    result["confidence"] = calculate_confidence(distributor_id, parsed_items, reply_type)
    result["needs_followup"] = result["confidence"] < 0.75

    if result["needs_followup"]:
        result["notes"] = "Parsed with low confidence. Review or follow up recommended."

    return result