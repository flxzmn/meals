import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, select
from sqlalchemy.exc import SQLAlchemyError

from config.settings import settings
from db.models import (
    Ingredient,
    IngredientMatchRule,
    NutritionCache,
    Recipe,
    Substitution,
    SubstitutionFeedback,
    SubstitutionSuggestion,
)

EXPORT_FORMAT = "meal-mcp-export"
EXPORT_VERSION = 1

# Section in the file -> model and the columns that identify a row. An existing row is kept.
TABLES = {
    "nutrition_cache": (NutritionCache, ("normalized_name",)),
    "ingredient_match_rules": (IngredientMatchRule, ("normalized_name",)),
    "substitutions": (Substitution, ("source_ingredient", "target_ingredient")),
    "substitution_feedback": (SubstitutionFeedback, ("source_ingredient", "target_ingredient", "accepted", "constraints_hash")),
    "substitution_suggestions": (SubstitutionSuggestion, ("source_ingredient", "target_ingredient", "constraints_hash")),
}
SKIPPED_COLUMNS = {"id", "recipe_id", "parent_id"}


def row_to_dict(row) -> dict:
    data = {}
    for column in row.__table__.columns:
        if column.name not in SKIPPED_COLUMNS:
            value = getattr(row, column.name)
            data[column.name] = value.isoformat() if isinstance(value, datetime) else value
    return data


def dict_to_values(model, data: dict) -> dict:
    values = {}
    for column in model.__table__.columns:
        if column.name in SKIPPED_COLUMNS or column.name not in data:
            continue
        value = data[column.name]
        values[column.name] = datetime.fromisoformat(value) if isinstance(column.type, DateTime) and value else value
    return values


class DataService:
    """Backup as a JSON file: recipes with variants, substitutions, decisions, matches and label values.

    The USDA key is not part of the database and therefore never part of an export.
    """

    def __init__(self, session):
        self.session = session

    def export_data(self, path: str | None = None) -> dict:
        target = Path(path).expanduser() if path else self._default_path()
        if target.suffix.lower() != ".json":
            return {"status": "error", "message": "The export file must end in .json."}
        if target.exists():
            return {"status": "error", "message": f"{target} already exists and is not overwritten."}

        recipes = list(self.session.scalars(select(Recipe).order_by(Recipe.mealdb_id)))
        data = {"format": EXPORT_FORMAT, "version": EXPORT_VERSION, "exported_at": datetime.now(timezone.utc).isoformat()}
        data["recipes"] = [self._recipe_to_dict(recipe) for recipe in recipes]
        for section, (model, _) in TABLES.items():
            data[section] = [row_to_dict(row) for row in self.session.scalars(select(model))]

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return {
            "status": "exported",
            "path": str(target),
            "counts": {section: len(data[section]) for section in ("recipes", *TABLES)},
            "note": "The file holds no API key. Import it with import_data, also on another computer.",
        }

    def import_data(self, path: str) -> dict:
        source = Path(path).expanduser()
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return {"status": "error", "message": f"Cannot read {source}: {exc}"}
        if not isinstance(data, dict) or data.get("format") != EXPORT_FORMAT:
            return {"status": "error", "message": f"{source} is not a Meal MCP export."}
        if not isinstance(data.get("version"), int) or data["version"] > EXPORT_VERSION:
            return {"status": "error", "message": f"Export version {data.get('version')} is not supported. Update Meal MCP."}

        try:
            with self.session.begin_nested():
                result = {"recipes": self._import_recipes(data.get("recipes") or [])}
                errors = result["recipes"].pop("errors")
                for section, (model, key) in TABLES.items():
                    result[section] = self._import_rows(model, key, data.get(section) or [])
        except (SQLAlchemyError, AttributeError, KeyError, TypeError, ValueError) as exc:
            return {"status": "error", "message": f"Nothing was imported, the file is damaged: {exc}"}
        return {"status": "partial_success" if errors else "imported", "imported": result, "errors": errors}

    @staticmethod
    def _default_path() -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return settings.meal_data_dir / "exports" / f"meal-export-{stamp}.json"

    @staticmethod
    def _recipe_to_dict(recipe: Recipe) -> dict:
        data = row_to_dict(recipe)
        data["parent_mealdb_id"] = recipe.parent.mealdb_id if recipe.parent else None
        data["ingredients"] = [row_to_dict(row) for row in recipe.ingredients]
        return data

    def _import_recipes(self, rows: list[dict]) -> dict:
        added, kept, errors = 0, 0, []
        # Originals first, so that variants find their parent.
        for row in sorted(rows, key=lambda item: item.get("parent_mealdb_id") is not None):
            mealdb_id = row["mealdb_id"]
            if self.session.scalar(select(Recipe.id).where(Recipe.mealdb_id == mealdb_id)):
                kept += 1
                continue
            parent_id = row.get("parent_mealdb_id")
            parent = self.session.scalar(select(Recipe).where(Recipe.mealdb_id == parent_id)) if parent_id else None
            if parent_id and parent is None:
                errors.append({"mealdb_id": mealdb_id, "reason": f"Original {parent_id} is missing."})
                continue
            recipe = Recipe(**dict_to_values(Recipe, row))
            recipe.ingredients = [Ingredient(**dict_to_values(Ingredient, item)) for item in row.get("ingredients") or []]
            if parent:
                parent.variants.append(recipe)
            else:
                self.session.add(recipe)
            self.session.flush()
            added += 1
        return {"added": added, "kept": kept, "errors": errors}

    def _import_rows(self, model, key: tuple[str, ...], rows: list[dict]) -> dict:
        added, kept = 0, 0
        for row in rows:
            match = select(model.id).where(*(getattr(model, column) == row[column] for column in key))
            if self.session.scalar(match):
                kept += 1
                continue
            self.session.add(model(**dict_to_values(model, row)))
            self.session.flush()
            added += 1
        return {"added": added, "kept": kept}
