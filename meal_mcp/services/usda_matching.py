"""Pick the USDA food that best matches a recipe ingredient.

The USDA search ranks by text relevance, so "chicken" returns "Chicken, chicken roll, roasted" and
"salt" returns "Pecans, salted". Two layers fix this:

1. ALIASES maps common recipe ingredients to an exact USDA description (generic raw food).
2. score_food ranks all search results: every query word must appear in the description, the
   food should be the ingredient itself (not a dish containing it), raw and unprocessed foods win.
"""

import re

# Normalized ingredient name -> exact USDA description to search for.
ALIASES = {
    "chicken": "Chicken, broilers or fryers, meat and skin, raw",
    "chicken breast": "Chicken, broilers or fryers, breast, meat only, raw",
    "chicken breasts": "Chicken, broilers or fryers, breast, meat only, raw",
    "chicken thighs": "Chicken, broilers or fryers, thigh, meat only, raw",
    "yogurt": "Yogurt, plain, whole milk",
    "natural yogurt": "Yogurt, plain, whole milk",
    "greek yogurt": "Yogurt, Greek, plain, whole milk",
    "salt": "Salt, table",
    "sea salt": "Salt, table",
    "garlic": "Garlic, raw",
    "garlic clove": "Garlic, raw",
    "garlic cloves": "Garlic, raw",
    "ginger": "Ginger root, raw",
    "ginger paste": "Ginger root, raw",
    "garlic paste": "Garlic, raw",
    "chili powder": "Spices, chili powder",
    "green chili": "Peppers, hot chili, green, raw",
    "red chili": "Peppers, hot chili, red, raw",
    # No USDA entry for garam masala; curry powder is the closest spice blend.
    "garam masala": "Spices, curry powder",
    "onion": "Onions, raw",
    "onions": "Onions, raw",
    "tomato": "Tomatoes, red, ripe, raw, year round average",
    "tomatoes": "Tomatoes, red, ripe, raw, year round average",
    "butter": "Butter, salted",
    "egg": "Egg, whole, raw, fresh",
    "eggs": "Egg, whole, raw, fresh",
    "milk": "Milk, whole, 3.25% milkfat, with added vitamin D",
    "plain flour": "Wheat flour, white, all-purpose, enriched, bleached",
    "flour": "Wheat flour, white, all-purpose, enriched, bleached",
    "sugar": "Sugars, granulated",
    "rice": "Rice, white, long-grain, regular, raw, enriched",
    "beef": "Beef, ground, 80% lean meat / 20% fat, raw",
    "minced beef": "Beef, ground, 80% lean meat / 20% fat, raw",
    "potatoes": "Potatoes, flesh and skin, raw",
    "potato": "Potatoes, flesh and skin, raw",
    "spaghetti": "Pasta, dry, enriched",
    "pasta": "Pasta, dry, enriched",
    "pork": "Pork, fresh, ground, raw",
    # Recipes mostly mean cooked or canned chickpeas; dried ones have about 2.5 times the kcal.
    "chickpeas": "Chickpeas (garbanzo beans, bengal gram), mature seeds, canned, drained solids",
    "dried chickpeas": "Chickpeas (garbanzo beans, bengal gram), mature seeds, raw",
    "eggplant": "Eggplant, raw",
    "zucchini": "Squash, summer, zucchini, includes skin, raw",
    "green onions": "Onions, spring or scallions (includes tops and bulb), raw",
    "baking soda": "Leavening agents, baking soda",
    "powdered sugar": "Sugars, powdered",
    "parmesan cheese": "Cheese, parmesan, grated",
    "parmesan": "Cheese, parmesan, grated",
    "salmon": "Fish, salmon, Atlantic, farmed, raw",
    "coconut milk": "Nuts, coconut milk, canned (liquid expressed from grated meat and water)",
    "olive oil": "Oil, olive, salad or cooking",
    "vegetable oil": "Oil, vegetable, soybean, refined",
    "double cream": "Cream, fluid, heavy whipping",
    "heavy cream": "Cream, fluid, heavy whipping",
}

