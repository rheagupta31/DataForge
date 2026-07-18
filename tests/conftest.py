"""Shared pytest fixtures for the DataForge test suite.

Tests never hit the real Groq API or mutate the repo's tracked database.db —
generate_sql/summarize_results/explain_sql are monkeypatched with
deterministic stand-ins, and the sample database is copied to a pytest
tmp_path before each test that touches it.
"""
import os
import shutil
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import app as appmod  # noqa: E402


@pytest.fixture(autouse=True)
def _disable_rate_limiting():
    """Rate limiting uses process-wide in-memory counters, which would make
    unrelated tests order-dependent and flaky. Off by default; the dedicated
    rate-limit test re-enables and resets it explicitly."""
    appmod.limiter.enabled = False
    yield
    appmod.limiter.enabled = False


@pytest.fixture
def client():
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


@pytest.fixture
def sample_db_path():
    """Absolute path to the repo's sample database.db (read-only use)."""
    return os.path.join(REPO_ROOT, "database.db")


@pytest.fixture
def sample_db_url(tmp_path, sample_db_path):
    """Copy database.db to a throwaway location and return a sqlite:/// URL,
    so tests that clean/mutate data never touch the tracked file."""
    dst = tmp_path / "test.db"
    shutil.copy(sample_db_path, dst)
    return f"sqlite:///{dst}"


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace the Groq-backed functions with deterministic stand-ins so the
    suite runs offline and without a real API key."""

    def fake_generate_sql(english, schema_str, api_key, error_context="",
                           table_names=None, dialect="sqlite"):
        e = english.lower()
        if "drop" in e:
            return "DROP TABLE employees"
        if "delete" in e:
            return "DELETE FROM order_items WHERE item_id = 999999"
        if "create" in e:
            return "CREATE TABLE notes (id INTEGER, body TEXT)"
        return "SELECT name, salary FROM employees WHERE salary > 50000"

    def fake_summarize(english, sql, columns, rows, api_key):
        return f"Summary of {len(rows)} row(s) for: {english}"

    def fake_explain(sql, api_key, dialect="sqlite"):
        return f"Plain-English explanation of: {sql[:30]}"

    monkeypatch.setattr(appmod, "generate_sql", fake_generate_sql)
    monkeypatch.setattr(appmod, "summarize_results", fake_summarize)
    monkeypatch.setattr(appmod, "explain_sql", fake_explain)

    return {"generate_sql": fake_generate_sql, "summarize": fake_summarize, "explain": fake_explain}
