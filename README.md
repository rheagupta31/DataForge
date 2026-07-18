# DataForge

> **Convert plain English into executable SQL — instantly.**

DataForge is an AI-powered web application that translates natural language queries into SQL, executes them against SQLite, PostgreSQL, or MySQL, and autonomously debugs any errors — all from a clean, cinematic interface. Destructive statements are blocked in code, mutating statements require explicit confirmation, sensitive columns are redacted by default, and every query is logged locally with one-click CSV/Excel export.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=flat-square&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0%2B-black?style=flat-square&logo=flask)
![Groq](https://img.shields.io/badge/Groq-LLaMA%203.3-orange?style=flat-square)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-red?style=flat-square)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker)
![Tests](https://github.com/rheagupta31/DataForge/actions/workflows/tests.yml/badge.svg)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Installation](#installation)
- [Usage](#usage)
- [Security & Safety Guardrails](#security--safety-guardrails)
- [Deployment](#deployment)
- [Testing & CI](#testing--ci)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)
- [License](#license)
- [Author](#author)

---

## Features

- **Natural Language to SQL** — Ask questions in plain English; LLaMA 3.3 70B (via Groq) generates the correct SQL for your connected database's dialect.
- **Multi-Database Support** — Upload a SQLite `.db` file, or connect directly to a PostgreSQL or MySQL database with a connection string. Schema introspection, query generation, and execution all adapt automatically to the connected engine.
- **CSV / Excel Upload** — No `.db` file? Drop in a `.csv` or `.xlsx` instead — DataForge converts it into a SQLite database on the fly (one table per Excel sheet) and the rest of the pipeline works exactly the same.
- **Autonomous Error Debugging** — If a query fails, the engine feeds the error back to the model and retries up to 3 times without any manual intervention.
- **Code-Enforced Safety Guardrails** — Schema/permission-altering statements (`DROP`, `ALTER`, `TRUNCATE`, `PRAGMA`, etc.) are blocked outright at the application layer. Data-mutating statements (`INSERT` / `UPDATE` / `DELETE` / `CREATE`) require an explicit "Run Anyway" confirmation before they execute — this is enforced in `app.py`, not just in the model's instructions.
- **Column-Level Data Masking** — Sensitive columns (salary, SSN, password, credit card, date of birth, by default) are redacted server-side in every result unless you explicitly check "Reveal sensitive columns" for that query. The masked list is editable from the UI.
- **Rate Limiting** — Basic per-IP limits on the query, connect, and insight endpoints so one user or a runaway script can't hammer the Groq API or the database.
- **Plain-English Insights** — Click "Summarize" on any result set for a 2-4 sentence plain-English takeaway, and "Explain SQL" on the generated query to have it translated back into plain English for a non-technical reviewer to sanity-check.
- **Query History & Export** — Every query is logged locally (with status) in a sidebar history panel for quick re-use. Any result set can be exported to CSV or Excel (`.xlsx`) with one click.
- **Live Schema Explorer** — A collapsible sidebar shows every table, column, type, and primary key in the connected database.
- **Automated Data Cleaning** — Click "Clean Data" to dedupe rows, trim whitespace, and convert blank strings to NULL across every table, on demand. Table structure (columns, types, primary keys) is preserved; a before/after report shows exactly what changed.
- **On-Demand Visualizations** — Click "Visualize" on any result set with numeric data to render an interactive bar, line, or pie chart (Chart.js) directly from the query results — no extra queries, no server round-trip.
- **Production-Ready Deployment** — Ships with a `Dockerfile`, `.env`-based configuration, and a gunicorn entrypoint, so it's not just a `flask run` script.
- **Tested & CI'd** — A pytest suite (48 tests) covers the guardrails, the database layer, and every route; GitHub Actions runs it on every push and PR across Python 3.10–3.12.
- **Cinematic Dark UI** — Built with Inter, Space Grotesk, and JetBrains Mono. SQL output includes full syntax highlighting. Results render in a clean table with a JSON output panel.

---

## Tech Stack

| Layer          | Technology                                        |
|----------------|----------------------------------------------------|
| Backend        | Python 3.9+, Flask 3.0                             |
| Database layer | SQLAlchemy 2.0 (SQLite / PostgreSQL / MySQL)       |
| AI Model       | LLaMA 3.3 70B via Groq API                         |
| Data Cleaning  | pandas                                             |
| Export         | pandas + openpyxl (Excel), native CSV (client-side)|
| Charts         | Chart.js (CDN, client-side)                        |
| Frontend       | Vanilla HTML, CSS, JavaScript                      |
| Config         | python-dotenv (`.env`)                             |
| Rate limiting  | Flask-Limiter                                      |
| Testing        | pytest, GitHub Actions                             |
| Production server | gunicorn                                        |
| Container      | Docker                                             |
| Fonts          | Inter · Space Grotesk · JetBrains Mono (Google Fonts) |

---

## Installation

### Prerequisites

- Python 3.9 or higher
- A free [Groq API key](https://console.groq.com/keys) — no credit card required
- (Optional) A running PostgreSQL or MySQL instance, if you want to connect to one instead of using SQLite

### Steps

**1. Clone the repository**

```bash
git clone https://github.com/rheagupta31/DataForge.git
cd DataForge
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. (Optional) Configure environment variables**

```bash
cp .env.example .env
```

Edit `.env` to set a `GROQ_API_KEY` if you want end users to skip pasting their own key. Leave it blank to require each user to supply their own.

**4. (Optional) Generate the sample database**

If you don't have your own `.db` file, run the included setup script to create a sample database with 6 tables and realistic data:

```bash
python setup_database.py
```

This creates `database.db` in the project root with the following schema:

```
departments   — department_id, name, budget
employees     — employee_id, name, email, department_id, salary, hire_date, role
customers     — customer_id, name, email, city, signup_date
products      — product_id, name, category, price, stock
orders        — order_id, customer_id, order_date, status, total
order_items   — item_id, order_id, product_id, quantity, unit_price
```

**5. Start the server**

```bash
python app.py
```

**6. Open the app**

Navigate to [http://localhost:5000](http://localhost:5000) in your browser.

---

## Usage

### Step-by-step

1. **Enter your Groq API key** in the sidebar field (starts with `gsk_`) — unless the server already has one configured via `.env`, in which case this is optional. Get one free at [console.groq.com/keys](https://console.groq.com/keys).
2. **Connect a database** — either drag a `.db` file into the drop zone, or switch to "Connect URL" and paste a PostgreSQL/MySQL connection string.
3. **Explore your schema** — tables and columns appear in the collapsible sidebar tree.
4. **Type a question** in plain English in the query box.
5. **Press Run** (or `Ctrl+Enter` / `Cmd+Enter`).

DataForge will show the generated SQL, execute it, and display the results table. If the query fails, the auto-debug log will show each retry attempt and the corrected SQL. If the generated SQL modifies data, you'll be asked to confirm before it runs (see [Security & Safety Guardrails](#security--safety-guardrails)).

### Connecting to PostgreSQL / MySQL

Switch to the **Connect URL** tab in the Database section and paste a SQLAlchemy-style connection string:

```
postgresql://user:password@host:5432/dbname
mysql+pymysql://user:password@host:3306/dbname
```

The connection string is sent to the local server to establish the connection and is not persisted to disk — the same trust model as the API key field. Don't point this at a production database you don't want an LLM writing to; see Known Limitations.

### Uploading a CSV or Excel file instead of a database

No `.db` file handy? Drop a `.csv` or `.xlsx` into the same upload zone. DataForge converts it into a fresh SQLite database behind the scenes: a CSV becomes one table (named after the file), and each sheet in an Excel workbook becomes its own table. Column names are automatically sanitized into valid SQL identifiers. From there it behaves exactly like any other connected database.

### Plain-English insights

Once a query succeeds, click **Summarize** on the Results card for a short plain-English takeaway of what the data shows (trends, standouts, totals) — useful for handing results to someone who doesn't want to read a table. Click **Explain SQL** on the Generated SQL card at any time (even for a blocked or pending-confirmation query) to have the statement translated back into plain English, so a non-technical reviewer can sanity-check what will actually run before it does.

### Data governance: column masking

Columns named things like `salary`, `ssn`, `password`, or `credit_card` are redacted (`•••• (masked)`) in results by default — this happens server-side, so the real values never reach the browser unless requested. Check **Reveal sensitive columns for this query** above the query box to see real values for that one query, or click **Manage masked columns** to edit the list of column names treated as sensitive. Masking is name-based, not content-based — it won't catch a column called `pay_amount` unless you add that name to the list.

### Data cleaning

Click **Clean Data** in the sidebar (appears once a database is connected) to dedupe rows, trim whitespace, and convert blank strings to NULL across every table. A report card shows rows before/after, duplicates removed, and cells trimmed per table. Works identically across SQLite, Postgres, and MySQL.

### Visualizations

After running a query that returns at least one numeric column, click **Visualize** on the Results card to render a chart from the returned rows. Switch between Bar, Line, and Pie using the dropdown — no re-query needed, it's rendered from the data already on screen.

### Query history

Every query you run is logged in the **History** panel in the sidebar (persisted in your browser via `localStorage`), with a colored dot showing whether it succeeded, failed, was blocked, or needed confirmation. Click any entry to reload it into the query box. Click **Clear** to wipe the log.

### Exporting results

On any successful result set, click **Export CSV** (generated instantly in the browser) or **Export Excel** (built server-side with pandas) to download the current table.

### Example queries

```
Show me all employees in the Engineering department
What are the top 3 most expensive products?
Count the total revenue per customer, sorted highest first
How many orders were completed vs pending vs cancelled?
Which employees earn more than the average salary?
Count rows in each table
```

### Sample queries file

The repo includes `queries.sql` with 5 pre-written queries ranging from easy to advanced, complete with expected output comments. Open any of them in the query box to test the pipeline end to end.

---

## Security & Safety Guardrails

DataForge classifies every LLM-generated statement before it runs (`classify_sql` in `app.py`):

- **Blocked outright** — `DROP`, `ALTER`, `TRUNCATE`, `ATTACH`, `DETACH`, `VACUUM`, `REINDEX`, `GRANT`, `REVOKE`, `PRAGMA`. These never execute, regardless of confirmation.
- **Requires confirmation** — `INSERT`, `UPDATE`, `DELETE`, `REPLACE`, `CREATE`, `MERGE`. The generated SQL is shown to you with a "Run Anyway" / "Cancel" choice before it touches your data.
- **Runs immediately** — everything else (reads).

This is a keyword-based classifier, not a full SQL parser — string and identifier literals are stripped before scanning to avoid false positives (e.g. a column value containing the word "dropped" won't trigger a block), and the whole statement is scanned so semicolon-separated multi-statement injection attempts are caught too. It's a solid defense-in-depth layer, not a substitute for good judgment: still point this at databases you're comfortable letting an LLM query, and use a read-only database role/credential wherever possible for anything resembling production data.

Column-level masking is a separate, complementary control (see [Usage](#data-governance-column-masking)): sensitive columns are redacted server-side by default, and only revealed when a user explicitly checks a box for that one query — never inferred from the wording of the question.

Basic rate limiting (Flask-Limiter) caps `/query`, `/connect`, `/summarize`, and `/explain` at 10-20 requests per minute per IP, with a 120/minute default elsewhere, so one user or script can't monopolize the Groq API or hammer a connected database. It uses in-memory counters, which is fine for a single-process deployment — under gunicorn with multiple workers, each worker tracks its own count (so the *effective* limit scales with worker count); put a shared backend like Redis in front of it for a real multi-worker production limit.

Other things worth knowing before a corporate/production deployment:

- **No authentication** — DataForge has no login system or session isolation. It's designed for local or trusted-network use. Put it behind your own auth layer (SSO proxy, VPN, etc.) before exposing it more broadly.
- **Credentials round-trip through the browser** — the database connection string and Groq API key are sent from the browser to the local server on each request (not persisted server-side beyond the request). This matches how the app has always handled the API key; treat it accordingly, and prefer environment-configured credentials (`GROQ_API_KEY` in `.env`) over user-entered ones where you control the deployment.

---

## Deployment

### Docker

```bash
docker build -t dataforge .
docker run -p 5000:5000 --env-file .env dataforge
```

The image runs via gunicorn (4 workers) rather than the Flask development server. Configure `GROQ_API_KEY`, `PORT`, and `FLASK_DEBUG` through `.env` or `-e` flags — see `.env.example`.

### Bare-metal / VM production

```bash
pip install -r requirements.txt
export FLASK_DEBUG=false
gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 120 app:app
```

Never run `python app.py` (the Flask dev server, with its interactive debugger) in production — always use gunicorn or an equivalent WSGI server, with `FLASK_DEBUG=false`.

---

## Testing & CI

```bash
pip install -r requirements-dev.txt
pytest -v
```

The suite (`tests/`) covers the guardrail classifier (including string-literal false positives and multi-statement injection attempts), the SQLAlchemy database layer (schema introspection, execution, cleaning — including a regression test for a real bug where SQLAlchemy's bind-parameter parsing misreads literal colons in time strings), and every route (upload for `.db`/`.csv`/`.xlsx`, connect, the full query/guardrail/debug-loop lifecycle, clean, export, masking, rate limiting, and the insight endpoints) — all against real SQLite databases and the real Flask app, with only the Groq calls mocked out so it runs offline. `.github/workflows/tests.yml` runs it on every push and PR to `main` across Python 3.10, 3.11, and 3.12.

---

## Project Structure

```
DataForge/
├── app.py                  # Flask backend — SQLAlchemy data layer, SQL generation,
│                            #   guardrail classification, masking, rate limiting,
│                            #   debug loop, cleaning, export, insights
├── setup_database.py       # One-time script to create the sample SQLite database
├── database.db             # Sample SQLite database (6 tables, generated by setup_database.py)
├── queries.sql              # 5 sample queries (easy → advanced)
├── english_to_sql.ipynb    # Notebook version of the core pipeline, for exploration
├── requirements.txt        # Python dependencies
├── requirements-dev.txt    # requirements.txt + pytest, for running the test suite
├── pytest.ini
├── tests/
│   ├── conftest.py          # Shared fixtures (test client, disposable sample DB, mocked LLM)
│   ├── test_guardrails.py   # classify_sql / guardrail_gate
│   ├── test_database.py     # schema introspection, execute_sql, clean_database
│   ├── test_routes.py       # every Flask route, including the guardrail lifecycle
│   └── test_masking_and_limits.py
├── .github/
│   └── workflows/
│       └── tests.yml        # Runs pytest on push/PR across Python 3.10-3.12
├── templates/
│   └── index.html          # Single-page frontend UI (SQL runner, cleaning, charts,
│                            #   history, export, connection UI, masking controls)
├── Dockerfile               # Production container image (gunicorn entrypoint)
├── .dockerignore
├── .env.example             # Template for GROQ_API_KEY / PORT / FLASK_DEBUG
├── HOW_TO_RUN.txt          # Quick-start cheat sheet
├── .gitignore
├── LICENSE
└── README.md
```

---

## Troubleshooting

### `429 — insufficient_quota` on startup
Your Groq account has hit its rate limit. Wait a few minutes, or check [console.groq.com](https://console.groq.com) for usage. Groq's free tier resets daily.

### "No database connected" error
Make sure you've either uploaded a valid `.db` file or successfully connected via a URL (check for a green "Connected" badge in the sidebar). A `.db` file corrupted by an interrupted write will be rejected — try regenerating with `python setup_database.py`.

### "Could not connect" when using a Postgres/MySQL URL
Double-check the connection string format (`postgresql://user:pass@host:5432/db` or `mysql+pymysql://user:pass@host:3306/db`), that the database is reachable from wherever DataForge is running, and that the corresponding driver is installed (`psycopg2-binary` / `pymysql` — both are in `requirements.txt` by default).

### A query I expected to run instead asked for confirmation, or was blocked
That's the safety guardrail working as intended — see [Security & Safety Guardrails](#security--safety-guardrails). If it was blocked outright, rephrase your question as a read query; DataForge does not execute schema-altering statements under any circumstances.

### Query returns wrong results or an unrelated table
This is usually caused by an ambiguous question. Be more specific about table names — e.g. instead of *"show sales"*, say *"show all rows in the orders table where status is completed"*.

### The app fails to start (`ModuleNotFoundError`)
Run `pip install -r requirements.txt` again. If you have multiple Python environments, make sure you're using the same one for both install and run.

### Port 5000 already in use
Set `PORT` in `.env`, or override directly:
```bash
PORT=5001 python app.py
```

---

## Known Limitations

- **No authentication** — The app has no login system or session isolation. Do not expose it to the public internet without adding your own auth layer.
- **Single database per session** — Only one database can be connected at a time. Re-upload or reconnect to switch.
- **Guardrails are best-effort, not a full SQL parser** — The keyword-based classifier catches the common cases (including multi-statement injection attempts) but is not a formal grammar-level parser. Use a read-only database credential for anything you can't afford to have written to.
- **Column masking is name-based, not content-based** — it redacts columns whose *name* matches the configured list (`salary`, `ssn`, etc.); it does not scan cell values for things that look sensitive. Add any additional column names your schema uses (e.g. `pay_amount`, `national_id`) via "Manage masked columns."
- **Masked-column list and rate limits are process-wide and in-memory** — they reset on restart and aren't scoped per-user; fine for a single local/demo deployment, not a substitute for real multi-tenant settings storage.
- **Credentials round-trip through the browser** — database connection strings and API keys are sent from browser to server per-request rather than stored server-side; see [Security & Safety Guardrails](#security--safety-guardrails).

---

## Roadmap

**Shipped**
- [x] Automated data cleaning (dedupe, trim, blank → NULL)
- [x] On-demand chart visualizations
- [x] Code-enforced safety guardrails (block/confirm classification)
- [x] Query history panel with re-run, plus CSV / Excel export
- [x] Production deployment support (Dockerfile, `.env` config, gunicorn)
- [x] PostgreSQL and MySQL support via connection string
- [x] CSV / Excel upload (auto-converted to SQLite)
- [x] Plain-English result summaries and SQL explanations
- [x] pytest suite + GitHub Actions CI
- [x] Column-level data masking + basic rate limiting

**Under consideration**
- [ ] Multi-user authentication layer
- [ ] Support for additional LLM providers (Anthropic Claude, Google Gemini)
- [ ] Server-persisted query history and masking settings (currently browser-local / in-memory)
- [ ] Shared rate-limit backend (Redis) for true multi-worker production limits

---

## License

This project is licensed under the [MIT License](LICENSE).

```
MIT License

Copyright (c) 2026 Rhea Gupta

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
```

---

## Author

**Rhea Gupta**
rheagupta993@gmail.com

---

*Built with Python, Flask, Groq, SQLAlchemy, and a lot of SQL.*
