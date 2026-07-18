import os
import re
import io
import tempfile
import datetime as dt
from decimal import Decimal

import pandas as pd
from flask import Flask, request, jsonify, render_template, send_file
from groq import Groq
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

load_dotenv()  # loads GROQ_API_KEY / PORT / FLASK_DEBUG from a local .env, if present

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload limit

MAX_RETRIES = 3

# If set (via .env or the real environment), end users don't have to paste their
# own Groq API key in the browser — useful for a shared/team deployment.
DEFAULT_GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# ── Rate limiting ────────────────────────────────────────────────────────────
# In-memory storage — fine for a single-process/dev deployment. Under gunicorn
# with multiple workers, each worker keeps its own counter (so the *effective*
# limit is roughly limit × worker count); put a shared backend like Redis in
# front of this (storage_uri="redis://...") for a real multi-worker production
# deployment. Flagged in the README rather than silently pretended away.
limiter = Limiter(get_remote_address, app=app, default_limits=["120 per minute"])


@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": f"Rate limit exceeded — please slow down. ({e.description})"}), 429


# ── Column-level data masking ────────────────────────────────────────────────
# A basic data-governance guardrail: column *names* matching this list are
# redacted in query results server-side (the raw values never leave the
# server) unless the request explicitly opts in with reveal_masked=true —
# an explicit user action in the UI, never inferred from the English question.
DEFAULT_MASKED_COLUMNS = {
    "ssn", "social_security_number", "password", "passwd",
    "credit_card", "credit_card_number", "salary", "dob", "date_of_birth",
}
masked_columns = set(DEFAULT_MASKED_COLUMNS)  # mutable at runtime via /mask-settings
MASK_PLACEHOLDER = "•••• (masked)"


def _normalize_col_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def is_masked_column(name: str) -> bool:
    norm = _normalize_col_name(name)
    return any(norm == _normalize_col_name(m) for m in masked_columns)


def apply_masking(columns: list, rows: list, reveal: bool):
    """Redact values in any column whose name matches the masked list, unless
    reveal=True. Returns (rows, masked_column_names) — rows unchanged if
    nothing matched or reveal was requested."""
    if not rows:
        return rows, []
    mask_idx = [i for i, c in enumerate(columns) if is_masked_column(c)]
    if not mask_idx or reveal:
        return rows, [columns[i] for i in mask_idx]
    masked_rows = []
    for r in rows:
        r2 = list(r)
        for i in mask_idx:
            if r2[i] is not None:
                r2[i] = MASK_PLACEHOLDER
        masked_rows.append(r2)
    return masked_rows, [columns[i] for i in mask_idx]


# ── SQL safety guardrails ───────────────────────────────────────────────────
#
# This is a best-effort keyword classifier, not a full SQL parser. It is a
# defense-in-depth layer on top of the model's own instructions, not a
# substitute for running this against a database you don't mind the model
# writing to. String/identifier literals are blanked out before scanning so
# that e.g. WHERE comment = 'dropped the ball' doesn't false-positive.

