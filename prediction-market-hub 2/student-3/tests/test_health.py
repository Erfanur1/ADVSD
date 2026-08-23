import importlib
def test_health():
    m = importlib.import_module("backend.app")
    c = m.app.test_client()
    assert c.get("/health").status_code == 200
