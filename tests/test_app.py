import pytest

from aleph_soar import create_app


@pytest.fixture
def client():
    return create_app({"TESTING": True}).test_client()


def test_health_identifies_scaffold_stage(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.is_json
    assert response.json["success"] is True
    assert response.json["data"]["stage"] == "scaffold"


def test_starter_page_and_stylesheet_are_served(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/workspace.css").status_code == 200


@pytest.mark.parametrize("path,method", [
    ("/api/v1/auth/login", "post"),
    ("/api/v1/events", "post"),
    ("/api/v1/incidents", "get"),
])
def test_unimplemented_business_endpoints_do_not_report_success(client, path, method):
    assert getattr(client, method)(path).status_code == 404