BLOCKED_KEYWORDS = {
    "DROP", "ALTER", "TRUNCATE", "ATTACH", "DETACH",
    "VACUUM", "REINDEX", "GRANT", "REVOKE", "PRAGMA",
}
CONFIRM_KEYWORDS = {"INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "MERGE"}


def classify_sql(sql: str) -> str:
    """Classify SQL as 'read', 'confirm' (mutates data, needs user confirm),
    or 'blocked' (schema/permission-altering, never executed)."""
    if not sql:
        return "read"
    cleaned = re.sub(r"--[^\n]*", " ", sql)
    cleaned = re.sub(r"/\*.*?\*/", " ", cleaned, flags=re.S)
    cleaned = re.sub(r"'(?:[^'\\]|\\.)*'", " ", cleaned)
    cleaned = re.sub(r'"(?:[^"\\]|\\.)*"', " ", cleaned)
    tokens = set(re.findall(r"[A-Za-z]+", cleaned.upper()))
    if tokens & BLOCKED_KEYWORDS:
        return "blocked"
    if tokens & CONFIRM_KEYWORDS:
        return "confirm"
    return "read"


def guardrail_gate(classification: str, confirmed: bool):
    """Return a dict to short-circuit the response with, or None to proceed."""
    if classification == "blocked":
        return {
            "execution_status": "blocked",
            "final_status": "blocked",
            "guardrail_message": (
                "This statement would modify database schema, permissions, or "
                "internal settings (e.g. DROP / ALTER / TRUNCATE / PRAGMA). "
                "DataForge blocks these outright — rephrase your question as a read query."
            ),
        }
    if classification == "confirm" and not confirmed:
        return {
            "execution_status": "confirmation_required",
            "final_status": "confirmation_required",
            "guardrail_message": (
                "This statement will modify data (INSERT / UPDATE / DELETE / CREATE). "
                "Review the SQL below and confirm to run it."
            ),
        }
    return None


# ── JSON safety ──────────────────────────────────────────────────────────────

def _json_safe(v):
    """Postgres/MySQL drivers return datetime/Decimal/bytes objects that
    Flask's jsonify can't serialize on their own — normalize them."""
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (bytes, bytearray)):
        try:
            return v.decode("utf-8")
        except Exception:
            return v.hex()
    return v


# ── Database helpers (SQLAlchemy — works across SQLite / Postgres / MySQL) ──

DIALECT_HINTS = {
    "sqlite": "Use correct SQLite syntax (LIKE not ILIKE; date('now') not NOW()).",
    "postgresql": "Use correct PostgreSQL syntax (ILIKE is available for case-insensitive "
                   "matching; NOW() or CURRENT_TIMESTAMP for the current time).",
    "mysql": "Use correct MySQL syntax (NOW() for the current time; LIKE is case-insensitive "
             "by default on most collations).",
}


def get_engine(db_url: str):
    return create_engine(db_url, pool_pre_ping=True, pool_recycle=280)


def get_schema(engine) -> dict:
    """Return schema as {table: [col_defs]} and a compact string for the LLM."""
    insp = inspect(engine)
    tables = insp.get_table_names()

    schema_dict = {}
    schema_lines = []
    for t in tables:
        cols = insp.get_columns(t)
        try:
            pk_cols = set(insp.get_pk_constraint(t).get("constrained_columns") or [])
        except Exception:
            pk_cols = set()

        col_list, col_strs = [], []
        for c in cols:
            is_pk = c["name"] in pk_cols
            col_list.append({"name": c["name"], "type": str(c["type"]), "pk": is_pk})
            col_strs.append(f"{c['name']} {c['type']}{'  PK' if is_pk else ''}")

        schema_dict[t] = col_list
        schema_lines.append(f"{t}({', '.join(col_strs)})")

    return schema_dict, "\n".join(schema_lines)


def get_table_names(engine) -> list:
    return inspect(engine).get_table_names()


