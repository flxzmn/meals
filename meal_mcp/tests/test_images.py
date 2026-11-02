"""Recipe photos as files (idea from the recipe book run of 02.11: Claude fetched them in the browser)."""

import httpx

from db.models import Recipe
from services.image_service import ImageService
from services.variant_service import VariantService
from tests.test_substitutions import build_session
from tests.test_variants import adapted

PHOTO = "https://www.themealdb.com/images/media/meals/curry.jpg"
JPEG = b"\xff\xd8\xff" + b"x" * 100


def photo_server(requested: list[str], content_type: str = "image/jpeg", status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(status, content=JPEG, headers={"content-type": content_type})
    return httpx.MockTransport(handler)


def session_with_photo():
    session = build_session()
    VariantService(session).save_variants([adapted(session)])
    session.query(Recipe).filter_by(mealdb_id="test-1").one().image_url = PHOTO
    return session


async def test_photos_are_saved_as_files_in_the_chosen_size(tmp_path):
    requested = []
    service = ImageService(session_with_photo(), transport=photo_server(requested))
    result = await service.download(["test-1"], "small", str(tmp_path))
    assert requested == [f"{PHOTO}/small"]
    image = result["images"][0]
    assert image["status"] == "downloaded"
    assert (tmp_path / "test-1-small.jpg").read_bytes() == JPEG
    assert image["path"] == str(tmp_path / "test-1-small.jpg")


async def test_variant_uses_the_photo_of_its_original_and_it_is_fetched_once(tmp_path):
    requested = []
    service = ImageService(session_with_photo(), transport=photo_server(requested))
    result = await service.download(["test-1", "test-1-v1"], "original", str(tmp_path))
    assert requested == [PHOTO]
    assert {image["mealdb_id"]: image["path"] for image in result["images"]} == {
        "test-1": str(tmp_path / "test-1-original.jpg"),
        "test-1-v1": str(tmp_path / "test-1-original.jpg"),
    }


async def test_existing_files_are_not_downloaded_again(tmp_path):
    requested = []
    service = ImageService(session_with_photo(), transport=photo_server(requested))
    await service.download(["test-1"], "medium", str(tmp_path))
    again = await service.download(["test-1"], "medium", str(tmp_path))
    assert len(requested) == 1
    assert again["images"][0]["status"] == "existing"


async def test_only_themealdb_is_contacted(tmp_path):
    session = session_with_photo()
    session.query(Recipe).filter_by(mealdb_id="test-1").one().image_url = "http://localhost:8080/admin"
    requested = []
    result = await ImageService(session, transport=photo_server(requested)).download(["test-1", "nope"], folder=str(tmp_path))
    assert requested == []
    assert result["no_image"] == ["test-1"]
    assert result["missing_recipes"] == ["nope"]


async def test_failed_downloads_are_errors_not_files(tmp_path):
    for transport in (photo_server([], status=404), photo_server([], content_type="text/html")):
        result = await ImageService(session_with_photo(), transport=transport).download(["test-1"], folder=str(tmp_path))
        assert result["images"] == [] and "test-1" in result["errors"]
    assert not list(tmp_path.iterdir())


async def test_unknown_size_is_refused():
    result = await ImageService(build_session()).download(["test-1"], "huge")
    assert result["status"] == "error"
