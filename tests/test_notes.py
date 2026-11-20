from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_get_note(client: TestClient) -> None:
    created = client.post("/notes", json={"title": "First", "body": "Hello"})
    assert created.status_code == 201
    note_id = created.json()["id"]

    fetched = client.get(f"/notes/{note_id}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "First"
    assert fetched.json()["body"] == "Hello"


def test_list_notes_in_creation_order(client: TestClient) -> None:
    client.post("/notes", json={"title": "A"})
    client.post("/notes", json={"title": "B"})

    titles = [note["title"] for note in client.get("/notes").json()]
    assert titles == ["A", "B"]


def test_missing_note_returns_404(client: TestClient) -> None:
    assert client.get("/notes/999").status_code == 404


def test_empty_title_is_rejected(client: TestClient) -> None:
    assert client.post("/notes", json={"title": ""}).status_code == 422
