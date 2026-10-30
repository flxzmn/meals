from repo.match_rule_repo import CUSTOM_FDC_ID, MatchRuleRepo
from repo.nutrition_repo import NutritionRepo
from services.measure_service import normalize_ingredient_name
from services.usda_service import USDAConfigurationError, USDAService


class MatchService:
    """Manual correction of USDA matches (Sprint 10).

    search_foods shows candidates, set_matches pins a chosen food to an ingredient and
    reject_matches blocks a wrong food and looks for the next best one. Decisions are stored as
    rules, so enrich_recipes with refresh=true keeps them.
    """

    def __init__(self, session):
        self.rules = MatchRuleRepo(session)
        self.nutrition_repo = NutritionRepo(session)
        self.usda = USDAService()

    async def search_foods(self, queries: list[str]) -> dict:
        clean = list(dict.fromkeys(query.strip() for query in queries if query and query.strip()))
        try:
            return await self.usda.search_foods(clean)
        except USDAConfigurationError as exc:
            return {"results": {}, "errors": {"configuration": str(exc)}}

    async def set_matches(self, matches: list[dict]) -> dict:
        items, errors, custom = [], [], []
        for match in matches:
            name = normalize_ingredient_name(str(match.get("ingredient") or ""))
            fdc_id = str(match.get("fdc_id") or "").strip()
            if name and not fdc_id and match.get("calories_per_100g") is not None:
                row, problem = self._custom_row(name, match)
                if problem:
                    errors.append({"ingredient": match.get("ingredient"), "reason": problem})
                    continue
                self.rules.set_choice(name, CUSTOM_FDC_ID, match.get("note"))
                self.nutrition_repo.save_bulk([row])
                custom.append(self._summary(row, "manual"))
                continue
            if not name or not fdc_id:
                errors.append({"ingredient": match.get("ingredient"), "reason": "ingredient and fdc_id or calories_per_100g are required."})
                continue
            items.append({"source_name": str(match["ingredient"]), "normalized_name": name, "fdc_id": fdc_id, "note": match.get("note")})

        lookup = await self._lookup(items, errors)
        updated = custom
        found = {row["normalized_name"]: row for row in lookup["matched"]}
        for item in items:
            row = found.get(item["normalized_name"])
            if row is None:
                errors.append({"ingredient": item["source_name"], "reason": f"USDA food {item['fdc_id']} not found."})
                continue
            self.rules.set_choice(item["normalized_name"], item["fdc_id"], item["note"])
            self.nutrition_repo.save_bulk([row])
            updated.append(self._summary(row, "manual"))
        return {"status": "updated" if updated else "nothing_updated", "updated": updated, "errors": errors}

    async def reject_matches(self, rejections: list[dict]) -> dict:
        names = [normalize_ingredient_name(str(item.get("ingredient") or "")) for item in rejections]
        cached = self.nutrition_repo.get_cached_bulk([name for name in names if name])
        rejected, items, errors = [], [], []
        for item, name in zip(rejections, names):
            current = cached.get(name)
            fdc_id = str(item.get("fdc_id") or (current.usda_fdc_id if current else "")).strip()
            if not name or not fdc_id:
                errors.append({"ingredient": item.get("ingredient"), "reason": "No current match to reject. Pass fdc_id."})
                continue
            rule = self.rules.add_rejection(name, fdc_id, item.get("note"))
            rejected.append({"ingredient": name, "rejected_fdc_id": fdc_id, "rejected_match": current.matched_name if current and current.usda_fdc_id == fdc_id else None})
            self.nutrition_repo.delete_bulk([name])
            items.append({
                "source_name": current.source_name if current else str(item["ingredient"]),
                "normalized_name": name,
                "fdc_id": rule.fdc_id,
                "exclude_fdc_ids": rule.rejected_fdc_ids,
            })

        lookup = await self._lookup(items, errors)
        self.nutrition_repo.save_bulk(lookup["matched"])
        return {
            "status": "rejected" if rejected else "nothing_rejected",
            "rejected": rejected,
            "new_matches": [self._summary(row, "auto") for row in lookup["matched"]],
            "no_alternative": lookup["missing"],
            "errors": errors,
            "next_step": "Check new_matches. Use search_usda_foods and set_ingredient_matches to choose a food by hand.",
        }

    @staticmethod
    def _custom_row(name: str, match: dict) -> tuple[dict | None, str | None]:
        """Cache row for values entered by hand. Missing protein, fat or carbs stay unknown."""
        values = {}
        for key in ("calories_per_100g", "protein_per_100g", "fat_per_100g", "carbs_per_100g"):
            value = match.get(key)
            if value is None:
                values[key] = None
                continue
            try:
                values[key] = float(value)
            except (TypeError, ValueError):
                return None, f"{key} must be a number."
            if values[key] < 0:
                return None, f"{key} must not be negative."
        return {
            "normalized_name": name,
            "source_name": str(match["ingredient"]),
            "usda_fdc_id": CUSTOM_FDC_ID,
            "matched_name": f"{match['ingredient']} (custom values)",
            "portions": [],
            **values,
        }, None

    def list_matches(self, ingredients: list[str] | None = None) -> list[dict]:
        names = [normalize_ingredient_name(value) for value in ingredients or []]
        if names:
            rules = self.rules.get_bulk(names)
            cached = self.nutrition_repo.get_cached_bulk(names)
        else:
            rules = {row.normalized_name: row for row in self.rules.list_all()}
            cached = {row.normalized_name: row for row in self.nutrition_repo.list_all()}
        result = []
        for name in names or sorted(set(rules) | set(cached)):
            row, rule = cached.get(name), rules.get(name)
            entry = {"ingredient": name, "usda_match": None, "fdc_id": None, "source": None}
            if row is not None:
                entry.update(self._summary(row, "manual" if rule and rule.fdc_id == row.usda_fdc_id else "auto"))
            entry["rejected_fdc_ids"] = (rule.rejected_fdc_ids or []) if rule else []
            entry["note"] = rule.note if rule else None
            result.append(entry)
        return result

    async def _lookup(self, items: list[dict], errors: list[dict]) -> dict:
        if not items:
            return {"matched": [], "missing": [], "errors": {}}
        try:
            lookup = await self.usda.get_nutrients_bulk(items)
        except USDAConfigurationError as exc:
            errors.append({"ingredient": None, "reason": str(exc)})
            return {"matched": [], "missing": [], "errors": {}}
        errors.extend({"ingredient": name, "reason": reason} for name, reason in lookup["errors"].items())
        return lookup

    @staticmethod
    def _summary(row, source: str) -> dict:
        get = row.get if isinstance(row, dict) else lambda key: getattr(row, key)
        return {
            "ingredient": get("normalized_name"),
            "usda_match": get("matched_name"),
            "fdc_id": get("usda_fdc_id"),
            "source": source,
            "calories_per_100g": get("calories_per_100g"),
            "protein_per_100g": get("protein_per_100g"),
        }
