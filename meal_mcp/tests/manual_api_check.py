import asyncio
from services.mealdb_service import MealDBService


async def main():
    result = await MealDBService().search_bulk(["Arrabiata", "Chicken Curry"])
    print({query: [meal["strMeal"] for meal in meals] for query, meals in result["results"].items()})
    print("Errors:", result["errors"])


if __name__ == "__main__":
    asyncio.run(main())
