"""
Run this script once to create database.db in the same folder.
    python setup_database.py
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")


def create():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.executescript("""
    -- ── Tables ──────────────────────────────────────────────────────────────

    CREATE TABLE IF NOT EXISTS departments (
        department_id   INTEGER PRIMARY KEY,
        name            TEXT    NOT NULL,
        budget          REAL
    );

    CREATE TABLE IF NOT EXISTS employees (
        employee_id     INTEGER PRIMARY KEY,
        name            TEXT    NOT NULL,
        email           TEXT    UNIQUE,
        department_id   INTEGER REFERENCES departments(department_id),
        salary          REAL,
        hire_date       TEXT,   -- YYYY-MM-DD
        role            TEXT
    );

    CREATE TABLE IF NOT EXISTS customers (
        customer_id     INTEGER PRIMARY KEY,
        name            TEXT    NOT NULL,
        email           TEXT    UNIQUE,
        city            TEXT,
        signup_date     TEXT    -- YYYY-MM-DD
    );

    CREATE TABLE IF NOT EXISTS products (
        product_id      INTEGER PRIMARY KEY,
        name            TEXT    NOT NULL,
        category        TEXT,
        price           REAL,
        stock           INTEGER
    );

    CREATE TABLE IF NOT EXISTS orders (
        order_id        INTEGER PRIMARY KEY,
        customer_id     INTEGER REFERENCES customers(customer_id),
        order_date      TEXT,   -- YYYY-MM-DD
        status          TEXT,   -- completed | pending | cancelled
        total           REAL
    );

    CREATE TABLE IF NOT EXISTS order_items (
        item_id         INTEGER PRIMARY KEY,
        order_id        INTEGER REFERENCES orders(order_id),
        product_id      INTEGER REFERENCES products(product_id),
        quantity        INTEGER,
        unit_price      REAL
    );
    """)

    # ── Seed data ──────────────────────────────────────────────────────────────

    cur.executemany("INSERT OR IGNORE INTO departments VALUES (?,?,?)", [
        (1, "Engineering", 500000),
        (2, "Sales",       300000),
        (3, "HR",          150000),
        (4, "Marketing",   200000),
    ])

    cur.executemany("INSERT OR IGNORE INTO employees VALUES (?,?,?,?,?,?,?)", [
        (1, "Alice Chen",  "alice@co.com",  1, 120000, "2021-03-15", "Senior Engineer"),
        (2, "Bob Smith",   "bob@co.com",    2,  85000, "2020-07-01", "Sales Rep"),
        (3, "Carol Davis", "carol@co.com",  1,  95000, "2022-01-10", "Engineer"),
        (4, "Dan Lee",     "dan@co.com",    3,  70000, "2019-05-20", "HR Manager"),
        (5, "Eva Kim",     "eva@co.com",    4,  80000, "2023-02-28", "Marketing Lead"),
        (6, "Frank Wu",    "frank@co.com",  2,  90000, "2021-11-03", "Sales Manager"),
        (7, "Grace Hall",  "grace@co.com",  1, 110000, "2020-09-14", "Lead Engineer"),
    ])

    cur.executemany("INSERT OR IGNORE INTO customers VALUES (?,?,?,?,?)", [
        (1, "John Doe",  "john@email.com", "New York", "2023-01-15"),
        (2, "Jane Roe",  "jane@email.com", "London",   "2022-08-20"),
        (3, "Mike Ray",  "mike@email.com", "Tokyo",    "2023-05-10"),
        (4, "Sara Ali",  "sara@email.com", "Paris",    "2021-12-01"),
        (5, "Tom Ng",    "tom@email.com",  "New York", "2024-01-03"),
    ])

    cur.executemany("INSERT OR IGNORE INTO products VALUES (?,?,?,?,?)", [
        (1, "Laptop Pro",     "Electronics", 1299.99, 50),
        (2, "Wireless Mouse", "Electronics",   29.99, 200),
        (3, "Standing Desk",  "Furniture",    599.99,  30),
        (4, "Notebook Set",   "Stationery",    12.99, 500),
        (5, "Coffee Maker",   "Appliances",    89.99,  75),
        (6, "Monitor 4K",     "Electronics",  449.99,  60),
    ])

    cur.executemany("INSERT OR IGNORE INTO orders VALUES (?,?,?,?,?)", [
        (1, 1, "2024-01-10", "completed", 1329.98),
        (2, 2, "2024-01-15", "completed",  599.99),
        (3, 3, "2024-02-01", "pending",    449.99),
        (4, 1, "2024-02-14", "completed",   89.99),
        (5, 4, "2024-03-01", "cancelled",   12.99),
        (6, 5, "2024-03-15", "completed", 1749.98),
    ])

    cur.executemany("INSERT OR IGNORE INTO order_items VALUES (?,?,?,?,?)", [
        (1, 1, 1, 1, 1299.99),
        (2, 1, 2, 1,   29.99),
        (3, 2, 3, 1,  599.99),
        (4, 3, 6, 1,  449.99),
        (5, 4, 5, 1,   89.99),
        (6, 5, 4, 1,   12.99),
        (7, 6, 1, 1, 1299.99),
        (8, 6, 3, 1,  449.99),
    ])

    conn.commit()
    conn.close()

    print(f"✅  database.db created at: {DB_PATH}")
    print()
    print("Schema:")
    conn2 = sqlite3.connect(DB_PATH)
    cur2  = conn2.cursor()
    cur2.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    for (t,) in cur2.fetchall():
        cur2.execute(f"SELECT COUNT(*) FROM {t}")
        n = cur2.fetchone()[0]
        cur2.execute(f"PRAGMA table_info({t})")
        cols = [r[1] for r in cur2.fetchall()]
        print(f"  {t:15s} ({n} rows)  columns: {', '.join(cols)}")
    conn2.close()


if __name__ == "__main__":
    create()
