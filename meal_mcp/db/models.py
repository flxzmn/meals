from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.db import Base


def utc_now():
    return datetime.now(timezone.utc)


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mealdb_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    area: Mapped[str | None] = mapped_column(String(100))
    instructions: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    # Variants (Sprint 6): an adapted copy of another recipe. mealdb_id is then "<parent>-v<n>".
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    constraints: Mapped[dict | None] = mapped_column(JSON)
    changes: Mapped[list | None] = mapped_column(JSON)
    # Who wrote the instructions of a variant: "original" (copied), "llm" (rewritten by Claude), "edited".
    instructions_source: Mapped[str | None] = mapped_column(String(20))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # TheMealDB has no servings, so this is None until the user states it. Variants inherit it.
    servings: Mapped[int | None] = mapped_column(Integer)

    ingredients: Mapped[list["Ingredient"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="Ingredient.position",
    )
    parent: Mapped["Recipe | None"] = relationship(back_populates="variants", remote_side="Recipe.id")
    variants: Mapped[list["Recipe"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="Recipe.id",
    )

    @property
    def effective_servings(self) -> int | None:
        return self.servings or (self.parent.servings if self.parent else None)


class Ingredient(Base):
    __tablename__ = "ingredients"
    __table_args__ = (
        UniqueConstraint("recipe_id", "position", name="uq_recipe_ingredient_position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    measure: Mapped[str] = mapped_column(String(100), default="")
    estimated_grams: Mapped[float | None] = mapped_column(Float)

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")


class NutritionCache(Base):
    __tablename__ = "nutrition_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    normalized_name: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    usda_fdc_id: Mapped[str] = mapped_column(String(50), nullable=False)
    matched_name: Mapped[str] = mapped_column(String(500), nullable=False)
    calories_per_100g: Mapped[float | None] = mapped_column(Float)
    protein_per_100g: Mapped[float | None] = mapped_column(Float)
    fat_per_100g: Mapped[float | None] = mapped_column(Float)
    carbs_per_100g: Mapped[float | None] = mapped_column(Float)
    # USDA portion weights [{"unit": "medium whole", "grams": 123.0}]; None = not loaded yet.
    portions: Mapped[list | None] = mapped_column(JSON)
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IngredientMatchRule(Base):
    """Manual USDA match decisions per ingredient (Sprint 10). Survive refresh and reinstall of the cache."""

    __tablename__ = "ingredient_match_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # Chosen food; enrichment loads it directly instead of searching.
    fdc_id: Mapped[str | None] = mapped_column(String(50))
    # Foods rejected for this ingredient; the search skips them.
    rejected_fdc_ids: Mapped[list | None] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Substitution(Base):
    __tablename__ = "substitutions"
    __table_args__ = (
        UniqueConstraint(
            "source_ingredient",
            "target_ingredient",
            name="uq_substitution_source_target",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_ingredient: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_ingredient: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    tags: Mapped[list | None] = mapped_column(JSON, default=list)
    # Grams of target per gram of source (Sprint 8); None means 1:1.
    quantity_ratio: Mapped[float | None] = mapped_column(Float)
    quantity_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SubstitutionFeedback(Base):
    __tablename__ = "substitution_feedback"
    __table_args__ = (
        UniqueConstraint(
            "source_ingredient",
            "target_ingredient",
            "accepted",
            "constraints_hash",
            name="uq_substitution_feedback_decision",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_ingredient: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_ingredient: Mapped[str] = mapped_column(String(255), nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255))
    feedback: Mapped[str | None] = mapped_column(Text)
    constraints: Mapped[dict | None] = mapped_column(JSON)
    constraints_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SubstitutionSuggestion(Base):
    __tablename__ = "substitution_suggestions"
    __table_args__ = (
        UniqueConstraint(
            "source_ingredient",
            "target_ingredient",
            "constraints_hash",
            name="uq_substitution_suggestion_context",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_ingredient: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_ingredient: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    tags: Mapped[list | None] = mapped_column(JSON, default=list)
    quantity_ratio: Mapped[float | None] = mapped_column(Float)
    quantity_note: Mapped[str | None] = mapped_column(Text)
    constraints: Mapped[dict | None] = mapped_column(JSON)
    constraints_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