def generate_sql(english: str, schema_str: str, api_key: str, error_context: str = "",
                  table_names: list = None, dialect: str = "sqlite") -> str:
    """Call Groq (LLaMA 3) to convert English → SQL."""
    client = Groq(api_key=api_key)
    dialect = dialect if dialect in DIALECT_HINTS else "sqlite"

    union_hint = ""
    if table_names:
        union_parts = [f"SELECT '{t}' AS table_name, COUNT(*) AS row_count FROM {t}" for t in table_names]
        union_hint = f"""
- To count rows in every table, use UNION ALL:
  {chr(10) + '  UNION ALL'.join(f'{chr(10)}  ' + p for p in union_parts)}
"""

    system = f"""You are a {dialect.upper()} SQL expert. Convert the user's English question into a single executable {dialect.upper()} SQL query.

Database schema:
{schema_str}

Rules:
- Return ONLY the raw SQL statement. No markdown, no explanation, no code fences.
- {DIALECT_HINTS[dialect]}
- Never use DROP, ALTER, TRUNCATE, or other schema-modifying statements — the application blocks these outright regardless of what you generate.
- Only use INSERT, UPDATE, DELETE, or CREATE if the user's question explicitly asks to add/change/remove data — these require the user to confirm before running.
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


def summarize_results(english: str, sql: str, columns: list, rows: list, api_key: str) -> str:
    """Ask the model for a short plain-English takeaway from a result set —
    for a non-technical stakeholder who wants "what does this mean", not
    another look at the table."""
    client = Groq(api_key=api_key)
    sample = rows[:50]
    preview_lines = [", ".join(str(c) for c in columns)]
    for r in sample:
        preview_lines.append(", ".join("" if v is None else str(v) for v in r))
    preview = "\n".join(preview_lines)

    system = (
        "You are a data analyst. Given a user's question, the SQL query that answered it, "
        "and a preview of the result rows, write a short plain-English takeaway (2-4 sentences, "
        "no jargon, no markdown, do not restate the SQL). Focus on what the data actually shows — "
        "trends, standouts, totals — not how it was computed. If the result set is empty, say so plainly."
    )
    user = (
        f"Question: {english}\n\nSQL: {sql}\n\n"
        f"Result preview ({len(rows)} total row(s), showing up to 50):\n{preview}"
    )
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


def explain_sql(sql: str, api_key: str, dialect: str = "sqlite") -> str:
    """Ask the model to translate a SQL statement back into plain English,
    for a non-technical reviewer sanity-checking what will actually run."""
    client = Groq(api_key=api_key)
    system = (
        f"You are a patient teacher explaining {dialect.upper()} SQL to someone with no "
        "technical background. Explain what the following query does in plain English — "
        "2-4 sentences, no jargon, no markdown, do not restate the SQL syntax verbatim."
    )
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": sql}],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


def clean_database(engine) -> dict:
    """Auto-clean every table in the database:
      - trims leading/trailing whitespace on text columns
      - converts blank strings to NULL
      - drops duplicate rows (compared on non-primary-key columns)
    Table structure (columns, types, primary keys, indexes) is preserved —
    rows are cleaned in a DataFrame, then the table is emptied and
    re-populated via DELETE + INSERT (no DROP/CREATE). Works across
    SQLite/Postgres/MySQL using each dialect's identifier quoting rules.
    """
    insp = inspect(engine)
    tables = insp.get_table_names()
    prep = engine.dialect.identifier_preparer

    summary = {}
    for t in tables:
        quoted = prep.quote(t)
        df = pd.read_sql_query(f"SELECT * FROM {quoted}", engine)
        rows_before = len(df)

        cells_trimmed = 0
        for col in df.select_dtypes(include="object").columns:
            trimmed = df[col].apply(lambda v: v.strip() if isinstance(v, str) else v)
            cells_trimmed += int((trimmed != df[col]).sum())
            df[col] = trimmed
            blanks = df[col].apply(lambda v: isinstance(v, str) and v == "")
            df.loc[blanks, col] = None

        try:
            pk_cols = set(insp.get_pk_constraint(t).get("constrained_columns") or [])
        except Exception:
            pk_cols = set()
        compare_cols = [c for c in df.columns if c not in pk_cols] or list(df.columns)

        deduped = df.drop_duplicates(subset=compare_cols, keep="first")
        duplicates_removed = rows_before - len(deduped)

        if duplicates_removed > 0 or cells_trimmed > 0:
            cols = list(deduped.columns)
            col_list = ", ".join(prep.quote(c) for c in cols)
            placeholders = ", ".join(f":p{i}" for i in range(len(cols)))
            records = [
                {f"p{i}": (None if pd.isna(v) else v) for i, v in enumerate(row)}
                for row in deduped.itertuples(index=False, name=None)
            ]
            with engine.begin() as conn:
                conn.execute(text(f"DELETE FROM {quoted}"))
                if records:
                    conn.execute(
                        text(f"INSERT INTO {quoted} ({col_list}) VALUES ({placeholders})"),
                        records,
                    )

        summary[t] = {
            "rows_before":        rows_before,
            "rows_after":         len(deduped),
            "duplicates_removed": duplicates_removed,
            "cells_trimmed":      cells_trimmed,
        }

    return summary


def _sanitize_identifier(name: str, fallback: str = "col") -> str:
    """Turn an arbitrary column/sheet name into a safe SQL identifier."""
    name = re.sub(r"[^0-9a-zA-Z_]", "_", str(name).strip())
    if not name:
        name = fallback
    if name[0].isdigit():
        name = f"_{name}"
    return name


def spreadsheet_to_sqlite(file_storage, filename: str) -> str:
    """Convert an uploaded .csv or .xlsx/.xls file into a fresh SQLite
    database file and return its path. Each Excel sheet becomes its own
    table; a CSV becomes a single table named after the file. This lets
    anyone without a ready-made .db file still use the whole pipeline."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_engine(f"sqlite:///{tmp.name}")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "csv":
        df = pd.read_csv(file_storage)
        table_name = _sanitize_identifier(filename.rsplit(".", 1)[0], "data")
        df.columns = [_sanitize_identifier(c) for c in df.columns]
        df.to_sql(table_name, engine, index=False, if_exists="replace")
    else:  # xlsx / xls — one table per sheet
        sheets = pd.read_excel(file_storage, sheet_name=None)
        for sheet_name, sheet_df in sheets.items():
            table_name = _sanitize_identifier(sheet_name, "sheet")
            sheet_df.columns = [_sanitize_identifier(c) for c in sheet_df.columns]
            sheet_df.to_sql(table_name, engine, index=False, if_exists="replace")

    return tmp.name


