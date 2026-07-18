"""Tests for the SQLAlchemy-based database helpers in app.py (schema
introspection, execution, cleaning) against a disposable copy of the sample
SQLite database."""
from sqlalchemy import text

from app import get_engine, get_schema, get_table_names, execute_sql, clean_database


def test_get_schema_returns_expected_tables_and_pk_flags(sample_db_url):
    engine = get_engine(sample_db_url)
    schema, schema_str = get_schema(engine)

    assert "employees" in schema
    assert any(c["pk"] for c in schema["employees"])
    assert "employees(" in schema_str


def test_get_table_names(sample_db_url):
    engine = get_engine(sample_db_url)
    tables = set(get_table_names(engine))
    assert tables == {"customers", "departments", "employees", "order_items", "orders", "products"}


def test_execute_sql_basic_select(sample_db_url):
    engine = get_engine(sample_db_url)
    rows, cols, err = execute_sql("SELECT COUNT(*) AS n FROM employees", engine)
    assert err is None
    assert cols == ["n"]
    assert rows[0][0] > 0


def test_execute_sql_colon_literal_not_misparsed_as_bind_param(sample_db_url):
    """Regression test: SQLAlchemy's text()/connection.execute() treats a
    literal ':30' inside a string as a bind parameter placeholder. execute_sql
    must go through the raw DBAPI connection to avoid that."""
    engine = get_engine(sample_db_url)
    rows, cols, err = execute_sql("SELECT '14:30:00' AS t", engine)
    assert err is None
    assert rows[0][0] == "14:30:00"


def test_execute_sql_surfaces_errors_without_raising(sample_db_url):
    engine = get_engine(sample_db_url)
    rows, cols, err = execute_sql("SELECT * FROM not_a_real_table", engine)
    assert rows is None and cols is None
    assert err is not None


def test_clean_database_dedupes_ignoring_autoincrement_pk(sample_db_url):
    engine = get_engine(sample_db_url)

    # order_items has no unique constraints beyond its PK, so it's a valid
    # place to prove a "same data, different autoincrement id" row counts
    # as a duplicate once the PK column is excluded from comparison.
    with engine.begin() as conn:
        row = dict(conn.execute(text("SELECT * FROM order_items LIMIT 1")).mappings().first())
        max_id = conn.execute(text("SELECT MAX(item_id) FROM order_items")).scalar()
        row["item_id"] = max_id + 1
        cols = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row.keys())
        conn.execute(text(f"INSERT INTO order_items ({cols}) VALUES ({placeholders})"), row)

    before = conn = None
    with engine.begin() as conn:
        before = conn.execute(text("SELECT COUNT(*) FROM order_items")).scalar()

    summary = clean_database(engine)
    assert summary["order_items"]["duplicates_removed"] == 1
    assert summary["order_items"]["rows_after"] == before - 1

    # Table structure (not just row count) must be untouched.
    schema, _ = get_schema(engine)
    assert "item_id" in [c["name"] for c in schema["order_items"]]


def test_clean_database_trims_whitespace_and_blanks_to_null(sample_db_url):
    engine = get_engine(sample_db_url)
    with engine.begin() as conn:
        conn.execute(text("UPDATE employees SET role = '  Manager  ' WHERE employee_id = "
                           "(SELECT MIN(employee_id) FROM employees)"))

    summary = clean_database(engine)
    assert summary["employees"]["cells_trimmed"] >= 1

    with engine.begin() as conn:
        cleaned = conn.execute(text("SELECT role FROM employees WHERE role = 'Manager'")).fetchall()
    assert len(cleaned) >= 1
