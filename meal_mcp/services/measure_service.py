import re
from fractions import Fraction

UNIT_TO_GRAMS = {
    "g": 1.0, "gram": 1.0, "grams": 1.0,
    "kg": 1000.0, "kilogram": 1000.0, "kilograms": 1000.0,
    "mg": 0.001,
    "oz": 28.3495, "ounce": 28.3495, "ounces": 28.3495,
    "lb": 453.592, "pound": 453.592, "pounds": 453.592,
    "ml": 1.0, "milliliter": 1.0, "milliliters": 1.0,
    "l": 1000.0, "liter": 1000.0, "liters": 1000.0,
    "tsp": 5.0, "teaspoon": 5.0, "teaspoons": 5.0,
    "tbsp": 15.0, "tablespoon": 15.0, "tablespoons": 15.0,
    "cup": 240.0, "cups": 240.0,
}

UNICODE_FRACTIONS = {
    "½": 0.5, "⅓": 1/3, "⅔": 2/3, "¼": 0.25, "¾": 0.75, "⅛": 0.125,
}


def normalize_ingredient_name(name: str) -> str:
    return " ".join(name.strip().lower().replace("_", " ").split())


def _parse_number(text: str) -> float | None:
    text = text.strip()
    for char, value in UNICODE_FRACTIONS.items():
        if char in text:
            whole = text.replace(char, "").strip()
            return (float(whole) if whole else 0.0) + value
    parts = text.split()
    try:
        if len(parts) == 2 and "/" in parts[1]:
            return float(parts[0]) + float(Fraction(parts[1]))
        if "/" in text:
            return float(Fraction(text))
        return float(text.replace(",", "."))
    except (ValueError, ZeroDivisionError):
        return None


def estimate_grams(measure: str) -> float | None:
    if not measure or not measure.strip():
        return None
    # Drop abbreviation dots ("tsp.") but keep decimal points ("1.2 kg").
    clean = re.sub(r"\.(?!\d)|(?<!\d)\.", " ", measure.lower()).strip()
    match = re.search(r"(\d+(?:[.,]\d+)?(?:\s+\d+/\d+)?|\d+/\d+|\d*[½⅓⅔¼¾⅛])\s*([a-z]+)", clean)
    if not match:
        return None
    amount = _parse_number(match.group(1))
    factor = UNIT_TO_GRAMS.get(match.group(2))
    if amount is None or factor is None:
        return None
    return round(amount * factor, 4)


MASS_UNITS = {"g", "gram", "grams", "kg", "kilogram", "kilograms", "mg", "oz", "ounce", "ounces", "lb", "pound", "pounds"}

# Spoon and cup spellings -> the form USDA portions use.
UNIT_ALIASES = {
    "teaspoon": "tsp", "teaspoons": "tsp",
    "tablespoon": "tbsp", "tablespoons": "tbsp", "tbs": "tbsp", "tbl": "tbsp", "tbls": "tbsp",
    "cups": "cup",
}
VOLUME_UNITS = {"tsp", "tbsp", "cup", "ml", "l"}
SPOONS_IN_TSP = {"tsp": 1, "tbsp": 3, "cup": 48}
# Cut pieces hold air; their cup weight says little about a spoon of paste or powder.
CUT_WORDS = {"slice", "slices", "sliced", "chopped", "diced", "grated", "minced", "shredded", "pieces", "strips"}

# Portions that are not a single piece of the food.
NON_PIECE_WORDS = {
    "tsp", "tbsp", "cup", "fl", "oz", "lb", "g", "ml", "slice", "slices", "ring", "rings", "quantity",
    "specified", "serving", "pinch", "dash", "chopped", "diced", "sliced", "cherry", "nlea", "package",
}
SIZE_WORDS = ("medium", "large", "small")


def _words(text: str) -> list[str]:
    return [UNIT_ALIASES.get(word, word) for word in re.findall(r"[a-z]+", text.lower())]


