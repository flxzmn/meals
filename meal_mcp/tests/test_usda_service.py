from services.usda_service import USDAService

ENERGY = [{"nutrientName": "Energy", "unitName": "KCAL", "value": 100}]


def test_extract_usda_nutrients():
    food = {
        "fdcId": 123,
        "description": "Tomatoes, raw",
        "foodNutrients": [
            {"nutrientName": "Energy", "value": 18},
            {"nutrientName": "Protein", "value": 0.9},
            {"nutrientName": "Total lipid (fat)", "value": 0.2},
            {"nutrientName": "Carbohydrate, by difference", "value": 3.9},
        ],
    }
    result = USDAService()._extract("Tomato", "tomato", food)
    assert result["usda_fdc_id"] == "123"
    assert result["calories_per_100g"] == 18


async def test_api_key_is_sent_as_header_and_never_in_errors(monkeypatch):
    import httpx

    from config.settings import settings

    key = "secret-test-key"
    monkeypatch.setattr(settings, "usda_api_key", key)
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(403, request=request)

    result = await USDAService(httpx.MockTransport(handler)).get_nutrients_bulk(
        [{"source_name": "Chicken", "normalized_name": "chicken"}]
    )
    assert requests[0].headers["X-Api-Key"] == key
    assert key not in str(requests[0].url)
    assert "API key rejected" in result["errors"]["Chicken"]
    assert key not in str(result)


def test_api_key_whitespace_is_stripped():
    from config.settings import Settings

    assert Settings(usda_api_key=" abc123 \n").usda_api_key == "abc123"


def test_energy_uses_kcal_not_kilojoule():
    food = {
        "fdcId": 1,
        "description": "Spices, cumin seed",
        "foodNutrients": [
            {"nutrientName": "Energy", "unitName": "KCAL", "value": 375},
            {"nutrientName": "Energy", "unitName": "kJ", "value": 1570},
        ],
    }
    assert USDAService()._extract("Cumin", "cumin", food)["calories_per_100g"] == 375


async def test_intermittent_400_is_retried(monkeypatch):
    import httpx

    from config.settings import settings

    monkeypatch.setattr(settings, "usda_api_key", "test-key")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "/food/" in request.url.path:
            return httpx.Response(200, request=request, json={"foodPortions": []})
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(400, request=request)
        return httpx.Response(200, request=request, json={"foods": [{"fdcId": 7, "description": "Kale, raw", "dataType": "SR Legacy", "foodNutrients": ENERGY}]})

    result = await USDAService(httpx.MockTransport(handler), retry_delay=0).get_nutrients_bulk(
        [{"source_name": "Kale", "normalized_name": "kale"}]
    )
    assert len(calls) == 3
    assert result["matched"][0]["matched_name"] == "Kale, raw"
    assert result["errors"] == {}


async def test_persistent_400_falls_back_to_unfiltered_search(monkeypatch):
    import httpx

    from config.settings import settings

    monkeypatch.setattr(settings, "usda_api_key", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if "dataType" in request.url.params:
            return httpx.Response(400, request=request)
        return httpx.Response(200, request=request, json={"foods": [
            {"fdcId": 1, "description": "CHICKEN NUGGETS", "dataType": "Branded", "foodNutrients": ENERGY},
            {"fdcId": 2, "description": "Chicken, broilers or fryers, meat only, raw", "dataType": "SR Legacy", "foodNutrients": ENERGY},
        ]})

    result = await USDAService(httpx.MockTransport(handler), retry_delay=0).get_nutrients_bulk(
        [{"source_name": "Chicken", "normalized_name": "chicken"}]
    )
    assert result["matched"][0]["usda_fdc_id"] == "2"


def test_energy_from_atwater_factors_for_foundation_foods():
    food = {
        "fdcId": 2,
        "description": "Yogurt, plain, whole milk",
        "foodNutrients": [
            {"nutrientName": "Energy (Atwater General Factors)", "unitName": "KCAL", "value": 78},
            {"nutrientName": "Energy (Atwater Specific Factors)", "unitName": "KCAL", "value": 74},
            {"nutrientName": "Protein", "unitName": "G", "value": 3.82},
        ],
    }
    result = USDAService()._extract("Yogurt", "yogurt", food)
    assert result["calories_per_100g"] == 78
    assert result["protein_per_100g"] == 3.82


async def test_alias_query_is_sent_without_punctuation_and_falls_back_to_name(monkeypatch):
    import httpx

    from config.settings import settings

    monkeypatch.setattr(settings, "usda_api_key", "test-key")
    queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "/food/" in request.url.path:
            return httpx.Response(200, request=request, json={"foodPortions": []})
        query = request.url.params["query"]
        queries.append(query)
        if query.startswith("Beef"):
            return httpx.Response(400, request=request)
        return httpx.Response(200, request=request, json={"foods": [
            {"fdcId": 3, "description": "Beef, cured, corned beef, brisket, raw", "dataType": "SR Legacy", "foodNutrients": ENERGY},
            {"fdcId": 4, "description": "Beef, ground, raw", "dataType": "SR Legacy", "foodNutrients": ENERGY},
        ]})

    result = await USDAService(httpx.MockTransport(handler), retry_delay=0).get_nutrients_bulk(
        [{"source_name": "Beef", "normalized_name": "beef"}]
    )
    assert "/" not in queries[0]
    assert queries[-1] == "beef"
    assert result["matched"][0]["usda_fdc_id"] == "4"
    assert result["errors"] == {}


async def test_portions_are_loaded_for_the_matched_food(monkeypatch):
    import httpx

    from config.settings import settings

    monkeypatch.setattr(settings, "usda_api_key", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/food/11"):
            return httpx.Response(200, request=request, json={"foodPortions": [
                {"portionDescription": "1 whole", "gramWeight": 148},
                {"amount": 0.5, "modifier": "cup, chopped", "gramWeight": 80},
            ]})
        return httpx.Response(200, request=request, json={"foods": [
            {"fdcId": 11, "description": "Onions, raw", "dataType": "SR Legacy", "foodNutrients": ENERGY},
        ]})

    result = await USDAService(httpx.MockTransport(handler), retry_delay=0).get_nutrients_bulk(
        [{"source_name": "Onion", "normalized_name": "onion"}]
    )
    assert result["matched"][0]["portions"] == [
        {"unit": "whole", "grams": 148.0},
        {"unit": "cup, chopped", "grams": 160.0},
    ]
