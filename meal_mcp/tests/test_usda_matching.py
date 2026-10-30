import pytest

from services.usda_matching import best_match, search_queries, search_text


def foods(*descriptions, data_type="Survey (FNDDS)"):
    return [{"fdcId": index, "description": text, "dataType": data_type} for index, text in enumerate(descriptions)]


# Search results as the USDA API returned them in the release test (first result was used before).
@pytest.mark.parametrize("query, results, expected", [
    ("salt", ["Pecans, salted", "Almonds, salted", "Butter, salted", "Salt, table"], "Salt, table"),
    ("garlic", ["Garlic sauce", "Garlic, cooked", "Garlic, raw", "Roll, garlic"], "Garlic, raw"),
    ("chili powder", ["Baobab powder", "Sugars, powdered", "Spices, chili powder"], "Spices, chili powder"),
    ("turmeric powder", ["Baobab powder", "Spices, turmeric, ground"], "Spices, turmeric, ground"),
    ("green chili", ["Peppers, chili, green, canned", "Peppers, hot chili, green, raw"], "Peppers, hot chili, green, raw"),
    ("yogurt", ["Tofu yogurt", "Yogurt tube", "Frozen yogurt, NFS", "Yogurt, NFS"], "Yogurt, NFS"),
    ("mozzarella", ["APPLEBEE'S, mozzarella sticks", "Cheese, mozzarella, nonfat", "Cheese, mozzarella, whole milk"],
     "Cheese, mozzarella, whole milk"),
    ("onion", ["Onions, raw", "Bread, onion", "Onion dip, regular"], "Onions, raw"),
])
def test_best_match_prefers_plain_ingredient(query, results, expected):
    assert best_match(query, foods(*results))["description"] == expected


def test_no_match_when_query_words_are_missing():
    assert best_match("ginger paste", foods("Almond paste", "Guava paste", "Wasabi paste")) is None


def test_exact_alias_description_wins():
    results = foods(
        "Chicken, broilers or fryers, back, meat and skin, raw",
        "Chicken, broilers or fryers, meat and skin, raw",
        data_type="SR Legacy",
    )
    match = best_match("Chicken, broilers or fryers, meat and skin, raw", results)
    assert match["description"] == "Chicken, broilers or fryers, meat and skin, raw"


def test_search_queries_use_alias_then_name_and_normalize_spelling():
    assert search_queries("chicken") == ["Chicken, broilers or fryers, meat and skin, raw", "chicken"]
    assert search_queries("green chilli") == ["Peppers, hot chili, green, raw", "green chili"]
    assert search_queries("quinoa") == ["quinoa"]


def test_search_text_removes_punctuation():
    assert search_text("Beef, ground, 80% lean meat / 20% fat, raw") == "Beef ground 80% lean meat 20% fat raw"
