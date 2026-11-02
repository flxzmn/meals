from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from db.db import Base
from db.models import Ingredient, NutritionCache, Recipe
from repo.nutrition_repo import NutritionRepo
from repo.recipe_repo import RecipeRepo


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def sample_meal():
    return {
        "idMeal": "52771", "strMeal": "Test Pasta", "strCategory": "Pasta", "strArea": "Italian",
        "strInstructions": "Cook.", "strMealThumb": "https://example.invalid/image.jpg",
        "strIngredient1": "Tomato", "strMeasure1": "100 g",
        "strIngredient2": "Olive Oil", "strMeasure2": "1 tbsp",
    }


def test_recipe_bulk_save_and_delete():
    session = build_session()
    repo = RecipeRepo(session)
    result = repo.save_bulk([sample_meal()])
    assert result["saved"] == ["52771"]
    assert len(repo.get_bulk(["52771"])[0].ingredients) == 2
    assert repo.delete_bulk(["52771"])["deleted"] == ["52771"]


def test_nutrition_bulk_cache():
    session = build_session()
    repo = NutritionRepo(session)
    repo.save_bulk([{
        "normalized_name": "tomato", "source_name": "Tomato", "usda_fdc_id": "1",
        "matched_name": "Tomatoes, raw", "calories_per_100g": 18.0,
        "protein_per_100g": 0.9, "fat_per_100g": 0.2, "carbs_per_100g": 3.9,
    }])
    assert repo.get_cached_bulk(["tomato"])["tomato"].calories_per_100g == 18.0


def test_missing_portions_column_is_added_to_old_database(tmp_path):
    from sqlalchemy import inspect, text

    from db.db import add_missing_columns

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE nutrition_cache (id INTEGER PRIMARY KEY, normalized_name VARCHAR)"))
    add_missing_columns(engine)
    add_missing_columns(engine)  # idempotent
    assert "portions" in {column["name"] for column in inspect(engine).get_columns("nutrition_cache")}


def test_seed_rules_start_an_unused_knowledge_base(tmp_path):
    from sqlalchemy.orm import sessionmaker

    from db.db import SEED_FILE, load_seed_substitutions
    from repo.substitution_repo import SubstitutionRepo
    from services.substitution_learning_service import SubstitutionLearningService

    engine = create_engine(f"sqlite:///{tmp_path / 'seed.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    assert load_seed_substitutions(factory) == 30
    assert load_seed_substitutions(factory) == 0

    with factory() as session:
        rules = SubstitutionRepo(session).find_bulk(["milk"])["milk"]
        assert rules[0]["target_ingredient"] == "oat milk"
        SubstitutionRepo(session).delete_bulk(SubstitutionRepo(session).list_all())
        session.commit()
    assert load_seed_substitutions(factory) == 30  # never used: deleted rules come back

    with factory() as session:
        SubstitutionRepo(session).delete_bulk(SubstitutionRepo(session).list_all())
        learning = SubstitutionLearningService(session)
        learning.record_suggestions([{"source_ingredient": "milk", "target_ingredient": "soy milk"}])
        session.commit()
    assert load_seed_substitutions(factory) == 0  # worked with: no rules forced on the user
    assert load_seed_substitutions(factory, tmp_path / "missing.json") == 0
    assert SEED_FILE.exists()
