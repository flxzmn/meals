from __future__ import annotations

import hashlib
import json

from services.measure_service import normalize_ingredient_name

LIST_KEYS = ("required_tags", "dislikes", "allergies", "excluded_ingredients")
EXCLUSION_KEYS = ("dislikes", "allergies", "excluded_ingredients")


def normalize_constraints(constraints: dict | None) -> dict:
    """Return a canonical constraints dict: lower case, sorted lists, no empty values."""
    constraints = constraints or {}
    normalized: dict = {}
    for key, value in constraints.items():
        if key in LIST_KEYS:
            values = value if isinstance(value, list) else [value]
            items = sorted({normalize_ingredient_name(str(item)) for item in values if str(item).strip()})
            if items:
                normalized[key] = items
        elif isinstance(value, str):
            if value.strip():
                normalized[key] = normalize_ingredient_name(value)
        elif value not in (None, [], {}):
            normalized[key] = value
    return normalized


def constraints_hash(constraints: dict | None) -> str:
    canonical = json.dumps(normalize_constraints(constraints), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def required_tags(constraints: dict | None) -> set[str]:
    constraints = normalize_constraints(constraints)
    tags = set(constraints.get("required_tags", []))
    if constraints.get("diet"):
        tags.add(constraints["diet"])
    return tags


def excluded_terms(constraints: dict | None) -> set[str]:
    constraints = normalize_constraints(constraints)
    return {value for key in EXCLUSION_KEYS for value in constraints.get(key, [])}


def constraint_violation(candidate: dict, constraints: dict | None) -> str | None:
    """Return why a candidate violates the constraints, or None if it is allowed."""
    source = normalize_ingredient_name(str(candidate.get("source_ingredient", "")))
    target = normalize_ingredient_name(str(candidate.get("target_ingredient", "")))
    if not target:
        return "Missing target ingredient"
    if source and target == source:
        return "Target equals source ingredient"

    for term in sorted(excluded_terms(constraints)):
        if term in target or target in term:
            return f"Excluded by user constraint: {term}"

    tags = {normalize_ingredient_name(str(tag)) for tag in candidate.get("tags") or []}
    missing = sorted(required_tags(constraints) - tags)
    if missing:
        return f"Missing required tags: {', '.join(missing)}"
    return None


def label_check_note(candidate: dict, constraints: dict | None) -> str | None:
    """Tags are metadata only. Safety-relevant tags must be verified on the concrete product."""
    constraints = normalize_constraints(constraints)
    tags = {normalize_ingredient_name(str(tag)) for tag in candidate.get("tags") or []}
    relevant = sorted(
        {tag for tag in required_tags(constraints) | tags if tag.endswith(" free")}
        | {f"{allergen} free" for allergen in constraints.get("allergies", [])}
    )
    if not relevant:
        return None
    return (
        "Tags are metadata, not a product safety guarantee. "
        f"Check the concrete product label for: {', '.join(relevant)}."
    )
