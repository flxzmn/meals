from __future__ import annotations

from sqlalchemy import select

from db.models import SubstitutionSuggestion, utc_now
from repo.substitution_repo import quantity_fields
from services.constraint_service import constraints_hash, normalize_constraints
from services.measure_service import normalize_ingredient_name


class SubstitutionSuggestionRepo:
    def __init__(self, session):
        self.session = session

    @staticmethod
    def serialize(row: SubstitutionSuggestion) -> dict:
        return {
            "id": row.id,
            "source_ingredient": row.source_ingredient,
            "target_ingredient": row.target_ingredient,
            "reason": row.reason,
            "confidence": row.confidence,
            "tags": row.tags or [],
            "quantity_ratio": row.quantity_ratio if row.quantity_ratio is not None else 1.0,
            "quantity_note": row.quantity_note,
            "constraints": row.constraints or {},
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        }

    def _get_row(self, source: str, target: str, digest: str) -> SubstitutionSuggestion | None:
        return self.session.scalar(
            select(SubstitutionSuggestion).where(
                SubstitutionSuggestion.source_ingredient == source,
                SubstitutionSuggestion.target_ingredient == target,
                SubstitutionSuggestion.constraints_hash == digest,
            )
        )

    def add_pending(self, item: dict, constraints: dict | None, reopen_rejected: bool = False) -> tuple[dict, bool]:
        """Store a pending suggestion. Returns (suggestion, created).

        Existing entries are returned unchanged, except a rejected entry when reopen_rejected is set.
        """
        source = normalize_ingredient_name(str(item["source_ingredient"]))
        target = normalize_ingredient_name(str(item["target_ingredient"]))
        constraints = normalize_constraints(constraints)
        digest = constraints_hash(constraints)

        tags = sorted({normalize_ingredient_name(str(tag)) for tag in item.get("tags") or [] if str(tag).strip()})
        quantity = quantity_fields(item) or {"quantity_ratio": None, "quantity_note": None}
        row = self._get_row(source, target, digest)
        if row is not None:
            if not (reopen_rejected and row.status == "rejected"):
                return self.serialize(row), False
            row.reason = item.get("reason")
            row.confidence = float(item.get("confidence", 0.5))
            row.tags = tags
            row.quantity_ratio = quantity["quantity_ratio"]
            row.quantity_note = quantity["quantity_note"]
            row.status = "pending"
            row.decided_at = None
            self.session.flush()
            return self.serialize(row), True

        row = SubstitutionSuggestion(
            source_ingredient=source,
            target_ingredient=target,
            reason=item.get("reason"),
            confidence=float(item.get("confidence", 0.5)),
            tags=tags,
            **quantity,
            constraints=constraints,
            constraints_hash=digest,
            status="pending",
        )
        self.session.add(row)
        self.session.flush()
        return self.serialize(row), True

    def find_for_decision(self, item: dict, constraints: dict | None = None) -> SubstitutionSuggestion | None:
        """Resolve a suggestion by id, or by source/target (and constraints, if given)."""
        if item.get("id") is not None or item.get("suggestion_id") is not None:
            return self.session.get(SubstitutionSuggestion, int(item.get("id") or item.get("suggestion_id")))

        source = normalize_ingredient_name(str(item.get("source_ingredient", "")))
        target = normalize_ingredient_name(str(item.get("target_ingredient", "")))
        if constraints is not None:
            row = self._get_row(source, target, constraints_hash(constraints))
            if row is not None:
                return row

        rows = self.session.scalars(
            select(SubstitutionSuggestion)
            .where(
                SubstitutionSuggestion.source_ingredient == source,
                SubstitutionSuggestion.target_ingredient == target,
            )
            .order_by(SubstitutionSuggestion.created_at.desc())
        ).all()
        pending = [row for row in rows if row.status == "pending"]
        return (pending or rows or [None])[0]

    def set_status(self, row: SubstitutionSuggestion, status: str) -> dict:
        row.status = status
        row.decided_at = utc_now()
        self.session.flush()
        return self.serialize(row)

    def list_pending(self, sources: list[str], constraints: dict | None) -> dict[str, list[dict]]:
        normalized = list(dict.fromkeys(normalize_ingredient_name(value) for value in sources if value.strip()))
        result: dict[str, list[dict]] = {value: [] for value in normalized}
        if not normalized:
            return result
        rows = self.session.scalars(
            select(SubstitutionSuggestion)
            .where(
                SubstitutionSuggestion.source_ingredient.in_(normalized),
                SubstitutionSuggestion.constraints_hash == constraints_hash(constraints),
                SubstitutionSuggestion.status == "pending",
            )
            .order_by(SubstitutionSuggestion.confidence.desc())
        ).all()
        for row in rows:
            result[row.source_ingredient].append(self.serialize(row))
        return result

    def list_all(self, status: str | None = None) -> list[dict]:
        statement = select(SubstitutionSuggestion).order_by(SubstitutionSuggestion.created_at.desc())
        if status:
            statement = statement.where(SubstitutionSuggestion.status == status)
        return [self.serialize(row) for row in self.session.scalars(statement).all()]
