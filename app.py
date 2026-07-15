import os
import re
import json
import sqlite3
import tempfile

import pandas as pd
from flask import Flask, request, jsonify, render_template
from groq import Groq

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload limit

MAX_RETRIES = 3


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_schema(db_path: str) -> dict:
    """Return schema as {table: [col_defs]} and a compact string for GPT."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]

    schema_dict = {}
    schema_lines = []
    for t in tables:
        cur.execute(f"PRAGMA table_info({t})")
        rows = cur.fetchall()
        cols = [{"name": r[1], "type": r[2], "pk": bool(r[5])} for r in rows]
        schema_dict[t] = cols
        col_strs = [f"{r[1]} {r[2]}{'  PK' if r[5] else ''}" for r in rows]
        schema_lines.append(f"{t}({', '.join(col_strs)})")

    conn.close()
    return schema_dict, "\n".join(schema_lines)


def get_table_names(db_path: str) -> list[str]:
    """Return all table names from the database."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    conn.close()
    return tables


def generate_sql(english: str, schema_str: str, api_key: str, error_context: str = "",
                 table_names: list = None) -> str:
    """Call Groq (LLaMA 3) to convert English → SQL."""
    client = Groq(api_key=api_key)

    # Build a UNION ALL snippet as a hint for "count rows" style queries
    union_hint = ""
    if table_names:
        union_parts = [f"SELECT '{t}' AS table_name, COUNT(*) AS row_count FROM {t}" for t in table_names]
        union_hint = f"""
- To count rows in every table, use UNION ALL:
  {chr(10) + '  UNION ALL'.join(f'{chr(10)}  ' + p for p in union_parts)}
"""

    system = f"""You are a SQLite SQL expert. Convert the user's English question into a single executable SQLite SQL query.

Database schema:
{schema_str}

Rules:
- Return ONLY the raw SQL statement. No markdown, no explanation, no code fences.
- Use correct SQLite syntax (LIKE not ILIKE; date('now') not NOW(); etc.).
- Never use DROP, DELETE, or ALTER unless explicitly confirmed by the user.
- Match the query EXACTLY to what the user asked — do not substitute a different query.
- For aggregations across ALL tables (e.g. "count rows in each table"), use UNION ALL over every table in the schema.{union_hint}
"""
    if error_context:
        system += f"\nPrevious attempt failed:\n{error_context}\nFix the SQL accordingly."

    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": english},
        ],
        temperature=0,
    )
    sql = resp.choices[0].message.content.strip()
    sql = re.sub(r"^```[\w]*\n?", "", sql)
    sql = re.sub(r"\n?```$", "", sql)
    return sql.strip()


