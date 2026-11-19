def test_respuesta_trae_instancia(client):
    response = client.get("/health")
    assert response.headers.get("X-Instance-Id")


def test_root_muestra_instancia(client):
    data = client.get("/").json()
    assert data["instance"]
