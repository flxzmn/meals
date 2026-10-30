from services.measure_service import (
    estimate_grams,
    grams_from_portions,
    is_mass_measure,
    normalize_ingredient_name,
    normalize_portions,
)


def test_normalize_ingredient_name():
    assert normalize_ingredient_name("  Chicken_Breast ") == "chicken breast"


def test_estimate_grams_mass_and_volume():
    assert estimate_grams("100 g") == 100.0
    assert estimate_grams("1 kg") == 1000.0
    assert estimate_grams("2 tbsp") == 30.0
    assert estimate_grams("1 1/2 cups") == 360.0


def test_unknown_measure_returns_none():
    assert estimate_grams("a pinch") is None


def test_decimal_amount_and_abbreviation_dot():
    assert estimate_grams("1.2 kg") == 1200.0
    assert estimate_grams("0,5 l") == 500.0
    assert estimate_grams("2 tsp.") == 10.0


# Portion data as the USDA API returns it (SR Legacy: amount + modifier, FNDDS: portionDescription).
TOMATO = normalize_portions([
    {"amount": 1.0, "modifier": 'medium whole (2-3/5" dia)', "gramWeight": 123},
    {"amount": 1.0, "modifier": 'slice, medium (1/4" thick)', "gramWeight": 20},
    {"amount": 1.0, "modifier": 'large whole (3" dia)', "gramWeight": 182},
    {"amount": 0.5, "modifier": "cup, chopped or diced", "gramWeight": 90},
])
GARLIC = normalize_portions([
    {"portionDescription": "Quantity not specified", "gramWeight": 5},
    {"portionDescription": "1 cup", "gramWeight": 135},
    {"portionDescription": "1 clove", "gramWeight": 3},
])
CHILI_POWDER = normalize_portions([
    {"amount": 1.0, "modifier": "tbsp", "gramWeight": 8},
    {"amount": 1.0, "modifier": "tsp", "gramWeight": 2.7},
])


def test_normalize_portions_gives_grams_per_unit():
    assert {"unit": "cup, chopped or diced", "grams": 180.0} in TOMATO
    assert {"unit": "clove", "grams": 3.0} in GARLIC


def test_piece_count_uses_medium_or_named_size():
    assert grams_from_portions("2 finely chopped", TOMATO)[0] == 246.0
    assert grams_from_portions("2 large", TOMATO)[0] == 364.0


def test_named_piece_unit():
    grams, basis = grams_from_portions("8 cloves chopped", GARLIC)
    assert grams == 24.0
    assert basis == "USDA portion: 1 clove = 3 g"


def test_spoons_use_usda_weight_and_are_scaled():
    assert grams_from_portions("1 tsp", CHILI_POWDER)[0] == 2.7
    assert grams_from_portions("2 teaspoons", CHILI_POWDER)[0] == 5.4
    assert grams_from_portions("1 cup", [{"unit": "tbsp", "grams": 8.0}])[0] == 128.0


def test_mass_and_unparsable_measures_are_not_converted_by_portions():
    assert grams_from_portions("100 g", TOMATO) is None
    assert grams_from_portions("To taste", TOMATO) is None
    assert is_mass_measure("1.2 kg")
    assert not is_mass_measure("2 tbsp")


def test_cut_pieces_are_not_scaled_to_spoons():
    ginger = [{"unit": 'cup slices (1" dia)', "grams": 96.0}]
    assert grams_from_portions("1 tbsp", ginger) is None
