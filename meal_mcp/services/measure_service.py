import re
from fractions import Fraction

UNIT_TO_GRAMS = {
    "g": 1.0, "gram": 1.0, "grams": 1.0,
    "kg": 1000.0, "kilogram": 1000.0, "kilograms": 1000.0,
    "mg": 0.001,
    "oz": 28.3495, "ounce": 28.3495, "ounces": 28.3495,
    "lb": 453.592, "lbs": 453.592, "pound": 453.592, "pounds": 453.592,
    "ml": 1.0, "milliliter": 1.0, "milliliters": 1.0, "millilitre": 1.0, "millilitres": 1.0,
    "l": 1000.0, "liter": 1000.0, "liters": 1000.0, "litre": 1000.0, "litres": 1000.0,
    "tsp": 5.0, "teaspoon": 5.0, "teaspoons": 5.0,
    "tbsp": 15.0, "tbs": 15.0, "tbl": 15.0, "tbls": 15.0, "tblsp": 15.0, "tablespoon": 15.0, "tablespoons": 15.0,
    "cup": 240.0, "cups": 240.0,
}

UNICODE_FRACTIONS = {
    "½": 0.5, "⅓": 1/3, "⅔": 2/3, "¼": 0.25, "¾": 0.75, "⅛": 0.125,
}


def normalize_ingredient_name(name: str) -> str:
    return " ".join(name.strip().lower().replace("_", " ").split())


# Longest forms first, otherwise "1/4" is read as 1: "2-1/2", "1 1/2", "1/4", "1½", "½", "2-3", "1.5".
AMOUNT = (
    r"\d+(?:\s+|\s*-\s*)\d+/\d+|\d+/\d+|\d*\s*[½⅓⅔¼¾⅛]|\d+\s*-\s*\d+(?![\d/])|\d+(?:[.,]\d+)?"
)
# "2 x 400g" and "2 x 400 g" are one total amount.
MULTIPLIED = re.compile(r"^(\d+)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*")


def _clean_measure(measure: str) -> str:
    """Lower case, without abbreviation dots ("tsp."), keeping decimal points ("1.2 kg"), multiplied out."""
    clean = re.sub(r"\.(?!\d)|(?<!\d)\.", " ", (measure or "").lower()).strip()
    multiplied = MULTIPLIED.match(clean)
    if multiplied:
        total = float(multiplied.group(1)) * float(multiplied.group(2).replace(",", "."))
        clean = f"{total:g} {clean[multiplied.end():]}".strip()
    return clean


def _parse_number(text: str) -> float | None:
    text = text.strip()
    if re.fullmatch(r"\d+\s*-\s*\d+/\d+", text):
        text = text.replace("-", " ")
    range_match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", text)
    if range_match:
        return (float(range_match.group(1)) + float(range_match.group(2))) / 2
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


def bracket_mass(measure: str) -> float | None:
    """Grams of a mass in brackets, the total of the line: "3 rashers (100g) chopped" -> 100."""
    match = re.search(rf"\(\s*({AMOUNT})\s*([a-z]+)\s*\)", _clean_measure(measure))
    if not match or match.group(2) not in MASS_UNITS:
        return None
    amount = _parse_number(match.group(1))
    return None if amount is None else round(amount * UNIT_TO_GRAMS[match.group(2)], 4)


def estimate_grams(measure: str) -> float | None:
    if not measure or not measure.strip():
        return None
    bracket = bracket_mass(measure)
    if bracket is not None:
        return bracket
    match = re.search(rf"({AMOUNT})\s*([a-z]+)", _clean_measure(measure))
    if not match:
        return None
    amount = _parse_number(match.group(1))
    factor = UNIT_TO_GRAMS.get(match.group(2))
    if amount is None or factor is None:
        return None
    return round(amount * factor, 4)


MASS_UNITS = {"g", "gram", "grams", "kg", "kilogram", "kilograms", "mg", "oz", "ounce", "ounces", "lb", "lbs", "pound", "pounds"}

# Spoon and cup spellings -> the form USDA portions use.
UNIT_ALIASES = {
    "teaspoon": "tsp", "teaspoons": "tsp",
    "tablespoon": "tbsp", "tablespoons": "tbsp", "tbs": "tbsp", "tbl": "tbsp", "tbls": "tbsp", "tblsp": "tbsp",
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
    # RACC is a labelling reference amount and "guideline amount per item" no piece of the food.
    "racc", "guideline",
}
# A count of containers says nothing about a piece of the food: "1 Packet" filo is not 1 sheet.
CONTAINER_WORDS = {
    "can", "tin", "packet", "pack", "package", "bag", "jar", "bottle", "box", "carton", "tub", "sachet",
    "bunch", "handful", "head",
}
SIZE_WORDS = ("medium", "large", "small")
# Portions that are only part of a piece; a bare count means whole pieces.
PART_WORDS = {"strip", "leaf", "cube", "wedge", "segment", "floret", "slice"}


def _words(text: str) -> list[str]:
    return [UNIT_ALIASES.get(word, word) for word in re.findall(r"[a-z]+", text.lower())]


def _singular(word: str) -> str:
    if word in IRREGULAR_SINGULARS:
        return IRREGULAR_SINGULARS[word]
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


IRREGULAR_SINGULARS = {"leaves": "leaf", "halves": "half", "loaves": "loaf"}


def parse_amount(measure: str) -> tuple[float, str] | None:
    """Leading amount and the rest of a measure: "8 cloves chopped" -> (8.0, "cloves chopped")."""
    match = re.match(rf"({AMOUNT})\s*(.*)", _clean_measure(measure))
    if not match:
        return None
    amount = _parse_number(match.group(1))
    return None if amount is None else (amount, match.group(2).strip())


