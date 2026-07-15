# DataForge

> **Convert plain English into executable SQL — instantly.**

DataForge is an AI-powered web application that translates natural language queries into SQLite SQL, executes them against your own database, and autonomously debugs any errors — all from a clean, cinematic interface.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=flat-square&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0%2B-black?style=flat-square&logo=flask)
![Groq](https://img.shields.io/badge/Groq-LLaMA%203.3-orange?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Installation](#installation)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)
- [License](#license)
- [Author](#author)

---

## Features

- **Natural Language to SQL** — Ask questions in plain English; LLaMA 3.3 70B (via Groq) generates the correct SQLite query.
- **Bring Your Own Database** — Drag and drop any `.db` SQLite file. DataForge reads the schema automatically and adapts to your tables.
- **Autonomous Error Debugging** — If a query fails, the engine feeds the error back to the model and retries up to 3 times without any manual intervention.
- **Live Schema Explorer** — A collapsible sidebar shows every table, column, type, and primary key in your uploaded database.
- **Automated Data Cleaning** — Click "Clean Data" to dedupe rows, trim whitespace, and convert blank strings to NULL across every table, on demand. Table structure (columns, types, primary keys) is preserved; a before/after report shows exactly what changed.
- **On-Demand Visualizations** — Click "Visualize" on any result set with numeric data to render an interactive bar, line, or pie chart (Chart.js) directly from the query results — no extra queries, no server round-trip.
- **Cinematic Dark UI** — Built with Inter, Space Grotesk, and JetBrains Mono. SQL output includes full syntax highlighting. Results render in a clean, paginated table with a JSON output panel.

---

## Tech Stack

| Layer     | Technology                          |
|-----------|-------------------------------------|
| Backend   | Python 3.9+, Flask 3.0              |
| AI Model  | LLaMA 3.3 70B via Groq API          |
| Database  | SQLite (via Python `sqlite3`)        |
| Frontend  | Vanilla HTML, CSS, JavaScript        |
| Data Cleaning | pandas                           |
| Charts    | Chart.js (CDN, client-side)          |
| Fonts     | Inter · Space Grotesk · JetBrains Mono (Google Fonts) |

---

## Installation

### Prerequisites

- Python 3.9 or higher
- A free [Groq API key](https://console.groq.com/keys) — no credit card required

### Steps

**1. Clone the repository**

```bash
git clone https://github.com/your-username/dataforge.git
cd dataforge
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. (Optional) Generate the sample database**

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

**4. Start the server**

```bash
python app.py
```

**5. Open the app**

Navigate to [http://localhost:5000](http://localhost:5000) in your browser.

---

## Usage

### Step-by-step

1. **Enter your Groq API key** in the sidebar field (starts with `gsk_`). Get one free at [console.groq.com/keys](https://console.groq.com/keys).
2. **Upload a `.db` file** by dragging it into the drop zone or clicking to browse.
3. **Explore your schema** — tables and columns appear in the collapsible sidebar tree.
4. **Type a question** in plain English in the query box.
5. **Press Run** (or `Ctrl+Enter` / `Cmd+Enter`).

DataForge will show the generated SQL, execute it, and display the results table. If the query fails, the auto-debug log will show each retry attempt and the corrected SQL.

### Data cleaning

Click **Clean Data** in the sidebar (appears once a database is loaded) to dedupe rows, trim whitespace, and convert blank strings to NULL across every table. A report card shows rows before/after, duplicates removed, and cells trimmed per table.

### Visualizations

After running a query that returns at least one numeric column, click **Visualize** on the Results card to render a chart from the returned rows. Switch between Bar, Line, and Pie using the dropdown — no re-query needed, it's rendered from the data already on screen.

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

## Project Structure

```
dataforge/
├── app.py                  # Flask backend — routes, SQL generation, debug loop
├── setup_database.py       # One-time script to create sample SQLite database
├── queries.sql             # 5 sample queries (easy → advanced)
├── requirements.txt        # Python dependencies
├── templates/
│   └── index.html          # Single-page frontend UI
└── README.md
```

---

## Troubleshooting

### `429 — insufficient_quota` on startup
Your Groq account has hit its rate limit. Wait a few minutes, or check [console.groq.com](https://console.groq.com) for usage. Groq's free tier resets daily.

### "No database loaded" error after uploading
Make sure your file has a `.db` extension and is a valid SQLite database. Files corrupted by an interrupted write will be rejected. Try regenerating with `python setup_database.py`.

### Query returns wrong results or an unrelated table
This is usually caused by an ambiguous question. Be more specific about table names — e.g. instead of *"show sales"*, say *"show all rows in the orders table where status is completed"*.

### The app fails to start (`ModuleNotFoundError`)
Run `pip install -r requirements.txt` again. If you have multiple Python environments, make sure you're using the same one for both install and run.

### Port 5000 already in use
Change the port in `app.py`:
```python
app.run(debug=True, port=5001)
```

---

## Known Limitations

- **SQLite only** — DataForge currently supports SQLite `.db` files exclusively. Other database engines (PostgreSQL, MySQL) are not yet supported.
- **No authentication** — The app is designed for local, single-user use. There is no login system or session isolation. Do not expose it to the public internet without adding authentication.
- **Single database per session** — Only one database can be active at a time. Re-upload to switch databases.

---

## Roadmap

- [ ] PostgreSQL and MySQL support via connection string input
- [ ] Query history panel with re-run capability
- [ ] Export results to CSV / Excel
- [ ] Multi-user authentication layer
- [ ] Support for additional LLM providers (Anthropic Claude, Google Gemini)

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

*Built with Python, Flask, Groq, and a lot of SQL.*
