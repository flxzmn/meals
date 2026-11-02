import time
from types import SimpleNamespace

from config.settings import settings
from repo.match_rule_repo import CUSTOM_FDC_ID, MatchRuleRepo
from repo.nutrition_repo import NutritionRepo
from repo.recipe_repo import RecipeRepo
from services.measure_service import DENSITY_BASIS, VOLUME_BASIS, estimate_grams, ingredient_grams, normalize_ingredient_name
from services.serving_service import clean_servings
from services.usda_service import USDAConfigurationError, USDAService


NUTRIENTS = ("calories", "protein", "fat", "carbs")
ENRICH_BATCH_SIZE = 16
# From this many recipes on, results leave out per-ingredient detail unless asked for.
COMPACT_ABOVE = 5
# Ingredients without a USDA match wait at the end of the next run, so they cannot block the others.
RETRY_MISSES_AFTER_SECONDS = 600
recent_misses: dict[str, float] = {}


def is_compact(compact: bool | None, count: int) -> bool:
    return count > COMPACT_ABOVE if compact is None else compact


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

        remaining = lookup["remaining"]
        matched_count = len(cached) + len(lookup["matched"])
        processed = len(unique)
        if lookup["errors"]:
            status = "partial_success" if matched_count else "error"
        elif lookup["missing"] or remaining:
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
            "complete": not remaining,
            "remaining_ingredients": remaining,
            "next_step": "Time limit reached, results so far are saved. Call enrich_recipes again with the same IDs." if remaining else None,
        }

    async def calculate(self, ingredients: list[dict], servings: int | None = None) -> dict:
        """Nutrition of free ingredients without a saved recipe: [{name, measure}]."""
        if servings is not None and clean_servings(servings) is None:
            return {"status": "error", "message": "servings must be a whole number of at least 1."}
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
        recipe = SimpleNamespace(mealdb_id=None, name="Ingredients", ingredients=rows, effective_servings=clean_servings(servings))
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
        cached = {
            name: row for name, row in cached.items()
            if row.calories_per_100g is not None or row.usda_fdc_id == CUSTOM_FDC_ID
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

        return cached, await self._lookup_in_batches(lookup_items, refresh)

    async def _lookup_in_batches(self, items: list[dict], refresh: bool) -> dict:
        """Look up in batches and save each one, stopping at the time budget. A refresh starts over on
        every call, so it has no budget and should be called with a few recipes."""
        now = time.monotonic()
        items = sorted(items, key=lambda item: now - recent_misses.get(item["normalized_name"], -1e9) < RETRY_MISSES_AFTER_SECONDS)
        result = {"matched": [], "missing": [], "errors": {}, "remaining": 0}
        started = time.monotonic()
        for start in range(0, len(items), ENRICH_BATCH_SIZE):
            if start and not refresh and time.monotonic() - started > settings.enrich_time_budget_seconds:
                result["remaining"] = len(items) - start
                break
            batch = items[start:start + ENRICH_BATCH_SIZE]
            lookup = await self.usda.get_nutrients_bulk(batch)
            self.nutrition_repo.save_bulk(lookup["matched"])
            self.nutrition_repo.session.commit()
            result["matched"].extend(lookup["matched"])
            result["missing"].extend(lookup["missing"])
            result["errors"].update(lookup["errors"])
            found = {row["normalized_name"] for row in lookup["matched"]}
            for item in batch:
                if item["normalized_name"] in found:
                    recent_misses.pop(item["normalized_name"], None)
                else:
                    recent_misses[item["normalized_name"]] = time.monotonic()
        return result

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
        if nutrition is None:
            return ingredient_grams(ingredient.measure, ingredient.estimated_grams, None)
        return ingredient_grams(ingredient.measure, ingredient.estimated_grams, nutrition.portions, nutrition.matched_name)

    def get_nutrition(self, mealdb_ids: list[str], compact: bool | None = None) -> dict:
        recipes = self.recipe_repo.get_bulk(mealdb_ids)
        cached = self._cached_for(recipes)
        found = {recipe.mealdb_id for recipe in recipes}
        summaries = [self._summarize(recipe, cached) for recipe in recipes]
        if is_compact(compact, len(recipes)):
            for summary in summaries:
                for key in ("covered_ingredients", "ingredient_breakdown", "estimated_volume_conversions", "calculation_note"):
                    del summary[key]
        return {
            "compact": is_compact(compact, len(recipes)),
            "recipes": summaries,
            "missing_recipes": sorted(set(mealdb_ids) - found),
        }

    async def compare_variants(self, mealdb_ids: list[str], enrich: bool = True, compact: bool | None = None) -> dict:
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
        compact = is_compact(compact, len(comparisons))
        if compact:
            for comparison in comparisons:
                comparison["change_effects"] = [effect for effect in comparison["change_effects"] if not effect["counted"]]
                del comparison["uncovered_ingredients"]
        if comparisons and not errors:
            status = "success"
        else:
            status = "partial_success" if comparisons else "error"
        return {
            "status": status,
            "compact": compact,
            "comparisons": comparisons,
            "errors": errors,
            "missing_recipes": sorted(set(mealdb_ids) - found),
            "enrichment_errors": enrichment.get("errors", {}),
            "enrichment_complete": enrichment.get("complete", True),
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
        uncounted = [effect for effect in effects if not effect["counted"]]
        if uncounted:
            uncovered_before = {row["position"]: row for row in before["uncovered_ingredients"]}
            uncovered_after = {row["position"]: row for row in after["uncovered_ingredients"]}
            causes = [self._uncounted_cause(effect, uncovered_before, uncovered_after) for effect in uncounted]
            notes.insert(0, (
                f"Not comparable: {'; '.join(causes)}. Uncounted ingredients count as 0, so partial_difference is "
                "not a result. Missing data can be stored with set_ingredient_matches (USDA fdc_id or values from the "
                "label); an amount that cannot be converted needs a measure in grams (update_recipe_variants for variants)."
            ))
        uncounted = [effect["target"] or effect["source"] for effect in uncounted]
        summary_keys = ("mealdb_id", "recipe_name", *NUTRIENTS, "servings", "per_serving")
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

    @staticmethod
    def _uncounted_cause(effect: dict, before: dict, after: dict) -> str:
        """Which side of a change is not counted and why, e.g. seitan has data but "2 Lbs" beef did not convert."""
        row = after.get(effect["position"])
        side = "substitute"
        name = effect["target"]
        if row is None:
            row, side, name = before.get(effect["position"]), "original", effect["source"]
        if row is None:
            return f"{name} is not counted"
        if row["reason"] == "amount_not_convertible":
            return f"amount '{row['measure']}' of {side} {name} cannot be converted"
        if row["reason"] == "calories_missing":
            return f"no energy value for {side} {name}"
        return f"no nutrition data for {side} {name}"

    def _summarize(self, recipe, cached) -> dict:
        totals = {key: 0.0 for key in NUTRIENTS}
        covered, uncovered, estimated, breakdown = [], [], [], []
        for ingredient in recipe.ingredients:
            nutrition = cached.get(ingredient.normalized_name)
            grams, basis = self._grams(ingredient, nutrition)
            if nutrition is None or grams is None or nutrition.calories_per_100g is None:
                reason = "nutrition_missing" if nutrition is None else "amount_not_convertible" if grams is None else "calories_missing"
                uncovered.append({"position": ingredient.position, "ingredient": ingredient.name, "measure": ingredient.measure, "reason": reason})
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
                "fat": round((nutrition.fat_per_100g or 0.0) * factor, 1),
                "carbs": round((nutrition.carbs_per_100g or 0.0) * factor, 1),
            })
            if basis in (VOLUME_BASIS, DENSITY_BASIS):
                estimated.append(ingredient.name)
        total = len(recipe.ingredients)
        servings = recipe.effective_servings
        return {
            "mealdb_id": recipe.mealdb_id,
            "recipe_name": recipe.name,
            **{key: round(value, 2) for key, value in totals.items()},
            "servings": servings,
            "per_serving": {key: round(value / servings, 1) for key, value in totals.items()} if servings else None,
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
                "USDA average portion weights (see grams_basis); other volumes assume approximately 1 g/ml, dry foods a typical density."
            ),
        }
