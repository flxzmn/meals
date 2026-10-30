from datetime import datetime, timezone

from repo.recipe_repo import RecipeRepo
from services.constraint_service import normalize_constraints
from services.measure_service import estimate_grams, normalize_ingredient_name
from services.recipe_service import serialize_recipe


class VariantService:
    """Recipe variants (Sprint 6): adapted copies of a saved recipe, stored with their own ID.

    A variant is a row in recipes with parent_id set, so enrich_recipes, get_nutrition and
    delete_recipes work on variants as well. The original recipe is never changed.
    """

    def __init__(self, session):
        self.repo = RecipeRepo(session)

    def save_variants(self, variants: list[dict]) -> dict:
        saved: list[dict] = []
        existing: list[dict] = []
        errors: list[dict] = []
        parents = {recipe.mealdb_id: recipe for recipe in self.repo.get_bulk(
            [str(item.get("source_mealdb_id", "")) for item in variants]
        )}

        for item in variants:
            source_id = str(item.get("source_mealdb_id", "")).strip()
            parent = parents.get(source_id)
            if parent is None:
                errors.append({"source_mealdb_id": source_id, "reason": "Source recipe is not saved. Call save_recipes first."})
                continue
            ingredients, problem = self._ingredients(item.get("ingredients"))
            if problem:
                errors.append({"source_mealdb_id": source_id, "reason": problem})
                continue

            constraints = normalize_constraints(item.get("constraints"))
            instructions = item.get("instructions", parent.instructions)
            duplicate = self._find_duplicate(parent, constraints, ingredients, instructions)
            if duplicate:
                existing.append(serialize_recipe(duplicate, full=False))
                continue

            variant = self.repo.add_variant(
                parent,
                name=str(item.get("name") or f"{parent.name} (adapted)"),
                instructions=instructions,
                instructions_source="original" if instructions == parent.instructions else "edited",
                constraints=constraints,
                changes=compute_changes(parent, ingredients, item.get("changes")),
                ingredients=ingredients,
            )
            saved.append(serialize_recipe(variant, full=False))

        return {
            "status": "saved" if saved else ("existing" if existing else "nothing_saved"),
            "saved": saved,
            "existing": existing,
            "errors": errors,
            "note": "Variants have their own mealdb_id and work with get_recipes, get_nutrition and delete_recipes. "
                    "The original recipes remain unchanged.",
        }

    def list_variants(self, source_mealdb_ids: list[str] | None = None) -> list[dict]:
        return [serialize_recipe(variant, full=False) for variant in self.repo.list_variants(source_mealdb_ids)]

    def update_variants(self, updates: list[dict]) -> dict:
        updated: list[dict] = []
        errors: list[dict] = []
        recipes = {recipe.mealdb_id: recipe for recipe in self.repo.get_bulk(
            [str(item.get("mealdb_id", "")) for item in updates]
        )}

        for item in updates:
            mealdb_id = str(item.get("mealdb_id", "")).strip()
            variant = recipes.get(mealdb_id)
            if variant is None:
                errors.append({"mealdb_id": mealdb_id, "reason": "Recipe not found."})
                continue
            if variant.parent_id is None:
                errors.append({"mealdb_id": mealdb_id, "reason": "Original recipes cannot be changed. Save a variant with save_adapted_recipes."})
                continue

            if "ingredients" in item:
                ingredients, problem = self._ingredients(item["ingredients"])
                if problem:
                    errors.append({"mealdb_id": mealdb_id, "reason": problem})
                    continue
                known = list(variant.changes or []) + list(item.get("changes") or [])
                self.repo.replace_ingredients(variant, ingredients)
                variant.changes = compute_changes(variant.parent, ingredients, known)
            if item.get("name"):
                variant.name = str(item["name"])
            if "instructions" in item:
                variant.instructions = item["instructions"]
                variant.instructions_source = "edited"
            if "constraints" in item:
                variant.constraints = normalize_constraints(item["constraints"])
            variant.updated_at = datetime.now(timezone.utc)
            updated.append(serialize_recipe(variant))

        self.repo.session.flush()
        return {"status": "updated" if updated else "nothing_updated", "updated": updated, "errors": errors}

    @staticmethod
    def _ingredients(items) -> tuple[list[dict], str | None]:
        """Clean ingredient list: names required, positions unique, grams recomputed from the measure."""
        if not items:
            return [], "A variant needs at least one ingredient."
        result: list[dict] = []
        used: set[int] = set()
        for index, item in enumerate(items, start=1):
            name = str((item or {}).get("name") or "").strip()
            if not name:
                return [], f"Ingredient {index} has no name."
            position = item.get("position")
            if not isinstance(position, int) or position in used:
                position = max(used | {0}) + 1
            used.add(position)
            measure = str(item.get("measure") or "").strip()
            result.append({
                "position": position,
                "name": name,
                "normalized_name": normalize_ingredient_name(name),
                "measure": measure,
                "estimated_grams": estimate_grams(measure),
            })
        return sorted(result, key=lambda row: row["position"]), None

    def _find_duplicate(self, parent, constraints: dict, ingredients: list[dict], instructions):
        signature = [(row["normalized_name"], row["measure"].lower()) for row in ingredients]
        for variant in parent.variants:
            same_ingredients = [(row.normalized_name, row.measure.lower()) for row in variant.ingredients] == signature
            if same_ingredients and (variant.constraints or {}) == constraints and variant.instructions == instructions:
                return variant
        return None


def compute_changes(parent, ingredients: list[dict], known: list[dict] | None = None) -> list[dict]:
    """Differences between the original and a variant by ingredient position.

    Reason and confidence of a substitution (from adapt_recipes) are kept when source and target match.
    """
    reasons = {
        (normalize_ingredient_name(str(change.get("source") or "")), normalize_ingredient_name(str(change.get("target") or ""))): change
        for change in known or []
    }
    before = {row.position: row for row in parent.ingredients}
    after = {row["position"]: row for row in ingredients}
    changes: list[dict] = []
    for position in sorted(set(before) | set(after)):
        old, new = before.get(position), after.get(position)
        old_name = old.name if old else None
        new_name = new["name"] if new else None
        old_measure = old.measure if old else None
        new_measure = new["measure"] if new else None
        same_name = old and new and old.normalized_name == new["normalized_name"]
        if same_name and (old_measure or "") == (new_measure or ""):
            continue
        change = {
            "position": position,
            "type": "removed" if new is None else "added" if old is None else "measure" if same_name else "substituted",
            "source": old_name,
            "target": new_name,
            "source_measure": old_measure,
            "target_measure": new_measure,
        }
        previous = reasons.get((normalize_ingredient_name(old_name or ""), normalize_ingredient_name(new_name or "")))
        if previous:
            change.update({key: previous[key] for key in ("reason", "confidence") if previous.get(key) is not None})
        changes.append(change)
    return changes
