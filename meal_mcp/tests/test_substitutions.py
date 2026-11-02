from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.db import Base
from db.models import Ingredient, Recipe
from repo.substitution_repo import SubstitutionRepo
from services.substitution_service import SubstitutionService


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def seed_recipe(session):
    recipe = Recipe(
        mealdb_id="test-1",
        name="Chicken Curry",
        category="Main",
        area="Test",
        instructions="Cook all ingredients.",
    )
    recipe.ingredients.extend([
        Ingredient(position=1, name="Chicken", normalized_name="chicken", measure="100 g", estimated_grams=100.0),
        Ingredient(position=2, name="Milk", normalized_name="milk", measure="100 ml", estimated_grams=100.0),
    ])
    session.add(recipe)
    session.commit()


def seed_substitutions(repo):
    return repo.add_bulk([
        {
            "source_ingredient": "chicken",
            "target_ingredient": "tofu",
            "reason": "vegan",
            "confidence": 0.8,
            "tags": ["vegan"],
        },
        {
            "source_ingredient": "chicken",
            "target_ingredient": "tempeh",
            "reason": "vegan",
            "confidence": 0.9,
            "tags": ["vegan", "high protein"],
        },
        {
            "source_ingredient": "milk",
            "target_ingredient": "oat milk",
            "reason": "vegan",
            "confidence": 0.9,
            "tags": ["vegan", "dairy free", "nut free"],
        },
    ])


def test_add_and_find_substitutions():
    session = build_session()
    repo = SubstitutionRepo(session)
    result = seed_substitutions(repo)
    assert len(result["created"]) == 3
    found = repo.find_bulk(["chicken", "milk"])
    assert found["chicken"][0]["target_ingredient"] == "tempeh"
    assert found["milk"][0]["target_ingredient"] == "oat milk"


def test_duplicate_substitution_is_not_created_twice():
    session = build_session()
    repo = SubstitutionRepo(session)
    seed_substitutions(repo)
    repeated = seed_substitutions(repo)
    assert repeated["created"] == []
    assert len(repeated["existing"]) == 3


def test_dislike_filter_prefers_tempeh_over_tofu():
    session = build_session()
    seed_substitutions(SubstitutionRepo(session))
    service = SubstitutionService(session)
    result = service.find_substitutions(["chicken"], {"diet": "vegan", "dislikes": ["tofu"]})
    assert [item["target_ingredient"] for item in result["chicken"]] == ["tempeh"]


def test_recipe_adaptation_is_bulk_and_keeps_original():
    session = build_session()
    seed_recipe(session)
    seed_substitutions(SubstitutionRepo(session))
    service = SubstitutionService(session)
    result = service.adapt_recipes(["test-1"], {"diet": "vegan", "dislikes": ["tofu"]})
    assert result["status"] == "success"
    assert result["substitutions_applied"] == 2
    adapted = result["adapted_recipes"][0]
    assert [item["name"] for item in adapted["ingredients"]] == ["tempeh", "oat milk"]
    original = session.query(Recipe).filter_by(mealdb_id="test-1").one()
    assert [item.normalized_name for item in original.ingredients] == ["chicken", "milk"]


def test_delete_bulk():
    session = build_session()
    repo = SubstitutionRepo(session)
    seed_substitutions(repo)
    result = repo.delete_bulk([{"source_ingredient": "milk", "target_ingredient": "oat milk"}])
    assert len(result["deleted"]) == 1
    assert repo.find_bulk(["milk"])["milk"] == []
