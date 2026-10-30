from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import delete, select

from db.models import Substitution
from services.measure_service import normalize_ingredient_name


def quantity_fields(item: dict) -> dict | None:
    """quantity_ratio (grams of target per gram of source, default 1:1) and quantity_note of an item.

    None if the ratio is not a positive number.
    """
    ratio = item.get("quantity_ratio")
    if ratio is not None:
        try:
            ratio = float(ratio)
        except (TypeError, ValueError):
            return None
        if ratio <= 0:
            return None
    note = item.get("quantity_note")
    return {"quantity_ratio": ratio, "quantity_note": str(note) if note else None}


class SubstitutionRepo:
    def __init__(self, session):
        self.session = session

    @staticmethod
    def _normalize(value: str) -> str:
        return normalize_ingredient_name(value)

    @staticmethod
    def _serialize(row: Substitution) -> dict:
        return {
            "id": row.id,
            "source_ingredient": row.source_ingredient,
            "target_ingredient": row.target_ingredient,
            "reason": row.reason,
            "confidence": row.confidence,
            "tags": row.tags or [],
            "quantity_ratio": row.quantity_ratio if row.quantity_ratio is not None else 1.0,
            "quantity_note": row.quantity_note,
        }

    def add_bulk(self, substitutions: list[dict]) -> dict:
        created: list[dict] = []
        existing: list[dict] = []
        invalid: list[dict] = []

        for item in substitutions:
            source = self._normalize(str(item.get("source_ingredient", "")))
            target = self._normalize(str(item.get("target_ingredient", "")))
            quantity = quantity_fields(item)
            if not source or not target or quantity is None:
                invalid.append(item)
                continue

            row = self.session.scalar(
                select(Substitution).where(
                    Substitution.source_ingredient == source,
                    Substitution.target_ingredient == target,
                )
            )
            if row is not None:
                existing.append(self._serialize(row))
                continue

            row = Substitution(
                source_ingredient=source,
                target_ingredient=target,
                reason=item.get("reason"),
                confidence=float(item.get("confidence", 1.0)),
                tags=sorted({self._normalize(str(tag)) for tag in item.get("tags", []) if str(tag).strip()}),
                **quantity,
            )
            self.session.add(row)
            self.session.flush()
            created.append(self._serialize(row))

        return {"created": created, "existing": existing, "invalid": invalid}

    def find_bulk(self, ingredients: Iterable[str]) -> dict[str, list[dict]]:
        normalized = list(dict.fromkeys(self._normalize(value) for value in ingredients if value and value.strip()))
        result = {value: [] for value in normalized}
        if not normalized:
            return result

        rows = self.session.scalars(
            select(Substitution)
            .where(Substitution.source_ingredient.in_(normalized))
            .order_by(Substitution.source_ingredient, Substitution.confidence.desc(), Substitution.target_ingredient)
        ).all()

        for row in rows:
            result[row.source_ingredient].append(self._serialize(row))
        return result

    def set_quantities(self, rules: list[dict]) -> dict:
        """Set quantity_ratio / quantity_note of existing substitutions."""
        updated: list[dict] = []
        missing: list[dict] = []
        invalid: list[dict] = []
        for item in rules:
            source = self._normalize(str(item.get("source_ingredient", "")))
            target = self._normalize(str(item.get("target_ingredient", "")))
            quantity = quantity_fields(item)
            if quantity is None or item.get("quantity_ratio") is None:
                invalid.append(item)
                continue
            row = self.session.scalar(
                select(Substitution).where(
                    Substitution.source_ingredient == source,
                    Substitution.target_ingredient == target,
                )
            )
            if row is None:
                missing.append({"source_ingredient": source, "target_ingredient": target})
                continue
            row.quantity_ratio = quantity["quantity_ratio"]
            if quantity["quantity_note"] is not None:
                row.quantity_note = quantity["quantity_note"]
            updated.append(self._serialize(row))
        self.session.flush()
        return {"updated": updated, "missing": missing, "invalid": invalid}

    def list_all(self) -> list[dict]:
        rows = self.session.scalars(
            select(Substitution).order_by(
                Substitution.source_ingredient,
                Substitution.confidence.desc(),
                Substitution.target_ingredient,
            )
        ).all()
        return [self._serialize(row) for row in rows]

    def delete_bulk(self, substitutions: list[dict]) -> dict:
        deleted: list[dict] = []
        missing: list[dict] = []

        for item in substitutions:
            source = self._normalize(str(item.get("source_ingredient", "")))
            target = self._normalize(str(item.get("target_ingredient", "")))
            row = self.session.scalar(
                select(Substitution).where(
                    Substitution.source_ingredient == source,
                    Substitution.target_ingredient == target,
                )
            )
            if row is None:
                missing.append({"source_ingredient": source, "target_ingredient": target})
                continue
            deleted.append(self._serialize(row))
            self.session.delete(row)

        self.session.flush()
        return {"deleted": deleted, "missing": missing}