# German descriptive words dropped before translation ("frischer Knoblauch" -> "garlic").
GERMAN_FILLERS = {
    "frisch", "frische", "frischer", "frisches", "gehackt", "gehackte", "gehackter", "getrocknet",
    "getrocknete", "getrockneter", "gemahlen", "gemahlene", "gemahlener", "fein", "grob", "große", "großer",
    "kleine", "kleiner",
}

# British and alternative spellings -> USDA spelling.
SPELLINGS = {
    "chilli": "chili",
    "chillies": "chili",
    "chilies": "chili",
    "chillis": "chili",
    "yoghurt": "yogurt",
}

# German and international ingredient names -> English recipe name (Sprint 10).
# Whole names are looked up first, then single words ("frischer knoblauch" -> "frischer garlic").
TRANSLATIONS = {
    # German
    "hähnchen": "chicken", "hühnchen": "chicken", "huhn": "chicken", "hähnchenbrust": "chicken breast",
    "hähnchenschenkel": "chicken thighs", "rindfleisch": "beef", "hackfleisch": "minced beef",
    "schweinefleisch": "pork", "lachs": "salmon", "ei": "egg", "eier": "eggs",
    "zwiebel": "onion", "zwiebeln": "onions", "frühlingszwiebeln": "green onions", "knoblauch": "garlic",
    "knoblauchzehe": "garlic clove", "knoblauchzehen": "garlic cloves", "ingwer": "ginger",
    "tomate": "tomato", "tomaten": "tomatoes", "kartoffel": "potato", "kartoffeln": "potatoes",
    "möhre": "carrot", "möhren": "carrots", "karotte": "carrot", "karotten": "carrots",
    "spinat": "spinach", "kichererbsen": "chickpeas",
    "linsen": "lentils", "reis": "rice", "nudeln": "pasta", "mehl": "flour", "zucker": "sugar",
    "puderzucker": "powdered sugar", "salz": "salt", "pfeffer": "black pepper", "milch": "milk",
    "sahne": "cream", "schlagsahne": "heavy cream", "joghurt": "yogurt",
    "käse": "cheese", "olivenöl": "olive oil", "pflanzenöl": "vegetable oil", "honig": "honey",
    "kreuzkümmel": "cumin", "kurkuma": "turmeric powder", "zimt": "cinnamon", "petersilie": "parsley",
    "koriander": "coriander leaves", "natron": "baking soda",
    "rote": "red", "roter": "red", "rotes": "red", "grüne": "green", "grüner": "green", "grünes": "green",
    "weiße": "white", "weißer": "white", "weißes": "white", "chilischote": "chili", "chilischoten": "chili",
    # British and international
    "aubergine": "eggplant", "courgette": "zucchini", "courgettes": "zucchini",
    "spring onions": "green onions", "spring onion": "green onions", "scallions": "green onions",
    "caster sugar": "sugar", "icing sugar": "powdered sugar", "bicarbonate of soda": "baking soda",
    "self-raising flour": "flour", "parmigiano-reggiano": "parmesan cheese",
    "parmigiano reggiano": "parmesan cheese", "grana padano": "parmesan cheese",
    "garbanzo beans": "chickpeas", "minced meat": "minced beef", "mince": "minced beef",
}

# Words that mark a dish or processed product. Penalized unless the query asks for them.
PROCESSED = {
    "sauce", "soup", "bread", "dip", "roll", "rolls", "frozen", "salted", "sweetened", "flavored",
    "fast", "restaurant", "baby", "toddler", "pickled", "canned", "imitation", "substitute",
    "casserole", "stick", "sticks", "puffed", "fried", "spread", "drink", "beverage", "beverages", "candy", "cake", "cookie",
    "pie", "pizza", "sandwich", "with", "dehydrated", "breaded", "nuggets", "meatless",
}

