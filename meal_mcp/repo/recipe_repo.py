from sqlalchemy import select
from sqlalchemy.orm import selectinload
from db.models import Ingredient, Recipe
from services.measure_service import estimate_grams, normalize_ingredient_name


class RecipeRepo:
    def __init__(self, session):
        self.session = session

    def save_bulk(self, meals: list[dict]) -> dict:
        saved, existing, missing = [], [], []
        for meal in meals:
            meal_id = str(meal.get("idMeal", "")).strip()
            if not meal_id:
                missing.append("unknown")
                continue
            current = self.session.scalar(select(Recipe).where(Recipe.mealdb_id == meal_id))
            if current:
                existing.append(meal_id)
                continue
            recipe = Recipe(
                mealdb_id=meal_id,
                name=meal.get("strMeal") or "Unnamed recipe",
                category=meal.get("strCategory"),
                area=meal.get("strArea"),
                instructions=meal.get("strInstructions"),
                image_url=meal.get("strMealThumb"),
            )
            for position in range(1, 21):
                name = (meal.get(f"strIngredient{position}") or "").strip()
                if not name:
                    continue
                measure = (meal.get(f"strMeasure{position}") or "").strip()
                recipe.ingredients.append(Ingredient(
                    position=position,
                    name=name,
                    normalized_name=normalize_ingredient_name(name),
                    measure=measure,
                    estimated_grams=estimate_grams(measure),
                ))
            self.session.add(recipe)
            saved.append(meal_id)
        self.session.flush()
        return {"saved": saved, "existing": existing, "missing": missing}

    def list_all(self) -> list[Recipe]:
        statement = select(Recipe).options(selectinload(Recipe.ingredients)).order_by(Recipe.name)
        return list(self.session.scalars(statement).all())

    def get_bulk(self, mealdb_ids: list[str]) -> list[Recipe]:
        if not mealdb_ids:
            return []
        statement = select(Recipe).options(selectinload(Recipe.ingredients)).where(Recipe.mealdb_id.in_(mealdb_ids))
        return list(self.session.scalars(statement).all())

    def delete_bulk(self, mealdb_ids: list[str]) -> dict:
        recipes = self.get_bulk(mealdb_ids)
        found = {recipe.mealdb_id for recipe in recipes}
        # Deleting an original also deletes its variants.
        with_variants = sorted(
            variant.mealdb_id for recipe in recipes for variant in recipe.variants if variant.mealdb_id not in found
        )
        for recipe in recipes:
            if recipe.parent is None:
                self.session.delete(recipe)
            elif recipe.parent.mealdb_id not in found:
                # Remove it from the parent's collection too (delete-orphan deletes the row),
                # so the parent does not delete it a second time later in this session.
                recipe.parent.variants.remove(recipe)
        self.session.flush()
        return {"deleted": sorted(found), "deleted_variants": with_variants, "missing": sorted(set(mealdb_ids) - found)}

    def add_variant(self, parent: Recipe, name: str, instructions: str | None, constraints: dict,
                    changes: list[dict], ingredients: list[dict], instructions_source: str = "original") -> Recipe:
        number = len(parent.variants) + 1
        while self.session.scalar(select(Recipe.id).where(Recipe.mealdb_id == f"{parent.mealdb_id}-v{number}")):
            number += 1
        variant = Recipe(
            mealdb_id=f"{parent.mealdb_id}-v{number}",
            name=name,
            category=parent.category,
            area=parent.area,
            instructions=instructions,
            instructions_source=instructions_source,
            image_url=parent.image_url,
            constraints=constraints,
            changes=changes,
            ingredients=[Ingredient(**row) for row in ingredients],
        )
        parent.variants.append(variant)
        self.session.flush()
        return variant

    def replace_ingredients(self, recipe: Recipe, ingredients: list[dict]) -> None:
        recipe.ingredients.clear()
        self.session.flush()  # free the (recipe_id, position) pairs before inserting
        recipe.ingredients.extend(Ingredient(**row) for row in ingredients)
        self.session.flush()

    def list_variants(self, parent_mealdb_ids: list[str] | None = None) -> list[Recipe]:
        statement = select(Recipe).options(selectinload(Recipe.ingredients)).where(Recipe.parent_id.is_not(None))
        if parent_mealdb_ids:
            parent_ids = select(Recipe.id).where(Recipe.mealdb_id.in_(parent_mealdb_ids))
            statement = statement.where(Recipe.parent_id.in_(parent_ids))
        return list(self.session.scalars(statement.order_by(Recipe.mealdb_id)).all())