def _singular(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def parse_amount(measure: str) -> tuple[float, str] | None:
    """Leading amount and the rest of a measure: "8 cloves chopped" -> (8.0, "cloves chopped")."""
    clean = re.sub(r"\.(?!\d)|(?<!\d)\.", " ", (measure or "").lower()).strip()
    match = re.match(r"(\d+(?:[.,]\d+)?(?:\s+\d+/\d+)?|\d+/\d+|\d*[½⅓⅔¼¾⅛])\s*(.*)", clean)
    if not match:
        return None
    amount = _parse_number(match.group(1))
    return None if amount is None else (amount, match.group(2).strip())


def is_mass_measure(measure: str) -> bool:
    parsed = parse_amount(measure)
    return bool(parsed and parsed[1] and parsed[1].split()[0] in MASS_UNITS)


def normalize_portions(food_portions: list[dict]) -> list[dict]:
    """USDA foodPortions -> [{"unit": "medium whole", "grams": 123.0}], grams per one unit.

    SR Legacy and Foundation give amount + modifier/measureUnit, FNDDS a portionDescription ("1 clove").
    """
    portions = []
    for portion in food_portions or []:
        grams = portion.get("gramWeight")
        description = portion.get("portionDescription")
        if description:
            parsed = parse_amount(description)
            amount, unit = parsed if parsed else (1.0, description.lower())
        else:
            amount = portion.get("amount") or 1.0
            unit_name = (portion.get("measureUnit") or {}).get("name") or ""
            unit = str(portion.get("modifier") or ("" if unit_name == "undetermined" else unit_name)).lower()
        if not grams or not amount or not unit:
            continue
        portions.append({"unit": unit, "grams": round(float(grams) / float(amount), 3)})
    return portions


def grams_from_portions(measure: str, portions: list[dict]) -> tuple[float, str] | None:
    """Grams for piece and spoon measures ("5", "8 cloves", "1 tsp") from USDA portion weights.

    Returns (grams, basis) or None when the measure is a mass or no portion fits.
    """
    parsed = parse_amount(measure)
    if parsed is None or not portions:
        return None
    amount, rest = parsed
    rest_words = _words(rest)
    unit = rest_words[0] if rest_words else ""
    if unit in MASS_UNITS:
        return None

    def basis(portion: dict) -> tuple[float, str]:
        return round(amount * portion["grams"], 1), f"USDA portion: 1 {portion['unit']} = {portion['grams']:g} g"

    if unit in VOLUME_UNITS:
        for portion in portions:
            if unit in _words(portion["unit"]):
                return basis(portion)
        # Only "1 tsp" known for "1 tbsp": 1 tbsp = 3 tsp, 1 cup = 48 tsp.
        if unit in SPOONS_IN_TSP:
            for portion in portions:
                words = _words(portion["unit"])
                known = [word for word in words if word in SPOONS_IN_TSP]
                if known and not set(words) & CUT_WORDS:
                    grams = portion["grams"] * SPOONS_IN_TSP[unit] / SPOONS_IN_TSP[known[0]]
                    return round(amount * grams, 1), f"USDA portion: 1 {portion['unit']} = {portion['grams']:g} g, scaled to {unit}"
        return None

    pieces = [portion for portion in portions if not set(_words(portion["unit"])) & NON_PIECE_WORDS]
    # "8 cloves" -> portion "clove"; "2 large" -> portion "large whole".
    for word in rest_words:
        for portion in pieces:
            if _singular(word) in {_singular(item) for item in _words(portion["unit"])}:
                return basis(portion)
    for size in ("medium", "whole"):
        for portion in pieces:
            if size in _words(portion["unit"]) and not set(_words(portion["unit"])) & {"large", "small"} - {size}:
                return basis(portion)
    return basis(pieces[0]) if pieces else None


VOLUME_BASIS = "volume, approx. 1 g/ml"


def ingredient_grams(measure: str, estimated_grams: float | None, portions: list[dict] | None) -> tuple[float | None, str | None]:
    """Grams of an ingredient and how they were derived: measured mass, USDA portion, or approx. 1 g/ml."""
    if is_mass_measure(measure):
        return estimated_grams, "measured"
    portion = grams_from_portions(measure, portions) if portions else None
    if portion:
        return portion
    if estimated_grams is not None:
        return estimated_grams, VOLUME_BASIS
    return None, None


def measure_kind(measure: str) -> str:
    """"mass", "volume", "piece" (a count, "8 cloves") or "unknown" ("To taste")."""
    parsed = parse_amount(measure)
    if parsed is None:
        return "unknown"
    words = _words(parsed[1])
    unit = words[0] if words else ""
    if unit in MASS_UNITS:
        return "mass"
    if unit in VOLUME_UNITS or unit in UNIT_TO_GRAMS:
        return "volume"
    return "piece"


def format_amount(value: float) -> str:
    return f"{round(value, 2):g}"


def scale_measure(measure: str, factor: float) -> str:
    """Multiply the leading amount and keep the unit: ("200 ml", 0.5) -> "100 ml"."""
    parsed = parse_amount(measure)
    if parsed is None or factor == 1:
        return measure
    amount, rest = parsed
    value = amount * factor
    if rest.split()[:1] == ["kg"] and value < 1:
        return f"{format_amount(value * 1000)} g{rest[2:]}"
    return f"{format_amount(value)} {rest}".strip()