def execute_sql(sql: str, engine):
    """Run SQL via the raw DBAPI connection (bypassing SQLAlchemy's textual
    bind-parameter parsing, which would otherwise misinterpret literal colons
    in e.g. time strings '14:30:00' as bind params). Return (rows, columns, error)."""
    try:
        raw_conn = engine.raw_connection()
        try:
            cur = raw_conn.cursor()
            cur.execute(sql)
            if cur.description:
                cols = [d[0] for d in cur.description]
                rows = [[_json_safe(v) for v in row] for row in cur.fetchall()]
            else:
                cols, rows = [], []
            raw_conn.commit()
            return rows, cols, None
        finally:
            raw_conn.close()
    except Exception as e:
        return None, None, str(e)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", has_server_api_key=bool(DEFAULT_GROQ_API_KEY))


@app.route("/upload", methods=["POST"])
def upload():
    """Receive a .db, .csv, or .xlsx/.xls file and return its schema.
    Spreadsheets are converted into a fresh SQLite database (one table per
    sheet for Excel; a single table for CSV) so the rest of the pipeline —
    querying, cleaning, exporting — is unchanged either way."""
    if "db_file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["db_file"]
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""

    if ext not in ("db", "csv", "xlsx", "xls"):
        return jsonify({"error": "Please upload a .db, .csv, or .xlsx file"}), 400

    try:
        if ext == "db":
            tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
            f.save(tmp.name)
            tmp.close()
            db_path = tmp.name
        else:
            db_path = spreadsheet_to_sqlite(f, f.filename)
    except Exception as e:
        return jsonify({"error": f"Could not read file: {e}"}), 400

    db_url = f"sqlite:///{db_path}"
    try:
        engine = get_engine(db_url)
        schema_dict, schema_str = get_schema(engine)
    except Exception as e:
        os.unlink(db_path)
        return jsonify({"error": f"Could not read database: {e}"}), 400

    return jsonify({
        "db_url":     db_url,
        "schema":     schema_dict,
        "schema_str": schema_str,
        "tables":     list(schema_dict.keys()),
        "engine":     "sqlite",
        "label":      f.filename,
    })


