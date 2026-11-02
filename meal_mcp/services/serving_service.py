from repo.recipe_repo import RecipeRepo
from services.measure_service import parse_amount, scale_measure


def clean_servings(value) -> int | None:
    """A positive whole number of servings, otherwise None."""
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
        return number if number >= 1 and number == float(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


class ServingService:
    """Servings and scaling. TheMealDB has no servings, so the user or the recipe text provides them."""

    def __init__(self, session):
        self.repo = RecipeRepo(session)

    def set_servings(self, items: list[dict]) -> dict:
        recipes = self._recipes(items)
        updated, errors = [], []
        for item in items:
            mealdb_id = str(item.get("mealdb_id", "")).strip()
            servings = clean_servings(item.get("servings"))
            if mealdb_id not in recipes:
                errors.append({"mealdb_id": mealdb_id, "reason": "Recipe not found."})
            elif servings is None:
                errors.append({"mealdb_id": mealdb_id, "reason": "servings must be a whole number of at least 1."})
            else:
                recipes[mealdb_id].servings = servings
                updated.append({"mealdb_id": mealdb_id, "servings": servings})
        self.repo.session.flush()
        return {"status": "updated" if updated else "nothing_updated", "updated": updated, "errors": errors}

    def scale(self, items: list[dict]) -> dict:
        """Ingredient amounts for another number of servings. Nothing is saved."""
        recipes = self._recipes(items)
        scaled, errors = [], []
        for item in items:
            mealdb_id = str(item.get("mealdb_id", "")).strip()
            recipe = recipes.get(mealdb_id)
            servings = clean_servings(item.get("servings"))
            if recipe is None:
                errors.append({"mealdb_id": mealdb_id, "reason": "Recipe not found."})
            elif servings is None:
                errors.append({"mealdb_id": mealdb_id, "reason": "servings must be a whole number of at least 1."})
            elif not recipe.effective_servings:
                errors.append({"mealdb_id": mealdb_id, "reason": "Servings of this recipe are unknown. Ask the user, then call set_recipe_servings."})
            else:
                scaled.append(self._scaled(recipe, servings))
        return {"recipes": scaled, "errors": errors}

    def _recipes(self, items: list[dict]) -> dict:
        ids = [str(item.get("mealdb_id", "")).strip() for item in items]
        return {recipe.mealdb_id: recipe for recipe in self.repo.get_bulk(ids)}

    @staticmethod
    def _scaled(recipe, servings: int) -> dict:
        factor = servings / recipe.effective_servings
        return {
            "mealdb_id": recipe.mealdb_id,
            "recipe_name": recipe.name,
            "servings_from": recipe.effective_servings,
            "servings_to": servings,
            "factor": round(factor, 3),
            "ingredients": [
                {"position": row.position, "name": row.name, "measure": row.measure, "scaled_measure": scale_measure(row.measure, factor)}
                for row in recipe.ingredients
            ],
            # Amounts like "to taste" have no number to multiply.
            "unscaled_ingredients": [row.name for row in recipe.ingredients if parse_amount(row.measure) is None],
            "note": "Not saved. Nutrition per serving stays the same; totals change by factor.",
        }
