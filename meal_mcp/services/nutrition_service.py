from types import SimpleNamespace

from repo.match_rule_repo import CUSTOM_FDC_ID, MatchRuleRepo
from repo.nutrition_repo import NutritionRepo
from repo.recipe_repo import RecipeRepo
from services.measure_service import VOLUME_BASIS, estimate_grams, ingredient_grams, normalize_ingredient_name
from services.usda_service import USDAConfigurationError, USDAService


NUTRIENTS = ("calories", "protein", "fat", "carbs")


class NutritionService:
    def __init__(self, session):
        self.recipe_repo = RecipeRepo(session)
        self.nutrition_repo = NutritionRepo(session)
        self.match_rules = MatchRuleRepo(session)
        self.usda = USDAService()

    async def enrich_recipes(self, mealdb_ids: list[str], refresh: bool = False) -> dict:
        recipes = self.recipe_repo.get_bulk(mealdb_ids)
        found_ids = {recipe.mealdb_id for recipe in recipes}
        missing_recipes = sorted(set(mealdb_ids) - found_ids)

        unique = {}
        for recipe in recipes:
            for ingredient in recipe.ingredients:
                unique.setdefault(ingredient.normalized_name, ingredient.name)

        try:
            cached, lookup = await self._load(unique, refresh)
        except USDAConfigurationError as exc:
            return {
                "status": "configuration_error",
                "message": str(exc),
                "recipes_processed": len(recipes),
                "missing_recipes": missing_recipes,
            }

        matched_count = len(cached) + len(lookup["matched"])
        processed = len(unique)
        if lookup["errors"]:
            status = "partial_success" if matched_count else "error"
        elif lookup["missing"]:
            status = "partial_success"
        else:
            status = "success"
        return {
            "status": status,
            "recipes_processed": len(recipes),
            "ingredients_processed": processed,
            "ingredients_from_cache": len(cached),
            "ingredients_loaded_from_usda": len(lookup["matched"]),
            "ingredients_matched": matched_count,
            "ingredients_missing": len(lookup["missing"]),
            "missing_ingredients": lookup["missing"],
            "missing_recipes": missing_recipes,
            "errors": lookup["errors"],
        }

    async def calculate(self, ingredients: list[dict]) -> dict:
        """Nutrition of free ingredients without a saved recipe: [{name, measure}]."""
        rows, invalid, unique = [], [], {}
        for position, item in enumerate(ingredients, start=1):
            name = str((item or {}).get("name") or "").strip()
            if not name:
                invalid.append(item)
                continue
            measure = str(item.get("measure") or "").strip()
            normalized = normalize_ingredient_name(name)
            unique.setdefault(normalized, name)
            rows.append(SimpleNamespace(
                position=position, name=name, normalized_name=normalized,
                measure=measure, estimated_grams=estimate_grams(measure),
            ))
        try:
            _, lookup = await self._load(unique)
        except USDAConfigurationError as exc:
            return {"status": "configuration_error", "message": str(exc)}
        recipe = SimpleNamespace(mealdb_id=None, name="Ingredients", ingredients=rows)
        summary = self._summarize(recipe, self._cached_for([recipe]))
        del summary["mealdb_id"], summary["recipe_name"]
        return {**summary, "invalid": invalid, "errors": lookup["errors"]}

    async def _load(self, unique: dict[str, str], refresh: bool = False) -> tuple[dict, dict]:
        """Look up ingredients that are not usable from the cache. Returns (kept cache rows, lookup result)."""
        rules = self.match_rules.get_bulk(list(unique))
        cached = self.nutrition_repo.get_cached_bulk(list(unique))
        if refresh:
            # Custom values do not come from USDA, so there is nothing to refresh.
            cached = {name: row for name, row in cached.items() if row.usda_fdc_id == CUSTOM_FDC_ID}
        # Entries cached before v0.5.3 have no portion weights yet, and entries that contradict a
        # manual match rule are outdated; look them up again.
        cached = {
            name: row for name, row in cached.items()
            if row.portions is not None and self._follows_rule(row, rules.get(name))
        }
        lookup_items = []
        for name, source in unique.items():
            if name in cached:
                continue
            item = {"normalized_name": name, "source_name": source}
            rule = rules.get(name)
            if rule is not None:
                item.update({"fdc_id": rule.fdc_id, "exclude_fdc_ids": rule.rejected_fdc_ids or []})
            lookup_items.append(item)

        lookup = await self.usda.get_nutrients_bulk(lookup_items) if lookup_items else {"matched": [], "missing": [], "errors": {}}
        self.nutrition_repo.save_bulk(lookup["matched"])
        return cached, lookup

    @staticmethod
    def _follows_rule(row, rule) -> bool:
        if rule is None:
            return True
        if rule.fdc_id:
            return row.usda_fdc_id == rule.fdc_id
        return row.usda_fdc_id not in (rule.rejected_fdc_ids or [])

    @staticmethod
    def _grams(ingredient, nutrition) -> tuple[float | None, str | None]:
        """Grams of an ingredient and how they were derived."""
        return ingredient_grams(ingredient.measure, ingredient.estimated_grams, nutrition.portions if nutrition else None)

    def get_nutrition(self, mealdb_ids: list[str]) -> dict:
        recipes = self.recipe_repo.get_bulk(mealdb_ids)
        cached = self._cached_for(recipes)
        found = {recipe.mealdb_id for recipe in recipes}
        return {
            "recipes": [self._summarize(recipe, cached) for recipe in recipes],
            "missing_recipes": sorted(set(mealdb_ids) - found),
        }

    async def compare_variants(self, mealdb_ids: list[str], enrich: bool = True) -> dict:
        """Compare each variant with its original (Sprint 9). An original ID compares all its variants."""
        recipes = self.recipe_repo.get_bulk(mealdb_ids)
        found = {recipe.mealdb_id for recipe in recipes}
        pairs, errors = [], []
        for recipe in recipes:
            if recipe.parent is not None:
                pairs.append((recipe.parent, recipe))
            elif recipe.variants:
                pairs.extend((recipe, variant) for variant in recipe.variants)
            else:
                errors.append({"mealdb_id": recipe.mealdb_id, "reason": "Original recipe without variants. Save a variant first."})
        pairs = list(dict.fromkeys(pairs))

        enrichment = {}
        if enrich and pairs:
            ids = list(dict.fromkeys(recipe.mealdb_id for pair in pairs for recipe in pair))
            enrichment = await self.enrich_recipes(ids)
            if enrichment.get("status") == "configuration_error":
                errors.append({"mealdb_id": None, "reason": enrichment["message"]})

        cached = self._cached_for([recipe for pair in pairs for recipe in pair])
        comparisons = [self._compare(original, variant, cached) for original, variant in pairs]
        if comparisons and not errors:
            status = "success"
        else:
            status = "partial_success" if comparisons else "error"
        return {
            "status": status,
            "comparisons": comparisons,
            "errors": errors,
            "missing_recipes": sorted(set(mealdb_ids) - found),
            "enrichment_errors": enrichment.get("errors", {}),
        }

    def _cached_for(self, recipes) -> dict:
        names = sorted({ingredient.normalized_name for recipe in recipes for ingredient in recipe.ingredients})
        return self.nutrition_repo.get_cached_bulk(names)

    def _compare(self, original, variant, cached) -> dict:
        before = self._summarize(original, cached)
        after = self._summarize(variant, cached)
        difference = {}
        for key in NUTRIENTS:
            absolute = round(after[key] - before[key], 2)
            percent = round(absolute / before[key] * 100, 1) if before[key] else None
            difference[key] = {"absolute": absolute, "percent": percent}

        notes = []
        if before["coverage"]["percent"] < 100 or after["coverage"]["percent"] < 100:
            notes.append("Not all ingredients are counted (see uncovered_ingredients). Differences can come from missing data.")
        rows_before = {row["position"]: row for row in before["ingredient_breakdown"]}
        rows_after = {row["position"]: row for row in after["ingredient_breakdown"]}
        effects = []
        for change in variant.changes or []:
            old = rows_before.get(change["position"])
            new = rows_after.get(change["position"])
            effects.append({
                "position": change["position"],
                "type": change["type"],
                "source": change.get("source"),
                "target": change.get("target"),
                "calories_before": old["calories"] if old else None,
                "calories_after": new["calories"] if new else None,
                "protein_before": old["protein"] if old else None,
                "protein_after": new["protein"] if new else None,
                # False if one side is not counted, e.g. no USDA data for the substitute.
                "counted": (old is not None or change["type"] == "added") and (new is not None or change["type"] == "removed"),
            })
        # A replaced ingredient that counts as 0 would make the variant look far better than it is.
        uncounted = [effect["target"] or effect["source"] for effect in effects if not effect["counted"]]
        if uncounted:
            notes.insert(0, (
                f"Not comparable: no nutrition data for {', '.join(uncounted)}. These count as 0, so partial_difference "
                "is too low. Store values with set_ingredient_matches (USDA fdc_id or values from the label)."
            ))
        summary_keys = ("mealdb_id", "recipe_name", *NUTRIENTS)
        return {
            "original": {key: before[key] for key in summary_keys},
            "variant": {key: after[key] for key in summary_keys},
            "comparable": not uncounted,
            "difference": None if uncounted else difference,
            "partial_difference": difference if uncounted else None,
            "coverage": {"original": before["coverage"], "variant": after["coverage"]},
            "change_effects": effects,
            "uncovered_ingredients": {"original": before["uncovered_ingredients"], "variant": after["uncovered_ingredients"]},
            "notes": notes,
        }

    def _summarize(self, recipe, cached) -> dict:
        totals = {key: 0.0 for key in NUTRIENTS}
        covered, uncovered, estimated, breakdown = [], [], [], []
        for ingredient in recipe.ingredients:
            nutrition = cached.get(ingredient.normalized_name)
            grams, basis = self._grams(ingredient, nutrition)
            if nutrition is None or grams is None:
                uncovered.append({"ingredient": ingredient.name, "measure": ingredient.measure, "reason": "nutrition_missing" if nutrition is None else "amount_not_convertible"})
                continue
            factor = grams / 100.0
            totals["calories"] += (nutrition.calories_per_100g or 0.0) * factor
            totals["protein"] += (nutrition.protein_per_100g or 0.0) * factor
            totals["fat"] += (nutrition.fat_per_100g or 0.0) * factor
            totals["carbs"] += (nutrition.carbs_per_100g or 0.0) * factor
            covered.append(ingredient.name)
            breakdown.append({
                "position": ingredient.position,
                "ingredient": ingredient.name,
                "measure": ingredient.measure,
                "grams": grams,
                "grams_basis": basis,
                "usda_match": nutrition.matched_name,
                "calories": round((nutrition.calories_per_100g or 0.0) * factor, 1),
                "protein": round((nutrition.protein_per_100g or 0.0) * factor, 1),
            })
            if basis == VOLUME_BASIS:
                estimated.append(ingredient.name)
        total = len(recipe.ingredients)
        return {
            "mealdb_id": recipe.mealdb_id,
            "recipe_name": recipe.name,
            **{key: round(value, 2) for key, value in totals.items()},
            "coverage": {
                "covered": len(covered),
                "total": total,
                "percent": round(len(covered) / total * 100, 1) if total else 0.0,
            },
            "covered_ingredients": covered,
            "ingredient_breakdown": breakdown,
            "uncovered_ingredients": uncovered,
            "estimated_volume_conversions": estimated,
            "calculation_note": (
                "Values are estimates. USDA values are scaled from per-100g data. Pieces and spoons use "
                "USDA average portion weights (see grams_basis); other volumes assume approximately 1 g/ml."
            ),
        }
