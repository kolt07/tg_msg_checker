from fastapi.testclient import TestClient

from app.main import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKERS", "0")
    return TestClient(create_app(tmp_path))


def test_analyze_returns_only_hits_and_elapsed_header(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/api/dictionaries",
            json={"name": "Зброя", "language": "uk", "tag": "weapon", "words": ["граната"]},
        )
        assert created.status_code == 201
        body = created.json()
        assert body["word_count"] == 1
        assert body["form_count"] > 1
        stored = (tmp_path / "dictionaries.json").read_text(encoding="utf-8")
        assert "Зброя" in stored

        response = client.post(
            "/api/analyze",
            json={
                "messages": [
                    {
                        "id": "1",
                        "text": "бачив гранату, X = 5179365 Y = 6500127",
                    },
                    {"id": "2", "text": "тихий день без згадок"},
                    {"id": 3, "text": "ще гранату"},
                ]
            },
        )
        assert response.status_code == 200
        elapsed = float(response.headers["X-Elapsed-Ms"])
        assert elapsed >= 0
        payload = response.json()
        assert [item["id"] for item in payload] == ["1", "3"]
        assert payload[0]["tags"][0]["tag"] == "weapon"
        kinds = {entity["type"] for entity in payload[0]["entities"]}
        assert kinds == {"coordinates"}
        coordinates = next(entity for entity in payload[0]["entities"] if entity["type"] == "coordinates")
        assert coordinates["matches"][0]["format"] == "gauss_kruger"
        assert "entities" not in payload[1]


def test_dictionary_crud(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/api/dictionaries",
            json={"name": "Техніка", "language": "uk", "tag": "vehicle", "words": ["машина"]},
        )
        assert created.status_code == 201
        dictionary_id = created.json()["id"]
        assert len(client.get("/api/dictionaries").json()) == 1

        updated = client.put(
            f"/api/dictionaries/{dictionary_id}",
            json={
                "name": "Техніка",
                "language": "uk",
                "tag": "vehicle",
                "words": ["машина", "бойова машина"],
            },
        )
        assert updated.status_code == 200
        assert updated.json()["word_count"] == 2

        assert client.put(
            "/api/dictionaries/missing",
            json={"name": "Техніка", "language": "uk", "tag": "vehicle", "words": ["машина"]},
        ).status_code == 404
        assert client.post(
            "/api/dictionaries",
            json={"name": "Інше", "language": "de", "tag": "x", "words": ["тест"]},
        ).status_code == 400
        assert client.post(
            "/api/dictionaries",
            json={"name": "Довге", "language": "uk", "tag": "x", "words": ["один два три чотири п'ять"]},
        ).status_code == 400

        assert client.delete(f"/api/dictionaries/{dictionary_id}").status_code == 204
        assert client.get("/api/dictionaries").json() == []
