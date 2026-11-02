import asyncio
from pathlib import Path
from urllib.parse import urlparse

import httpx

from config.settings import settings
from repo.recipe_repo import RecipeRepo

# TheMealDB serves smaller versions under the image URL plus "/small", "/medium" or "/large".
SIZES = ("small", "medium", "large", "original")
# Image URLs come from the database, which import_data can fill; only TheMealDB is contacted.
ALLOWED_HOSTS = {"www.themealdb.com", "themealdb.com"}
MAX_BYTES = 2_000_000
PARALLEL_DOWNLOADS = 8


class ImageService:
    """Saves recipe photos as files, so a recipe book or document can embed them."""

    def __init__(self, session, transport: httpx.AsyncBaseTransport | None = None):
        self.repo = RecipeRepo(session)
        self.transport = transport

    async def download(self, mealdb_ids: list[str], size: str = "medium", folder: str | None = None) -> dict:
        if size not in SIZES:
            return {"status": "error", "message": f"size must be one of {', '.join(SIZES)}."}
        target = Path(folder).expanduser() if folder else settings.meal_data_dir / "images"
        recipes = {recipe.mealdb_id: recipe for recipe in self.repo.get_bulk(mealdb_ids)}
        wanted = list(dict.fromkeys(mealdb_ids))
        result = {"folder": str(target), "size": size, "images": [], "missing_recipes": [], "no_image": [], "errors": {}}

        # A variant has the photo of its original; each photo is fetched once.
        sources: dict[str, str] = {}
        urls: dict[str, str] = {}
        for mealdb_id in wanted:
            recipe = recipes.get(mealdb_id)
            if recipe is None:
                result["missing_recipes"].append(mealdb_id)
                continue
            owner = recipe.parent or recipe
            if not owner.image_url or urlparse(owner.image_url).hostname not in ALLOWED_HOSTS:
                result["no_image"].append(mealdb_id)
                continue
            sources[mealdb_id] = owner.mealdb_id
            urls[owner.mealdb_id] = owner.image_url

        target.mkdir(parents=True, exist_ok=True)
        limit = asyncio.Semaphore(PARALLEL_DOWNLOADS)
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, transport=self.transport, follow_redirects=False) as client:
            async def fetch(owner: str) -> tuple[str, dict | str]:
                path = target / f"{owner}-{size}.jpg"
                if path.exists():
                    return owner, {"path": str(path), "bytes": path.stat().st_size, "status": "existing"}
                url = urls[owner] if size == "original" else f"{urls[owner]}/{size}"
                async with limit:
                    try:
                        response = await client.get(url)
                        response.raise_for_status()
                    except httpx.HTTPError as exc:
                        return owner, f"{type(exc).__name__}: {exc}"
                if not response.headers.get("content-type", "").startswith("image/"):
                    return owner, "TheMealDB did not answer with an image"
                if len(response.content) > MAX_BYTES:
                    return owner, "image larger than 2 MB"
                path.write_bytes(response.content)
                return owner, {"path": str(path), "bytes": len(response.content), "status": "downloaded"}

            fetched = dict(await asyncio.gather(*(fetch(owner) for owner in urls)))

        for mealdb_id, owner in sources.items():
            outcome = fetched[owner]
            if isinstance(outcome, str):
                result["errors"][mealdb_id] = outcome
            else:
                result["images"].append({"mealdb_id": mealdb_id, **outcome})
        result["note"] = (
            "Photos from TheMealDB; variants use the photo of their original. "
            "Credit TheMealDB when the photos are published."
        )
        return result
