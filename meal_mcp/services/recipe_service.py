from repo.recipe_repo import RecipeRepo
from services.mealdb_service import MealDBService


class RecipeService:
    def __init__(self, session):
        self.repo = RecipeRepo(session)
        self.mealdb = MealDBService()

    async def search_recipes(self, queries: list[str]) -> dict:
        response = await self.mealdb.search_bulk(queries)
        compact = {
            query: [
                {"mealdb_id": meal["idMeal"], "name": meal["strMeal"], "category": meal.get("strCategory"), "area": meal.get("strArea")}
                for meal in meals
            ]
            for query, meals in response["results"].items()
        }
        return {"results": compact, "errors": response["errors"]}

    async def save_recipes(self, mealdb_ids: list[str]) -> dict:
        response = await self.mealdb.get_bulk(mealdb_ids)
        saved = self.repo.save_bulk(response["meals"])
        saved["missing"] = sorted(set(saved["missing"] + response["missing"]))
        saved["errors"] = response["errors"]
        return saved

    def list_recipes(self) -> list[dict]:
        return [serialize_recipe(recipe, full=False) for recipe in self.repo.list_all()]

    def get_recipes(self, mealdb_ids: list[str]) -> dict:
        recipes = {recipe.mealdb_id: recipe for recipe in self.repo.get_bulk(mealdb_ids)}
        return {
            "recipes": [serialize_recipe(recipes[mealdb_id]) for mealdb_id in dict.fromkeys(mealdb_ids) if mealdb_id in recipes],
            "missing": sorted(set(mealdb_ids) - set(recipes)),
        }

    def delete_recipes(self, mealdb_ids: list[str]) -> dict:
        return self.repo.delete_bulk(mealdb_ids)


def serialize_recipe(recipe, full: bool = True) -> dict:
    """Recipe or variant as a dict. full=False gives the short form used in lists."""
    data = {
        "mealdb_id": recipe.mealdb_id,
        "name": recipe.name,
        "category": recipe.category,
        "area": recipe.area,
        "is_variant": recipe.parent_id is not None,
        "parent_mealdb_id": recipe.parent.mealdb_id if recipe.parent else None,
        "ingredient_count": len(recipe.ingredients),
        "servings": recipe.effective_servings,
    }
    if recipe.parent_id is None:
        data["variant_ids"] = [variant.mealdb_id for variant in recipe.variants]
    else:
        data["constraints"] = recipe.constraints or {}
        data["change_count"] = len(recipe.changes or [])
    if not full:
        return data
    data.update({
        "instructions": recipe.instructions,
        "image_url": recipe.image_url,
        "ingredients": [
            {"position": row.position, "name": row.name, "measure": row.measure, "estimated_grams": row.estimated_grams}
            for row in recipe.ingredients
        ],
        "created_at": recipe.created_at.isoformat() if recipe.created_at else None,
    })
    if recipe.parent_id is not None:
        data["changes"] = recipe.changes or []
        data["instructions_source"] = recipe.instructions_source or "original"
        data["updated_at"] = recipe.updated_at.isoformat() if recipe.updated_at else None
    return data
