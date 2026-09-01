import importlib

def test_health():
    m = importlib.import_module("backend.app")
    c = m.app.test_client()
    assert c.get("/health").status_code == 200

def test_get_positions():
    m = importlib.import_module("backend.app")
    c = m.app.test_client()
    resp = c.get("/api/positions")
    assert resp.status_code == 200
    assert type(resp.json) == list