# Words that mark a prepared or altered variant. Penalized less than PROCESSED.
MODIFIED = {
    "cooked", "boiled", "baked", "roasted", "grilled", "braised", "stewed", "smoked", "cured",
    "corned", "salt", "nonfat", "lowfat", "low", "reduced", "light", "fat", "free", "skim",
}

STOPWORDS = {"and", "or", "of", "the", "a", "with"}
# USDA files many foods under a category first ("Spices, chili powder", "Cheese, mozzarella").
CATEGORY_HEADS = {"spices", "spice", "cheese", "oil", "nuts", "seeds", "sugars", "beans", "fish", "peppers", "pasta"}
# Describe the form of an ingredient; USDA often words them differently ("powder" vs "ground").
# They count when present but are not required.
FORM_WORDS = {"powder", "ground", "paste", "seed", "fresh", "dried", "chopped", "sliced", "minced", "leave", "flake"}
DATA_TYPE_BONUS = {"Foundation": 1.0, "SR Legacy": 0.8, "Survey (FNDDS)": 0.5}


def _words(text: str) -> list[str]:
    return [SPELLINGS.get(word, word) for word in re.findall(r"[a-zäöüß]+", text.lower())]


def translate(name: str) -> str:
    """English recipe name for a German or international ingredient name."""
    lowered = " ".join(name.lower().split())
    if lowered in TRANSLATIONS:
        return TRANSLATIONS[lowered]
    words = [word for word in lowered.split() if word not in GERMAN_FILLERS] or lowered.split()
    joined = " ".join(words)
    if joined in TRANSLATIONS:
        return TRANSLATIONS[joined]
    return " ".join(TRANSLATIONS.get(word, word) for word in words)


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("oes"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def search_text(query: str) -> str:
    """Query without punctuation; the USDA search answers 400 to some characters such as "/"."""
    return " ".join(re.findall(r"[\w%]+", query))


def search_queries(normalized_name: str) -> list[str]:
    """Texts to send to the USDA search, in order: the alias (if any), then the ingredient name."""
    english = translate(normalized_name)
    spelled = " ".join(_words(english))
    alias = ALIASES.get(english) or ALIASES.get(spelled)
    return [query for query in dict.fromkeys([alias, spelled]) if query]


def score_food(query: str, food: dict) -> float | None:
    """Higher is better. None means the food does not contain every query word."""
    description = str(food.get("description") or "")
    if description.lower() == query.lower():
        return 100.0

    query_stems = {_stem(word) for word in _words(query)} - STOPWORDS
    segments = [segment.strip() for segment in description.lower().split(",") if segment.strip()]
    words = [_stem(word) for segment in segments for word in _words(segment)]
    required = (query_stems - FORM_WORDS) or query_stems
    if not required <= set(words):
        return None

    # The food itself is the first segment, or the second one after a category ("Cheese, mozzarella").
    heads = segments[:2] if segments[0] in CATEGORY_HEADS else segments[:1]
    head = {_stem(word) for word in _words(heads[-1])} - STOPWORDS
    score = DATA_TYPE_BONUS.get(food.get("dataType"), 0.0)
    if head <= query_stems:
        score += 3.0  # the description starts with the ingredient itself
    if re.search(r"\b(?!NFS\b)[A-Z]{3,}", description) and not description.isupper():
        score -= 3.0  # brand or restaurant product ("APPLEBEE'S, mozzarella sticks")
    if "raw" in words and "raw" not in query_stems:
        score += 1.0
    extra = [word for word in words if word not in query_stems]
    score -= 3.0 * sum(1 for word in set(extra) if word in PROCESSED)
    score -= 1.0 * sum(1 for word in set(extra) if word in MODIFIED)
    score -= 0.1 * len(extra)
    return score


def best_match(query: str, foods: list[dict]) -> dict | None:
    scored = [(score, -index, food) for index, food in enumerate(foods) if (score := score_food(query, food)) is not None]
    if not scored:
        return None
    return max(scored, key=lambda entry: (entry[0], entry[1]))[2]