def clean_database(db_path: str) -> dict:
    """Auto-clean every table in the database:
      - trims leading/trailing whitespace on text columns
      - converts blank strings to NULL
      - drops exact duplicate rows
    Table structure (columns, types, primary keys, indexes) is preserved —
    rows are cleaned in a DataFrame, then the table is emptied and
    re-populated via DELETE + INSERT (no DROP/CREATE).
    Returns a per-table summary of what changed.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]

    summary = {}
    for t in tables:
        df = pd.read_sql_query(f'SELECT * FROM "{t}"', conn)
        rows_before = len(df)

        cells_trimmed = 0
        for col in df.select_dtypes(include="object").columns:
            trimmed = df[col].apply(lambda v: v.strip() if isinstance(v, str) else v)
            cells_trimmed += int((trimmed != df[col]).sum())
            df[col] = trimmed
            blanks = df[col].apply(lambda v: isinstance(v, str) and v == "")
            df.loc[blanks, col] = None

        # Dedupe on non-primary-key columns — an autoincrement PK makes every
        # row "unique" even when the real data is a duplicate, so PK columns
        # are excluded from the comparison (the first occurrence, with its
        # original PK, is kept).
        cur.execute(f'PRAGMA table_info("{t}")')
        pk_cols = [r[1] for r in cur.fetchall() if r[5]]
        compare_cols = [c for c in df.columns if c not in pk_cols] or list(df.columns)

        deduped = df.drop_duplicates(subset=compare_cols, keep="first")
        duplicates_removed = rows_before - len(deduped)

        if duplicates_removed > 0 or cells_trimmed > 0:
            cols = list(deduped.columns)
            col_list = ", ".join(f'"{c}"' for c in cols)
            placeholders = ", ".join("?" for _ in cols)
            records = [
                tuple(None if pd.isna(v) else v for v in row)
                for row in deduped.itertuples(index=False, name=None)
            ]
            cur.execute(f'DELETE FROM "{t}"')
            if records:
                cur.executemany(
                    f'INSERT INTO "{t}" ({col_list}) VALUES ({placeholders})', records
                )

        summary[t] = {
            "rows_before":        rows_before,
            "rows_after":         len(deduped),
            "duplicates_removed": duplicates_removed,
            "cells_trimmed":      cells_trimmed,
        }

    conn.commit()
    conn.close()
    return summary


def execute_sql(sql: str, db_path: str):
    """Run SQL; return (rows, columns, error)."""
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        conn.commit()
        conn.close()
        return rows, cols, None
    except Exception as e:
        return None, None, str(e)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    """Receive .db file, save to a temp location, return schema."""
    if "db_file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["db_file"]
    if not f.filename.endswith(".db"):
        return jsonify({"error": "Please upload a .db (SQLite) file"}), 400

    # Save to a temporary file that persists for the session
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.save(tmp.name)
    tmp.close()

    try:
        schema_dict, schema_str = get_schema(tmp.name)
    except Exception as e:
        os.unlink(tmp.name)
        return jsonify({"error": f"Could not read database: {e}"}), 400

    return jsonify({
        "db_path":    tmp.name,
        "schema":     schema_dict,
        "schema_str": schema_str,
        "tables":     list(schema_dict.keys()),
    })


@app.route("/clean", methods=["POST"])
def clean():
    """Auto-clean the currently loaded database: dedupe rows, trim whitespace,
    blank strings -> NULL. Returns a per-table before/after summary."""
    data = request.get_json()
    db_path = data.get("db_path", "")

    if not db_path or not os.path.exists(db_path):
        return jsonify({"error": "No database loaded. Please upload a .db file first."}), 400

    try:
        summary = clean_database(db_path)
        return jsonify({"summary": summary})
    except Exception as e:
        return jsonify({"error": f"Cleaning failed: {e}"}), 500


@app.route("/query", methods=["POST"])
def query():
    """Convert English → SQL → execute → debug loop."""
    data = request.get_json()
    english    = data.get("english", "").strip()
    db_path    = data.get("db_path", "")
    api_key    = data.get("api_key", "").strip()
    schema_str = data.get("schema_str", "")

    if not english:
        return jsonify({"error": "Query cannot be empty"}), 400
    if not db_path or not os.path.exists(db_path):
        return jsonify({"error": "No database loaded. Please upload a .db file first."}), 400
    if not api_key:
        return jsonify({"error": "Groq API key is required"}), 400

    result = {
        "english_query":    english,
        "sql_generated":    None,
        "execution_status": None,
        "error_message":    None,
        "debug_attempts":   [],
        "final_sql":        None,
        "final_status":     None,
        "result_rows":      None,
        "columns":          [],
        "rows":             [],
    }

    try:
        table_names = get_table_names(db_path)

        # Initial generation
        sql = generate_sql(english, schema_str, api_key, table_names=table_names)
        result["sql_generated"] = sql

        rows, cols, error = execute_sql(sql, db_path)

        if not error:
            result.update({
                "execution_status": "success",
                "final_sql":        sql,
                "final_status":     "success",
                "result_rows":      len(rows),
                "columns":          cols,
                "rows":             [list(r) for r in rows],
            })
            return jsonify(result)

        # Failed → debug loop
        result["execution_status"] = "failed"
        result["error_message"]    = error

        for attempt in range(1, MAX_RETRIES + 1):
            error_context = f"Error: {error}\nFailed SQL:\n{sql}"
            sql = generate_sql(english, schema_str, api_key, error_context=error_context,
                               table_names=table_names)
            rows, cols, error = execute_sql(sql, db_path)

            entry = {"attempt": attempt, "modified_sql": sql, "error": error}

            if not error:
                entry["status"] = "success"
                result["debug_attempts"].append(entry)
                result.update({
                    "final_sql":    sql,
                    "final_status": "success",
                    "result_rows":  len(rows),
                    "columns":      cols,
                    "rows":         [list(r) for r in rows],
                })
                return jsonify(result)
            else:
                entry["status"] = "failed"
                result["debug_attempts"].append(entry)

        result.update({
            "final_sql":    sql,
            "final_status": f"failed_after_{MAX_RETRIES}_attempts",
            "error_message": error,
        })
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
