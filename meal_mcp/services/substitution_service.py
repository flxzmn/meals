from __future__ import annotations

from copy import deepcopy

from repo.nutrition_repo import NutritionRepo
from repo.recipe_repo import RecipeRepo
from repo.substitution_repo import SubstitutionRepo
from services.constraint_service import constraint_violation, excluded_terms
from services.measure_service import (
    format_amount,
    ingredient_grams,
    measure_kind,
    normalize_ingredient_name,
    scale_measure,
)


class SubstitutionService:
    def __init__(self, session):
        self.recipe_repo = RecipeRepo(session)
        self.substitution_repo = SubstitutionRepo(session)
        self.nutrition_repo = NutritionRepo(session)

    def add_substitutions(self, substitutions: list[dict]) -> dict:
        return self.substitution_repo.add_bulk(substitutions)

    def delete_substitutions(self, substitutions: list[dict]) -> dict:
        return self.substitution_repo.delete_bulk(substitutions)

    def set_quantities(self, rules: list[dict]) -> dict:
        return self.substitution_repo.set_quantities(rules)

    def list_substitutions(self) -> list[dict]:
        return self.substitution_repo.list_all()

    def find_substitutions(self, ingredients: list[str], constraints: dict | None = None) -> dict:
        constraints = constraints or {}
        candidates = self.substitution_repo.find_bulk(ingredients)
        return {
            source: self._filter_candidates(rows, constraints)
            for source, rows in candidates.items()
        }

    def adapt_recipes(self, mealdb_ids: list[str], constraints: dict | None = None) -> dict:
        constraints = constraints or {}
        recipes = self.recipe_repo.get_bulk(mealdb_ids)
        found_ids = {recipe.mealdb_id for recipe in recipes}
        missing_recipes = sorted(set(mealdb_ids) - found_ids)

        sources = sorted({ingredient.normalized_name for recipe in recipes for ingredient in recipe.ingredients})
        candidates = self.find_substitutions(sources, constraints)
        cached = self.nutrition_repo.get_cached_bulk(sources)

        adapted_recipes: list[dict] = []
        missing_substitutions: set[str] = set()
        unverified_quantities: list[dict] = []
        substitutions_applied = 0

        for recipe in recipes:
            adapted_ingredients: list[dict] = []
            recipe_changes: list[dict] = []

            for ingredient in recipe.ingredients:
                available = candidates.get(ingredient.normalized_name, [])
                selected = available[0] if available else None
                ingredient_result = {
                    "position": ingredient.position,
                    "name": ingredient.name,
                    "normalized_name": ingredient.normalized_name,
                    "measure": ingredient.measure,
                    "estimated_grams": ingredient.estimated_grams,
                }

                if selected is not None:
                    ingredient_result["name"] = selected["target_ingredient"]
                    ingredient_result["normalized_name"] = normalize_ingredient_name(selected["target_ingredient"])
                    ingredient_result["substitution"] = selected
                    nutrition = cached.get(ingredient.normalized_name)
                    quantity = target_quantity(ingredient, selected, nutrition.portions if nutrition else None)
                    ingredient_result["quantity"] = quantity
                    if quantity["status"] == "adjusted":
                        ingredient_result["measure"] = quantity["target_measure"]
                        ingredient_result["estimated_grams"] = quantity.get("target_grams")
                    else:
                        unverified_quantities.append({"recipe": recipe.name, "ingredient": ingredient.name, "measure": ingredient.measure})
                    substitutions_applied += 1
                    recipe_changes.append({
                        "source": ingredient.name,
                        "target": selected["target_ingredient"],
                        "reason": selected.get("reason"),
                        "confidence": selected.get("confidence"),
                    })
                elif self._requires_substitution(ingredient.normalized_name, constraints):
                    missing_substitutions.add(ingredient.name)

                adapted_ingredients.append(ingredient_result)

            adapted_recipes.append({
                "source_mealdb_id": recipe.mealdb_id,
                "source_recipe_name": recipe.name,
                "name": f"{recipe.name} (adapted)",
                "category": recipe.category,
                "area": recipe.area,
                "instructions": recipe.instructions,
                "image_url": recipe.image_url,
                "constraints": constraints,
                "changes": recipe_changes,
                "ingredients": adapted_ingredients,
            })

        status = "success"
        if missing_recipes or missing_substitutions:
            status = "partial_success" if adapted_recipes else "error"

        return {
            "status": status,
            "recipes_processed": len(recipes),
            "adapted_recipes": adapted_recipes,
            "substitutions_applied": substitutions_applied,
            "missing_recipes": missing_recipes,
            "missing_substitutions": sorted(missing_substitutions),
            "unverified_quantities": unverified_quantities,
            "note": "Adapted recipes are returned, not stored. Save them with save_adapted_recipes. The original recipes remain unchanged.",
        }

    @staticmethod
    def _filter_candidates(candidates: list[dict], constraints: dict) -> list[dict]:
        return [candidate for candidate in candidates if constraint_violation(candidate, constraints) is None]

    @staticmethod
    def _requires_substitution(normalized_name: str, constraints: dict) -> bool:
        if constraints.get("diet"):
            return True
        return normalized_name in excluded_terms(constraints)


def target_quantity(ingredient, substitution: dict, portions: list[dict] | None) -> dict:
    """Amount of the substitute (Sprint 8): source amount x quantity_ratio, never a blind 1:1 count.

    Mass and volume measures are scaled in their own unit. Piece counts ("4 chicken breasts") are
    converted to grams with the USDA portion weight of the source first, so 4 breasts become
    about 700 g of the substitute instead of "4 chickpeas". Without a convertible amount the measure
    is kept and marked as unverified.
    """
    ratio = float(substitution.get("quantity_ratio") or 1.0)
    result = {"ratio": ratio, "source_measure": ingredient.measure}
    if substitution.get("quantity_note"):
        result["note"] = substitution["quantity_note"]
    kind = measure_kind(ingredient.measure)

    if kind in ("mass", "volume"):
        grams, basis = ingredient_grams(ingredient.measure, ingredient.estimated_grams, portions)
        result.update({
            "status": "adjusted",
            "target_measure": scale_measure(ingredient.measure, ratio),
            "target_grams": round(grams * ratio, 1) if grams is not None else None,
            "basis": basis,
            "estimated": kind == "volume" or ratio != 1.0,
        })
        return result

    if kind == "piece":
        grams, basis = ingredient_grams(ingredient.measure, None, portions)
        if grams is not None:
            target = grams * ratio
            result.update({
                "status": "adjusted",
                "target_measure": f"{format_amount(target)} g",
                "target_grams": round(target, 1),
                "basis": f"{ingredient.measure} {ingredient.name} = {format_amount(grams)} g ({basis})",
                "estimated": True,
            })
            return result
        result["reason"] = "Piece count without a USDA portion weight. Run enrich_recipes for the original first."
    else:
        result["reason"] = "Amount cannot be converted (e.g. 'to taste')."
    result.update({"status": "unverified", "target_measure": ingredient.measure})
    return result
