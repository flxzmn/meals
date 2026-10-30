import re
from datetime import datetime, timezone

from repo.recipe_repo import RecipeRepo
from services.measure_service import normalize_ingredient_name
from services.recipe_service import serialize_recipe

QUALIFIER_STOPWORDS = {"a", "an", "and", "for", "of", "or", "the", "to", "with"}

GUIDELINES = [
    "Replace every mention of a replaced ingredient with its substitute.",
    "Adapt cooking times, temperatures and steps to the substitute "
    "(e.g. tempeh or tofu need far less time than raw chicken; plant milk can split when boiled hard).",
    "Use the measures from the ingredient list of the variant.",
    "Do not add ingredients that are not in the ingredient list.",
    "Keep steps that are not affected unchanged and keep the language of the original.",
    "Do not promise allergy safety; tags such as 'nut free' must be checked on the product label.",
]


class InstructionService:
    """Instruction rewriter (Sprint 7).

    Claude Desktop is the LLM: rewrite_requests returns a structured job per variant, Claude writes the
    new instructions and save_rewrites stores them, checks them and marks them as LLM-generated.
    The original recipe keeps its instructions.
    """

    def __init__(self, session):
        self.repo = RecipeRepo(session)

    def rewrite_requests(self, mealdb_ids: list[str], force: bool = False) -> dict:
        recipes = {recipe.mealdb_id: recipe for recipe in self.repo.get_bulk(mealdb_ids)}
        requests, up_to_date, errors = [], [], []
        for mealdb_id in dict.fromkeys(mealdb_ids):
            variant = recipes.get(mealdb_id)
            problem = self._problem(variant)
            if problem:
                errors.append({"mealdb_id": mealdb_id, "reason": problem})
                continue
            changes = [change for change in variant.changes or [] if change["type"] != "measure"]
            if not changes:
                up_to_date.append({"mealdb_id": mealdb_id, "reason": "No ingredient was replaced, added or removed."})
                continue
            if variant.instructions_source == "llm" and not force:
                up_to_date.append({"mealdb_id": mealdb_id, "reason": "Already rewritten. Use force=true to rewrite again."})
                continue
            replaced = replaced_terms(variant)
            requests.append({
                "mealdb_id": mealdb_id,
                "name": variant.name,
                "current_instructions": variant.instructions or "",
                "original_instructions": variant.parent.instructions or "",
                "changes": [
                    {key: change.get(key) for key in ("type", "source", "target", "source_measure", "target_measure", "reason")}
                    for change in changes
                ],
                "ingredients": [{"name": row.name, "measure": row.measure} for row in variant.ingredients],
                "replaced_terms": replaced,
                "still_mentioned": mentioned_terms(variant.instructions or "", replaced, ingredient_names(variant), substitute_names(variant)),
            })
        return {
            "status": "rewrite_required" if requests else "nothing_to_rewrite",
            "requests": requests,
            "up_to_date": up_to_date,
            "errors": errors,
            "guidelines": GUIDELINES if requests else [],
            "next_tool": "save_rewritten_instructions" if requests else None,
        }

    def save_rewrites(self, rewrites: list[dict]) -> dict:
        recipes = {recipe.mealdb_id: recipe for recipe in self.repo.get_bulk(
            [str(item.get("mealdb_id", "")) for item in rewrites]
        )}
        saved, warnings, errors = [], [], []
        for item in rewrites:
            mealdb_id = str(item.get("mealdb_id", "")).strip()
            variant = recipes.get(mealdb_id)
            problem = self._problem(variant)
            text = str(item.get("instructions") or "").strip()
            if not problem and not text:
                problem = "Instructions are empty."
            if problem:
                errors.append({"mealdb_id": mealdb_id, "reason": problem})
                continue
            still = mentioned_terms(text, replaced_terms(variant), ingredient_names(variant), substitute_names(variant))
            if still:
                warnings.append({
                    "mealdb_id": mealdb_id,
                    "still_mentioned": still,
                    "warning": "The new instructions still mention replaced ingredients. Check them or rewrite again.",
                })
            variant.instructions = text
            variant.instructions_source = "llm"
            variant.updated_at = datetime.now(timezone.utc)
            saved.append(serialize_recipe(variant))
        self.repo.session.flush()
        return {
            "status": "saved" if saved else "nothing_saved",
            "saved": saved,
            "warnings": warnings,
            "errors": errors,
            "note": "Instructions marked instructions_source='llm' were written by Claude. Review them before cooking.",
        }

    @staticmethod
    def _problem(recipe) -> str | None:
        if recipe is None:
            return "Recipe not found."
        if recipe.parent_id is None:
            return "Only variants can be rewritten. The original recipe keeps its instructions."
        return None


def replaced_terms(variant) -> list[str]:
    """Names of ingredients that were replaced or removed and are not part of the variant."""
    remaining = {row.normalized_name for row in variant.ingredients}
    terms = {
        normalize_ingredient_name(change["source"])
        for change in variant.changes or []
        if change["type"] in ("substituted", "removed") and change.get("source")
    }
    return sorted(term for term in terms if term not in remaining)


def ingredient_names(variant) -> list[str]:
    return [row.normalized_name for row in variant.ingredients]


def substitute_names(variant) -> list[str]:
    return [change["target"] for change in variant.changes or [] if change["type"] in ("substituted", "added") and change.get("target")]


def mentioned_terms(text: str, terms: list[str], keep: list[str] | None = None, substitutes: list[str] | None = None) -> list[str]:
    """Terms that appear in the text as words, also in plural ("chicken" in "Chickens").

    Names in keep (the variant's ingredients) are blanked first, so "milk" is not found in "oat milk".
    A term directly after a word of a substitute also does not count: the ingredient "oat yogurt, plain"
    may be written as "plain oat yogurt", and "oat cream for cooking" as "oat cooking cream".
    """
    lowered = text.lower()
    for name in sorted(keep or [], key=len, reverse=True):
        lowered = re.sub(rf"\b{re.escape(name)}(?:s|es)?\b", " ", lowered)
    qualifiers = {word for name in substitutes or [] for word in _words(name)} - QUALIFIER_STOPWORDS
    found = []
    for term in terms:
        for match in re.finditer(rf"\b{re.escape(term)}(?:s|es)?\b", lowered):
            before = _words(lowered[:match.start()])
            if not before or before[-1] not in qualifiers - set(_words(term)):
                found.append(term)
                break
    return found


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zäöüß]+", text.lower())