def is_mass_measure(measure: str) -> bool:
    if bracket_mass(measure or "") is not None:
        return True
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
        return round(amount * portion["grams"], 1), f"USDA portion: 1 {short_unit(portion)} = {portion['grams']:g} g"

    if unit in VOLUME_UNITS:
        # A recipe's "cup" of cream is liquid, not "cup, whipped" at half the weight.
        portions = [portion for portion in portions if "whipped" not in _words(portion["unit"]) or "fluid" in _words(portion["unit"])]
        matching = [portion for portion in portions if unit in _words(portion["unit"])]
        for portion in sorted(matching, key=lambda portion: _words(portion["unit"]) != [unit]):
            return basis(portion)
        # Only "1 tsp" known for "1 tbsp": 1 tbsp = 3 tsp, 1 cup = 48 tsp.
        if unit in SPOONS_IN_TSP:
            for portion in portions:
                words = _words(portion["unit"])
                known = [word for word in words if word in SPOONS_IN_TSP]
                if known and not set(words) & CUT_WORDS:
                    grams = portion["grams"] * SPOONS_IN_TSP[unit] / SPOONS_IN_TSP[known[0]]
                    return round(amount * grams, 1), f"USDA portion: 1 {short_unit(portion)} = {portion['grams']:g} g, scaled to {unit}"
        return None

    pieces = [portion for portion in portions if not set(_portion_words(portion)) & NON_PIECE_WORDS]
    # "8 cloves" -> portion "clove"; "2 large" -> portion "large whole", not "extra large".
    for word in rest_words:
        named = [portion for portion in pieces if _singular(word) in {_singular(item) for item in _portion_words(portion)}]
        named = [portion for portion in named if "extra" not in _portion_words(portion)] or named
        if named:
            return basis(min(named, key=lambda portion: len(_portion_words(portion))))
    if {_singular(word) for word in rest_words} & CONTAINER_WORDS:
        return None
    for size in ("medium", "whole"):
        for portion in pieces:
            if size in _portion_words(portion) and not set(_portion_words(portion)) & {"large", "small"} - {size}:
                return basis(portion)
    # "2" yellow peppers are two peppers, not two strips.
    whole = [portion for portion in pieces if not {_singular(word) for word in _portion_words(portion)} & PART_WORDS]
    return basis((whole or pieces)[0]) if pieces else None


def short_unit(portion: dict) -> str:
    """Portion unit without its note in brackets: "medium (2-1/2" dia)" -> "medium"."""
    return re.sub(r"\s*\([^)]*\)", "", portion["unit"]).strip() or portion["unit"]


def _portion_words(portion: dict) -> list[str]:
    """Words of a USDA portion without its note: "eggplant, unpeeled (approx 1-1/4 lb)" has no unit "lb"."""
    return _words(re.sub(r"\([^)]*\)", " ", portion["unit"]))


VOLUME_BASIS = "volume, approx. 1 g/ml"
DENSITY_BASIS = "volume, typical density"
SMALL_AMOUNT_BASIS = "small amount, typical weight"
# Amounts without a number: grams of a typical pinch or dash.
SMALL_AMOUNTS = {"pinch": 0.4, "dash": 0.6}
# g/ml of dry foods; 1 g/ml would count a cup of flour as 240 g instead of 125 g.
DRY_DENSITIES = {
    "flour": 0.52, "rice": 0.77, "sugars": 0.83, "cornmeal": 0.6, "peanuts": 0.61, "nuts": 0.6, "oats": 0.34,
    "coconut": 0.35, "crumbs": 0.45, "lentils": 0.8, "couscous": 0.72, "cocoa": 0.36, "seeds": 0.6,
}


def dry_density(food_name: str | None) -> float | None:
    """Density of a dry food by the first word of its USDA description that has one. Oils and milks stay at 1."""
    words = re.findall(r"[a-z]+", (food_name or "").lower())
    if {"oil", "milk", "cream", "juice"} & set(words):
        return None
    return next((DRY_DENSITIES[word] for word in words if word in DRY_DENSITIES), None)


def ingredient_grams(
    measure: str, estimated_grams: float | None, portions: list[dict] | None, food_name: str | None = None,
) -> tuple[float | None, str | None]:
    """Grams of an ingredient and how they were derived: measured mass, USDA portion, or estimated volume."""
    small = SMALL_AMOUNTS.get((measure or "").strip().lower())
    if small is not None:
        return small, SMALL_AMOUNT_BASIS
    if is_mass_measure(measure):
        return estimated_grams, "measured"
    portion = grams_from_portions(measure, portions) if portions else None
    if portion:
        return portion
    if estimated_grams is not None:
        density = dry_density(food_name)
        if density:
            return round(estimated_grams * density, 1), DENSITY_BASIS
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
    # "2 (460g)" x 1.5 -> "3 (690 g)": the bracket is the total of the line.
    rest = re.sub(
        rf"\(\s*({AMOUNT})\s*([a-z]+)\s*\)",
        lambda match: f"({format_amount(_parse_number(match.group(1)) * factor)} {match.group(2)})"
        if match.group(2) in MASS_UNITS and _parse_number(match.group(1)) is not None else match.group(0),
        rest,
    )
    if rest.split()[:1] == ["kg"] and value < 1:
        return f"{format_amount(value * 1000)} g{rest[2:]}"
    return f"{format_amount(value)} {rest}".strip()
