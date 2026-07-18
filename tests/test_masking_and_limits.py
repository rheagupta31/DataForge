"""Tests for column-level data masking and rate limiting."""
import app as appmod


def test_masking_redacts_by_default(client, sample_db_url, fake_llm, monkeypatch):
    monkeypatch.setattr(appmod, "generate_sql",
                         lambda *a, **k: "SELECT name, salary FROM employees LIMIT 3")
    appmod.masked_columns = set(appmod.DEFAULT_MASKED_COLUMNS)

    r = client.post("/query", json={
        "english": "salaries", "db_url": sample_db_url, "api_key": "x", "schema_str": "",
    })
    d = r.get_json()
    assert d["masked_columns"] == ["salary"]
    assert all(row[1] == appmod.MASK_PLACEHOLDER for row in d["rows"])


def test_masking_reveals_when_explicitly_requested(client, sample_db_url, monkeypatch):
    monkeypatch.setattr(appmod, "generate_sql",
                         lambda *a, **k: "SELECT name, salary FROM employees LIMIT 3")
    appmod.masked_columns = set(appmod.DEFAULT_MASKED_COLUMNS)

    r = client.post("/query", json={
        "english": "salaries", "db_url": sample_db_url, "api_key": "x", "schema_str": "",
        "reveal_masked": True,
    })
    d = r.get_json()
    assert d["masked_columns"] == ["salary"]  # still flagged as sensitive...
    assert all(isinstance(row[1], (int, float)) for row in d["rows"])  # ...but not redacted


def test_mask_settings_get_and_post(client):
    appmod.masked_columns = set(appmod.DEFAULT_MASKED_COLUMNS)
    r = client.get("/mask-settings")
    assert "salary" in r.get_json()["masked_columns"]

    r = client.post("/mask-settings", json={"columns": ["foo", "bar"]})
    d = r.get_json()
    assert set(d["masked_columns"]) == {"foo", "bar"}

    appmod.masked_columns = set(appmod.DEFAULT_MASKED_COLUMNS)  # restore for other tests


def test_connect_route_is_rate_limited(client):
    appmod.limiter.enabled = True
    appmod.limiter.reset()
    try:
        statuses = [client.post("/connect", json={"db_url": ""}).status_code for _ in range(13)]
        assert 429 in statuses
    finally:
        appmod.limiter.enabled = False
