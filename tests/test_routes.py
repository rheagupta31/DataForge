"""Route-level tests via Flask's test client — covers upload (db/csv/xlsx),
connect, the full query/guardrail/debug lifecycle, clean, export, and the
plain-English insight endpoints."""
import io

import pandas as pd


def test_index_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"DataForge" in r.data


def test_upload_db_file(client, sample_db_path):
    with open(sample_db_path, "rb") as f:
        r = client.post(
            "/upload",
            data={"db_file": (io.BytesIO(f.read()), "database.db")},
            content_type="multipart/form-data",
        )
    d = r.get_json()
    assert r.status_code == 200
    assert d["engine"] == "sqlite"
    assert "employees" in d["tables"]
    assert d["db_url"].startswith("sqlite:///")


def test_upload_csv_file_creates_single_table(client):
    csv_bytes = b"Name,Salary\nAlice,90000\nBob,85000\n"
    r = client.post(
        "/upload",
        data={"db_file": (io.BytesIO(csv_bytes), "staff.csv")},
        content_type="multipart/form-data",
    )
    d = r.get_json()
    assert r.status_code == 200
    assert d["tables"] == ["staff"]


def test_upload_xlsx_creates_one_table_per_sheet(client):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame({"id": [1]}).to_excel(writer, sheet_name="Sheet A", index=False)
        pd.DataFrame({"id": [2]}).to_excel(writer, sheet_name="Sheet B", index=False)
    buf.seek(0)
    r = client.post(
        "/upload",
        data={"db_file": (buf, "book.xlsx")},
        content_type="multipart/form-data",
    )
    d = r.get_json()
    assert r.status_code == 200
    assert set(d["tables"]) == {"Sheet_A", "Sheet_B"}


def test_upload_rejects_unsupported_extension(client):
    r = client.post(
        "/upload",
        data={"db_file": (io.BytesIO(b"hi"), "file.txt")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400


def test_connect_requires_a_url(client):
    r = client.post("/connect", json={"db_url": ""})
    assert r.status_code == 400


def test_connect_fails_gracefully_on_unreachable_db(client):
    r = client.post("/connect", json={"db_url": "postgresql://baduser:badpass@127.0.0.1:1/nope"})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_query_read_only_success(client, sample_db_url, fake_llm):
    r = client.post("/query", json={
        "english": "high earners", "db_url": sample_db_url, "api_key": "x", "schema_str": "",
    })
    d = r.get_json()
    assert d["final_status"] == "success"
    assert d["result_rows"] > 0
    assert d["columns"] == ["name", "salary"]


def test_query_confirmation_required_then_run_anyway(client, sample_db_url, fake_llm):
    r = client.post("/query", json={
        "english": "delete a stale item", "db_url": sample_db_url, "api_key": "x", "schema_str": "",
    })
    d = r.get_json()
    assert d["final_status"] == "confirmation_required"
    assert d["guardrail_message"]

    r2 = client.post("/query", json={
        "english": "delete a stale item", "db_url": sample_db_url, "api_key": "x", "schema_str": "",
        "confirmed": True, "sql_override": d["final_sql"],
    })
    d2 = r2.get_json()
    assert d2["final_status"] == "success"
    assert d2["final_sql"] == d["final_sql"]


def test_query_blocked_even_when_confirmed(client, sample_db_url, fake_llm):
    r = client.post("/query", json={
        "english": "drop the table", "db_url": sample_db_url, "api_key": "x", "schema_str": "",
        "confirmed": True,
    })
    d = r.get_json()
    assert d["final_status"] == "blocked"


def test_query_requires_english_db_url_and_api_key(client, sample_db_url):
    assert client.post("/query", json={
        "english": "", "db_url": sample_db_url, "api_key": "x",
    }).status_code == 400
    assert client.post("/query", json={
        "english": "x", "db_url": "", "api_key": "x",
    }).status_code == 400
    assert client.post("/query", json={
        "english": "x", "db_url": sample_db_url, "api_key": "",
    }).status_code == 400


def test_clean_route(client, sample_db_url):
    r = client.post("/clean", json={"db_url": sample_db_url})
    d = r.get_json()
    assert r.status_code == 200
    assert "employees" in d["summary"]


def test_clean_route_requires_db_url(client):
    r = client.post("/clean", json={"db_url": ""})
    assert r.status_code == 400


def test_export_xlsx_returns_a_real_file(client):
    r = client.post("/export/xlsx", json={
        "columns": ["a", "b"], "rows": [[1, 2], [3, 4]], "filename": "t.xlsx",
    })
    assert r.status_code == 200
    assert len(r.data) > 100
    assert r.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_summarize_route(client, fake_llm):
    r = client.post("/summarize", json={
        "english": "top earners", "sql": "SELECT name FROM employees",
        "columns": ["name"], "rows": [["Alice"]], "api_key": "x",
    })
    d = r.get_json()
    assert r.status_code == 200
    assert "summary" in d


def test_summarize_requires_sql_and_api_key(client):
    assert client.post("/summarize", json={"sql": "", "api_key": "x"}).status_code == 400
    assert client.post("/summarize", json={"sql": "SELECT 1", "api_key": ""}).status_code == 400


def test_explain_route(client, fake_llm):
    r = client.post("/explain", json={
        "sql": "SELECT * FROM employees", "dialect": "postgresql", "api_key": "x",
    })
    d = r.get_json()
    assert r.status_code == 200
    assert "explanation" in d


def test_explain_requires_sql_and_api_key(client):
    assert client.post("/explain", json={"sql": "", "api_key": "x"}).status_code == 400
    assert client.post("/explain", json={"sql": "SELECT 1", "api_key": ""}).status_code == 400