@app.route("/connect", methods=["POST"])
@limiter.limit("10 per minute")
def connect():
    """Connect to an external Postgres/MySQL database via a SQLAlchemy URL,
    e.g. postgresql://user:pass@host:5432/dbname or mysql+pymysql://user:pass@host/dbname."""
    data = request.get_json()
    db_url = (data.get("db_url") or "").strip()

    if not db_url:
        return jsonify({"error": "Connection string is required"}), 400

    try:
        engine = get_engine(db_url)
        schema_dict, schema_str = get_schema(engine)
        if not schema_dict:
            return jsonify({"error": "Connected, but no tables were found in this database."}), 400
    except Exception as e:
        return jsonify({"error": f"Could not connect: {e}"}), 400

    return jsonify({
        "db_url":     db_url,
        "schema":     schema_dict,
        "schema_str": schema_str,
        "tables":     list(schema_dict.keys()),
        "engine":     engine.dialect.name,
        "label":      f"{engine.dialect.name} — {engine.url.database or 'connected'}",
    })


@app.route("/clean", methods=["POST"])
def clean():
    """Auto-clean the currently connected database: dedupe rows, trim whitespace,
    blank strings -> NULL. Returns a per-table before/after summary."""
    data = request.get_json()
    db_url = data.get("db_url", "")

    if not db_url:
        return jsonify({"error": "No database connected. Upload a file or connect to a database first."}), 400

    try:
        engine = get_engine(db_url)
        summary = clean_database(engine)
        return jsonify({"summary": summary})
    except Exception as e:
        return jsonify({"error": f"Cleaning failed: {e}"}), 500


@app.route("/query", methods=["POST"])
@limiter.limit("20 per minute")
def query():
    """Convert English → SQL → (guardrail check) → execute → debug loop."""
    data = request.get_json()
    english    = (data.get("english") or "").strip()
    db_url     = data.get("db_url", "")
    api_key    = (data.get("api_key") or DEFAULT_GROQ_API_KEY or "").strip()
    schema_str = data.get("schema_str", "")
    confirmed      = bool(data.get("confirmed", False))
    sql_override   = (data.get("sql_override") or "").strip()
    reveal_masked  = bool(data.get("reveal_masked", False))

    if not english:
        return jsonify({"error": "Query cannot be empty"}), 400
    if not db_url:
        return jsonify({"error": "No database connected. Upload a file or connect to a database first."}), 400
    if not api_key:
        return jsonify({"error": "Groq API key is required"}), 400

    result = {
        "english_query":     english,
        "sql_generated":     None,
        "execution_status":  None,
        "error_message":     None,
        "guardrail_message": None,
        "debug_attempts":    [],
        "final_sql":         None,
        "final_status":      None,
        "result_rows":       None,
        "columns":           [],
        "rows":              [],
        "masked_columns":    [],
    }

    try:
        engine  = get_engine(db_url)
        dialect = engine.dialect.name
        table_names = get_table_names(engine)

        # If the caller already had this exact SQL confirmed by the user (the
        # "Run Anyway" path after a confirmation_required response), execute
        # that same statement rather than asking the model to regenerate it —
        # avoids any drift between what the user reviewed and what runs.
        if sql_override and confirmed:
            sql = sql_override
        else:
            sql = generate_sql(english, schema_str, api_key, table_names=table_names, dialect=dialect)
        result["sql_generated"] = sql
        result["final_sql"] = sql

        gate = guardrail_gate(classify_sql(sql), confirmed)
        if gate:
            result.update(gate)
            return jsonify(result)

        rows, cols, error = execute_sql(sql, engine)

        if not error:
            masked_rows, masked_cols = apply_masking(cols, rows, reveal_masked)
            result.update({
                "execution_status": "success",
                "final_status":     "success",
                "result_rows":      len(rows),
                "columns":          cols,
                "rows":             masked_rows,
                "masked_columns":   masked_cols,
            })
            return jsonify(result)

        result["execution_status"] = "failed"
        result["error_message"]    = error

        for attempt in range(1, MAX_RETRIES + 1):
            error_context = f"Error: {error}\nFailed SQL:\n{sql}"
            sql = generate_sql(english, schema_str, api_key, error_context=error_context,
                                table_names=table_names, dialect=dialect)
            result["final_sql"] = sql

            gate = guardrail_gate(classify_sql(sql), confirmed)
            if gate:
                result["debug_attempts"].append({
                    "attempt": attempt, "modified_sql": sql, "error": None,
                    "status": gate["final_status"],
                })
                result.update(gate)
                return jsonify(result)

            rows, cols, error = execute_sql(sql, engine)
            entry = {"attempt": attempt, "modified_sql": sql, "error": error}

            if not error:
                masked_rows, masked_cols = apply_masking(cols, rows, reveal_masked)
                entry["status"] = "success"
                result["debug_attempts"].append(entry)
                result.update({
                    "final_sql":      sql,
                    "final_status":   "success",
                    "result_rows":    len(rows),
                    "columns":        cols,
                    "rows":           masked_rows,
                    "masked_columns": masked_cols,
                })
                return jsonify(result)
            else:
                entry["status"] = "failed"
                result["debug_attempts"].append(entry)

        result.update({
            "final_sql":     sql,
            "final_status":  f"failed_after_{MAX_RETRIES}_attempts",
            "error_message": error,
        })
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/export/xlsx", methods=["POST"])
def export_xlsx():
    """Export a result set (already fetched by the client) to a .xlsx file."""
    data = request.get_json()
    columns  = data.get("columns") or []
    rows     = data.get("rows") or []
    filename = (data.get("filename") or "query_results.xlsx").strip()
    if not filename.endswith(".xlsx"):
        filename += ".xlsx"

    try:
        df = pd.DataFrame(rows, columns=columns)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Results")
        buf.seek(0)
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        return jsonify({"error": f"Export failed: {e}"}), 500


