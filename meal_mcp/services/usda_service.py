import asyncio
import httpx
from config.settings import settings
from services.measure_service import normalize_portions
from services.usda_matching import best_match, search_queries, search_text, translate

NUTRIENT_NAMES = {
    "Protein": "protein_per_100g",
    "Total lipid (fat)": "fat_per_100g",
    "Carbohydrate, by difference": "carbs_per_100g",
}


# Foundation foods report energy only as Atwater factors; SR Legacy and FNDDS as "Energy".
ENERGY_NAMES = ["Energy", "Energy (Atwater General Factors)", "Energy (Atwater Specific Factors)"]
DATA_TYPES = ["Foundation", "SR Legacy", "Survey (FNDDS)"]

# The USDA search endpoint intermittently answers 400 when dataType is set. Retry a few
# times, then search once without the filter and filter the results locally.
RETRY_STATUS_CODES = {400, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 0.5
# Enough results for best_match to find the plain raw food among dishes and products.
PAGE_SIZE = 25


class USDAConfigurationError(RuntimeError):
    pass


class USDAService:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None, retry_delay: float = RETRY_DELAY_SECONDS):
        self.transport = transport
        self.retry_delay = retry_delay

    async def _search(self, client: httpx.AsyncClient, query: str) -> httpx.Response:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            last_attempt = attempt == MAX_ATTEMPTS
            params = {"query": query, "pageSize": 50} if last_attempt else {
                "query": query, "pageSize": PAGE_SIZE, "dataType": DATA_TYPES,
            }
            # Key as header, not query parameter, so it never appears in URLs or error messages.
            response = await client.get(
                f"{settings.usda_base_url}/foods/search",
                headers={"X-Api-Key": settings.usda_api_key},
                params=params,
            )
            if response.status_code not in RETRY_STATUS_CODES or last_attempt:
                return response
            await asyncio.sleep(self.retry_delay * attempt)

    async def _details(self, client: httpx.AsyncClient, fdc_id) -> dict | None:
        """Full record of one food (nutrients and portion weights). None if USDA does not answer."""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            response = await client.get(
                f"{settings.usda_base_url}/food/{fdc_id}",
                headers={"X-Api-Key": settings.usda_api_key},
                params={"format": "full"},
            )
            if response.status_code == 200:
                return response.json()
            if response.status_code in (401, 403):
                response.raise_for_status()
            if response.status_code not in RETRY_STATUS_CODES:
                return None
            await asyncio.sleep(self.retry_delay * attempt)
        return None

    async def _portions(self, client: httpx.AsyncClient, fdc_id) -> list[dict] | None:
        """Portion weights of a food. None if USDA did not answer; the next enrichment retries."""
        details = await self._details(client, fdc_id)
        return None if details is None else normalize_portions(details.get("foodPortions") or [])

    async def _candidates(self, client: httpx.AsyncClient, query: str) -> list[dict]:
        response = await self._search(client, search_text(query))
        response.raise_for_status()
        return [food for food in response.json().get("foods") or [] if food.get("dataType") in DATA_TYPES]

    async def _find(self, client: httpx.AsyncClient, query: str, exclude: set[str] = frozenset()) -> dict | None:
        foods = [food for food in await self._candidates(client, query) if str(food["fdcId"]) not in exclude]
        return best_match(query, foods)

    @staticmethod
    def _describe_error(exc: Exception) -> str:
        """Error text for tool results. Never includes the request URL or the API key."""
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status in (401, 403):
                return f"USDA HTTP {status}: API key rejected. Check the key in the extension settings."
            return f"USDA HTTP {status}"
        message = str(exc)
        if settings.usda_api_key:
            message = message.replace(settings.usda_api_key, "***")
        return f"{type(exc).__name__}: {message}"

    def _extract(self, source_name: str, normalized_name: str, food: dict) -> dict:
        """Nutrients per 100 g. Search results use nutrientName/value, food details nutrient.name/amount."""
        values = {field: None for field in NUTRIENT_NAMES.values()}
        energy: dict[str, float] = {}
        for nutrient in food.get("foodNutrients") or []:
            details = nutrient.get("nutrient") or {}
            name = nutrient.get("nutrientName") or details.get("name")
            value = nutrient.get("value", nutrient.get("amount"))
            # USDA reports energy in KCAL and kJ; only kcal is wanted.
            unit = str(nutrient.get("unitName") or details.get("unitName") or "").upper()
            if name in ENERGY_NAMES:
                if not unit or unit == "KCAL":
                    energy.setdefault(name, value)
                continue
            field = NUTRIENT_NAMES.get(name)
            if field:
                values[field] = value
        values["calories_per_100g"] = next((energy[name] for name in ENERGY_NAMES if name in energy), None)
        return {
            "normalized_name": normalized_name,
            "source_name": source_name,
            "usda_fdc_id": str(food["fdcId"]),
            "matched_name": food.get("description") or source_name,
            **values,
        }

    def _check_key(self) -> None:
        if not settings.usda_api_key or settings.usda_api_key == "replace_with_your_data_gov_key":
            raise USDAConfigurationError("USDA_API_KEY fehlt oder ist noch ein Platzhalter.")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=settings.http_timeout_seconds, transport=self.transport)

    async def get_nutrients_bulk(self, ingredients: list[dict]) -> dict:
        """Match and load several ingredients.

        Optional per item: fdc_id (a manually chosen food, no search) and exclude_fdc_ids (foods
        rejected for this ingredient).
        """
        self._check_key()
        semaphore = asyncio.Semaphore(settings.max_concurrent_requests)

        async def lookup(item: dict):
            async with semaphore:
                async with self._client() as client:
                    if item.get("fdc_id"):
                        details = await self._details(client, item["fdc_id"])
                        if details is None:
                            return None
                        result = self._extract(item["source_name"], item["normalized_name"], details)
                        result["portions"] = normalize_portions(details.get("foodPortions") or [])
                        return result
                    exclude = {str(value) for value in item.get("exclude_fdc_ids") or []}
                    queries = search_queries(item["normalized_name"])
                    for index, query in enumerate(queries):
                        try:
                            food = await self._find(client, query, exclude)
                        except httpx.HTTPStatusError as exc:
                            # An alias query that fails still leaves the plain ingredient name to try.
                            if exc.response.status_code in (401, 403) or index == len(queries) - 1:
                                raise
                            continue
                        if food:
                            result = self._extract(item["source_name"], item["normalized_name"], food)
                            result["portions"] = await self._portions(client, food["fdcId"])
                            return result
                    return None

        responses = await asyncio.gather(*(lookup(item) for item in ingredients), return_exceptions=True)
        matched, missing, errors = [], [], {}
        for item, response in zip(ingredients, responses):
            if isinstance(response, Exception):
                errors[item["source_name"]] = self._describe_error(response)
            elif response is None:
                missing.append(item["source_name"])
            else:
                matched.append(response)
        return {"matched": matched, "missing": missing, "errors": errors}

    async def search_foods(self, queries: list[str], limit: int = 8) -> dict:
        """USDA candidates per query with nutrients per 100 g, so a match can be chosen by hand."""
        self._check_key()
        semaphore = asyncio.Semaphore(settings.max_concurrent_requests)

        async def search(query: str):
            async with semaphore:
                async with self._client() as client:
                    foods = await self._candidates(client, translate(query))
            rows = []
            for food in foods[:limit]:
                values = self._extract(query, query, food)
                rows.append({
                    "fdc_id": values["usda_fdc_id"],
                    "description": values["matched_name"],
                    "data_type": food.get("dataType"),
                    "calories_per_100g": values["calories_per_100g"],
                    "protein_per_100g": values["protein_per_100g"],
                    "fat_per_100g": values["fat_per_100g"],
                    "carbs_per_100g": values["carbs_per_100g"],
                })
            return rows

        responses = await asyncio.gather(*(search(query) for query in queries), return_exceptions=True)
        results, errors = {}, {}
        for query, response in zip(queries, responses):
            if isinstance(response, Exception):
                errors[query] = self._describe_error(response)
            else:
                results[query] = response
        return {"results": results, "errors": errors}
