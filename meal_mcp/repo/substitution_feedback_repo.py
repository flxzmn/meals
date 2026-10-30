from sqlalchemy import select

from db.models import SubstitutionFeedback
from services.constraint_service import constraints_hash, normalize_constraints
from services.measure_service import normalize_ingredient_name


class SubstitutionFeedbackRepo:
    def __init__(self, session):
        self.session = session

    @staticmethod
    def _serialize(row: SubstitutionFeedback) -> dict:
        return {
            "id": row.id,
            "source_ingredient": row.source_ingredient,
            "target_ingredient": row.target_ingredient,
            "accepted": row.accepted,
            "suggestion_reason": row.reason,
            "feedback": row.feedback,
            "constraints": row.constraints or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def add_bulk(self, entries: list[dict], accepted: bool) -> dict:
        """Store decisions. An identical decision (pair, accepted, constraints) is stored only once."""
        created: list[dict] = []
        existing: list[dict] = []
        for entry in entries:
            source = normalize_ingredient_name(str(entry.get("source_ingredient", "")))
            target = normalize_ingredient_name(str(entry.get("target_ingredient", "")))
            if not source or not target:
                continue
            constraints = normalize_constraints(entry.get("constraints"))
            digest = constraints_hash(constraints)

            row = self.session.scalar(
                select(SubstitutionFeedback).where(
                    SubstitutionFeedback.source_ingredient == source,
                    SubstitutionFeedback.target_ingredient == target,
                    SubstitutionFeedback.accepted == accepted,
                    SubstitutionFeedback.constraints_hash == digest,
                )
            )
            if row is not None:
                existing.append(self._serialize(row))
                continue

            row = SubstitutionFeedback(
                source_ingredient=source,
                target_ingredient=target,
                accepted=accepted,
                reason=entry.get("reason"),
                feedback=entry.get("feedback"),
                constraints=constraints,
                constraints_hash=digest,
            )
            self.session.add(row)
            self.session.flush()
            created.append(self._serialize(row))
        return {"created": created, "existing": existing}

    def set_feedback(self, source: str, target: str, accepted: bool, digest: str, text: str) -> dict | None:
        """Set the user's feedback on an existing decision. Prefers the entry with the same constraints."""
        rows = self.session.scalars(
            select(SubstitutionFeedback)
            .where(
                SubstitutionFeedback.source_ingredient == source,
                SubstitutionFeedback.target_ingredient == target,
                SubstitutionFeedback.accepted == accepted,
            )
            .order_by(SubstitutionFeedback.created_at.desc())
        ).all()
        if not rows:
            return None
        row = next((item for item in rows if item.constraints_hash == digest), rows[0])
        row.feedback = text
        self.session.flush()
        return self._serialize(row)

    def find_rejections(self, sources: list[str]) -> dict[str, list[dict]]:
        normalized = list(dict.fromkeys(normalize_ingredient_name(value) for value in sources if value.strip()))
        result: dict[str, list[dict]] = {value: [] for value in normalized}
        if not normalized:
            return result
        rows = self.session.scalars(
            select(SubstitutionFeedback).where(
                SubstitutionFeedback.source_ingredient.in_(normalized),
                SubstitutionFeedback.accepted.is_(False),
            )
        ).all()
        for row in rows:
            item = self._serialize(row)
            item["constraints_hash"] = row.constraints_hash
            result[row.source_ingredient].append(item)
        return result

    def list_all(self, accepted: bool | None = None) -> list[dict]:
        statement = select(SubstitutionFeedback).order_by(SubstitutionFeedback.created_at.desc())
        if accepted is not None:
            statement = statement.where(SubstitutionFeedback.accepted == accepted)
        rows = self.session.scalars(statement).all()
        return [self._serialize(row) for row in rows]

    def summary(self) -> dict:
        rows = self.session.scalars(select(SubstitutionFeedback)).all()
        accepted = sum(1 for row in rows if row.accepted)
        rejected = len(rows) - accepted
        return {"total": len(rows), "accepted": accepted, "rejected": rejected}
