from sqlalchemy import select
from db.models import NutritionCache


class NutritionRepo:
    def __init__(self, session):
        self.session = session

    def get_cached_bulk(self, normalized_names: list[str]) -> dict[str, NutritionCache]:
        if not normalized_names:
            return {}
        statement = select(NutritionCache).where(NutritionCache.normalized_name.in_(normalized_names))
        rows = self.session.scalars(statement).all()
        return {row.normalized_name: row for row in rows}

    def save_bulk(self, records: list[dict]) -> None:
        if not records:
            return
        existing = self.get_cached_bulk([record["normalized_name"] for record in records])
        for record in records:
            row = existing.get(record["normalized_name"])
            if row is None:
                self.session.add(NutritionCache(**record))
                continue
            for key, value in record.items():
                setattr(row, key, value)
        self.session.flush()

    def delete_bulk(self, normalized_names: list[str]) -> None:
        for row in self.get_cached_bulk(normalized_names).values():
            self.session.delete(row)
        self.session.flush()

    def list_all(self) -> list[NutritionCache]:
        return list(self.session.scalars(select(NutritionCache).order_by(NutritionCache.normalized_name)).all())