@app.route("/summarize", methods=["POST"])
@limiter.limit("20 per minute")
def summarize():
    """Plain-English takeaway for a result set already fetched by the client."""
    data = request.get_json()
    english = (data.get("english") or "").strip()
    sql     = (data.get("sql") or "").strip()
    columns = data.get("columns") or []
    rows    = data.get("rows") or []
    api_key = (data.get("api_key") or DEFAULT_GROQ_API_KEY or "").strip()

    if not sql:
        return jsonify({"error": "No SQL to summarize"}), 400
    if not api_key:
        return jsonify({"error": "Groq API key is required"}), 400

    try:
        summary = summarize_results(english, sql, columns, rows, api_key)
        return jsonify({"summary": summary})
    except Exception as e:
        return jsonify({"error": f"Summary failed: {e}"}), 500


@app.route("/explain", methods=["POST"])
@limiter.limit("20 per minute")
def explain():
    """Plain-English explanation of a generated SQL statement."""
    data = request.get_json()
    sql     = (data.get("sql") or "").strip()
    dialect = (data.get("dialect") or "sqlite").strip()
    api_key = (data.get("api_key") or DEFAULT_GROQ_API_KEY or "").strip()

    if not sql:
        return jsonify({"error": "No SQL to explain"}), 400
    if not api_key:
        return jsonify({"error": "Groq API key is required"}), 400

    try:
        explanation = explain_sql(sql, api_key, dialect)
        return jsonify({"explanation": explanation})
    except Exception as e:
        return jsonify({"error": f"Explain failed: {e}"}), 500


@app.route("/mask-settings", methods=["GET", "POST"])
def mask_settings():
    """View or replace the set of column-name patterns treated as sensitive.
    In-memory and process-wide (not per-user, not persisted across restarts) —
    fine for a single local/demo deployment; a real multi-tenant setup would
    need this scoped per user or database instead."""
    global masked_columns
    if request.method == "POST":
        data = request.get_json() or {}
        cols = data.get("columns")
        if isinstance(cols, list):
            masked_columns = {str(c).strip() for c in cols if str(c).strip()}
    return jsonify({"masked_columns": sorted(masked_columns)})


if __name__ == "__main__":
    port  = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "true").strip().lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", debug=debug, port=port)
