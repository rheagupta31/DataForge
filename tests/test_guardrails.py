"""Tests for the code-enforced SQL safety guardrails in app.py."""
import pytest

from app import classify_sql, guardrail_gate


@pytest.mark.parametrize("sql,expected", [
    ("SELECT * FROM employees", "read"),
    ("SELECT * FROM employees WHERE name = 'dropped the ball'", "read"),
    ("SELECT * FROM t WHERE comment = 'please CREATE something'", "read"),
    ("DROP TABLE employees", "blocked"),
    ("ALTER TABLE employees ADD COLUMN x INT", "blocked"),
    ("TRUNCATE TABLE employees", "blocked"),
    ("PRAGMA table_info(employees)", "blocked"),
    ("DELETE FROM employees WHERE id=1", "confirm"),
    ("UPDATE employees SET salary=1 WHERE id=1", "confirm"),
    ("INSERT INTO employees (name) VALUES ('x')", "confirm"),
    ("CREATE TABLE notes (id INT)", "confirm"),
    ("SELECT * FROM orders WHERE order_time = '14:30:00'", "read"),
    ("SELECT * FROM employees; DROP TABLE employees;", "blocked"),
    ("", "read"),
    (None, "read"),
])
def test_classify_sql(sql, expected):
    assert classify_sql(sql) == expected


def test_guardrail_gate_blocked_returns_gate():
    gate = guardrail_gate("blocked", confirmed=True)
    assert gate is not None
    assert gate["final_status"] == "blocked"


def test_guardrail_gate_confirm_required_when_not_confirmed():
    gate = guardrail_gate("confirm", confirmed=False)
    assert gate is not None
    assert gate["final_status"] == "confirmation_required"


def test_guardrail_gate_confirm_passes_when_confirmed():
    assert guardrail_gate("confirm", confirmed=True) is None


def test_guardrail_gate_read_always_passes():
    assert guardrail_gate("read", confirmed=False) is None
    assert guardrail_gate("read", confirmed=True) is None
