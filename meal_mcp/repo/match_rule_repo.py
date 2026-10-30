from sqlalchemy import select

from db.models import IngredientMatchRule, utc_now


# usda_fdc_id of nutrition values entered by hand (e.g. from a product label).
CUSTOM_FDC_ID = "custom"


class MatchRuleRepo:
    def __init__(self, session):
        self.session = session

    @staticmethod
    def serialize(row: IngredientMatchRule) -> dict:
        return {
            "ingredient": row.normalized_name,
            "fdc_id": row.fdc_id,
            "rejected_fdc_ids": row.rejected_fdc_ids or [],
            "note": row.note,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def get_bulk(self, normalized_names: list[str]) -> dict[str, IngredientMatchRule]:
        if not normalized_names:
            return {}
        rows = self.session.scalars(
            select(IngredientMatchRule).where(IngredientMatchRule.normalized_name.in_(normalized_names))
        ).all()
        return {row.normalized_name: row for row in rows}

    def list_all(self) -> list[IngredientMatchRule]:
        return list(self.session.scalars(select(IngredientMatchRule).order_by(IngredientMatchRule.normalized_name)).all())

    def _get_or_create(self, normalized_name: str) -> IngredientMatchRule:
        row = self.get_bulk([normalized_name]).get(normalized_name)
        if row is None:
            row = IngredientMatchRule(normalized_name=normalized_name, rejected_fdc_ids=[])
            self.session.add(row)
        return row

    def set_choice(self, normalized_name: str, fdc_id: str, note: str | None) -> IngredientMatchRule:
        row = self._get_or_create(normalized_name)
        row.fdc_id = fdc_id
        row.rejected_fdc_ids = [value for value in row.rejected_fdc_ids or [] if value != fdc_id]
        if note:
            row.note = note
        row.updated_at = utc_now()
        self.session.flush()
        return row

    def add_rejection(self, normalized_name: str, fdc_id: str, note: str | None) -> IngredientMatchRule:
        row = self._get_or_create(normalized_name)
        row.rejected_fdc_ids = sorted(set(row.rejected_fdc_ids or []) | {fdc_id})
        if row.fdc_id == fdc_id:
            row.fdc_id = None
        if note:
            row.note = note
        row.updated_at = utc_now()
        self.session.flush()
        return row

    def delete(self, normalized_name: str) -> bool:
        row = self.get_bulk([normalized_name]).get(normalized_name)
        if row is None:
            return False
        self.session.delete(row)
        self.session.flush()
        return True
