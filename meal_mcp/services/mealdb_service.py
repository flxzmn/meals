import asyncio
import httpx
from config.settings import settings


class MealDBService:
    async def _request(self, endpoint: str, params: dict) -> dict:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            response = await client.get(f"{settings.mealdb_base_url}/{endpoint}", params=params)
            response.raise_for_status()
            return response.json()

    async def search_bulk(self, queries: list[str]) -> dict:
        clean = list(dict.fromkeys(query.strip() for query in queries if query.strip()))
        responses = await asyncio.gather(
            *(self._request("search.php", {"s": query}) for query in clean),
            return_exceptions=True,
        )
        results, errors = {}, {}
        for query, response in zip(clean, responses):
            if isinstance(response, Exception):
                errors[query] = str(response)
            else:
                results[query] = response.get("meals") or []
        return {"results": results, "errors": errors}

    async def get_bulk(self, mealdb_ids: list[str]) -> dict:
        clean = list(dict.fromkeys(str(item).strip() for item in mealdb_ids if str(item).strip()))
        responses = await asyncio.gather(
            *(self._request("lookup.php", {"i": meal_id}) for meal_id in clean),
            return_exceptions=True,
        )
        meals, missing, errors = [], [], {}
        for meal_id, response in zip(clean, responses):
            if isinstance(response, Exception):
                errors[meal_id] = str(response)
                continue
            found = response.get("meals") or []
            if found:
                meals.append(found[0])
            else:
                missing.append(meal_id)
        return {"meals": meals, "missing": missing, "errors": errors}
