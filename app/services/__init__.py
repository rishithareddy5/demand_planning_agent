import re
from typing import Dict, List, Optional


class ReplyParserService:
    """
    Parses distributor reply email text and extracts:

    - distributor_id
    - product_name
    - quantity

    Expected reply format:

    Product Name - Quantity

    Example:
    MALKIST CHEESE JUMBO PACK - 100
    BENG BENG WAFER CHOCOLATE - 50
    """

    def execute(self, reply_text: str) -> Dict:
        if not reply_text or not reply_text.strip():
            return {
                "distributor_id": None,
                "items": [],
                "parse_status": "FAILED"
            }

        cleaned_text = reply_text.strip()

        distributor_id = self._extract_distributor_id(cleaned_text)
        items = self._extract_product_lines(cleaned_text)

        parse_status = "PARSED" if items else "FAILED"

        return {
            "distributor_id": distributor_id,
            "items": items,
            "parse_status": parse_status
        }

    def _extract_distributor_id(self, text: str) -> Optional[str]:
        match = re.search(r"\bD\d{2}\b", text, re.IGNORECASE)
        if match:
            return match.group(0).upper()
        return None

    def _extract_product_lines(self, text: str) -> List[Dict]:
        items = []

        for line in text.splitlines():
            line = line.strip()

            if not line:
                continue

            # Match: Product Name - 100
            if len(line) > 100:
                continue

            match = re.match(r"^([^-]+)\s*-\s*(\d+)$", line) ## sonar changes for secr hotsp #1
            if match:
                product_name = match.group(1).strip()
                quantity = int(match.group(2))

                items.append({
                    "product_name": product_name,
                    "quantity": quantity
                }) 

        return items