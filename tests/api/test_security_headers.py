from app.main import app
from fastapi.testclient import TestClient


def test_security_headers_present_on_a_normal_response(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert (
        response.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    )
    assert "geolocation=()" in response.headers["permissions-policy"]


def test_security_headers_present_on_a_404(client: TestClient) -> None:
    # A route that 404s from routing itself, never touching the DB - keeps this test pure.
    response = client.get("/api/v1/this-route-does-not-exist")
    assert response.status_code == 404
    assert response.headers["x-frame-options"] == "DENY"


def test_docs_page_gets_a_relaxed_csp_that_still_denies_framing(client: TestClient) -> None:
    response = client.get("/docs")
    assert response.status_code == 200
    csp = response.headers["content-security-policy"]
    assert "cdn.jsdelivr.net" in csp
    assert csp != "default-src 'none'; frame-ancestors 'none'"
    # The docs surface still gets every other header, including frame denial.
    assert response.headers["x-frame-options"] == "DENY"


def test_redoc_is_disabled_and_gets_a_normal_404() -> None:
    response = TestClient(app).get("/redoc")
    assert response.status_code == 404
