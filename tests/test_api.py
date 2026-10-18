import pytest
fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from app.agents.extractor import RuleExtractor
from app.api import create_app
from app.config import Settings
from app.sources.fixtures import FixtureProvider
from app.sources.live import LiveProvider


@pytest.fixture()
def client():
    return TestClient(create_app(Settings(), FixtureProvider(), RuleExtractor()))


def test_full_flow_and_auth(client):
    g = client.post("/api/groups", json={}).json()
    gid, t = g["id"], g["token"]
    assert client.post(f"/api/groups/{gid}/join", json={"token": "wrong", "nickname": "A", "restrictions": []}).status_code == 404
    r = client.post(f"/api/groups/{gid}/join", json={"token": t, "nickname": "A", "restrictions": ["vegan", "gluten_free"]})
    assert r.status_code == 200
    assert client.get(f"/api/groups/{gid}?t=nope").status_code == 404
    rep = client.post(f"/api/groups/{gid}/report?t={t}")
    assert rep.status_code == 200 and rep.json()["venues"]
    assert client.post(f"/api/groups/{gid}/report?t={t}").status_code == 429  # cooldown
    assert client.get(f"/api/groups/{gid}/report?t={t}").status_code == 200


def test_validation_and_headers(client):
    g = client.post("/api/groups", json={}).json()
    bad = client.post(f"/api/groups/{g['id']}/join", json={"token": g["token"], "nickname": "A", "restrictions": ["not_real"]})
    assert bad.status_code == 422
    assert "default-src 'none'" in client.get("/").headers["content-security-policy"]


def test_live_provider_prefers_google_results_for_real_restaurants():
    class DummyHTTP:
        def post(self, *args, **kwargs):
            raise AssertionError("should not fall back to OSM when Google search is available")

        def get(self, *args, **kwargs):
            return DummyResponse([])

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class DummyFetch:
        def get(self, url):
            return (url, "<html><head><title>Din Tai Fung</title></head><body>vegan menu</body></html>")

    provider = LiveProvider(grounded_search=lambda q: ["https://www.dintaifung.com/"])
    provider._http = DummyHTTP()
    provider.fetch = DummyFetch()

    result = provider.find_venues("Bellevue, WA", 3, 47.6104, -122.2015, 5)
    assert result[0].name == "Din Tai Fung"
    assert result[0].website == "https://www.dintaifung.com/"


def test_live_provider_accepts_osm_fallback_links_for_real_restaurants():
    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class DummyHTTP:
        def post(self, *args, **kwargs):
            return DummyResponse({
                "elements": [{
                    "type": "node",
                    "id": 12345,
                    "lat": 47.6062,
                    "lon": -122.3321,
                    "tags": {"name": "Piroshky Piroshky", "amenity": "restaurant"}
                }]
            })

        def get(self, *args, **kwargs):
            return DummyResponse([])

    provider = LiveProvider()
    provider._http = DummyHTTP()

    result = provider.find_venues("Seattle, WA", 5, 47.6062, -122.3321, 5)
    assert len(result) == 1
    assert result[0].website == "https://www.openstreetmap.org/node/12345"


def test_live_provider_queries_all_osm_element_types():
    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class DummyHTTP:
        def __init__(self):
            self.captured = None

        def post(self, *args, **kwargs):
            self.captured = kwargs["data"]["data"] if isinstance(kwargs.get("data"), dict) else kwargs.get("data")
            return DummyResponse({"elements": []})

        def get(self, *args, **kwargs):
            return DummyResponse([])

    provider = LiveProvider()
    transport = DummyHTTP()
    provider._http = transport

    provider.find_venues("Seattle, WA", 5, 47.6062, -122.3321, 5)
    assert "way[\"amenity\"~\"restaurant|cafe|fast_food|food_court\"]" in transport.captured
    assert "relation[\"amenity\"~\"restaurant|cafe|fast_food|food_court\"]" in transport.captured
