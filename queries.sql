-- ============================================================
--  Sample Queries for database.db
--  Difficulty: Easy → Advanced
--  Dialect: SQLite
-- ============================================================


-- ────────────────────────────────────────────────────────────
-- QUERY 1  ·  EASY
-- List all products with their category and price,
-- sorted cheapest first.
-- ────────────────────────────────────────────────────────────
SELECT
    name,
    category,
    price,
    stock
FROM products
ORDER BY price ASC;

/*  Expected output (6 rows):
    Notebook Set  | Stationery  |   12.99 | 500
    Wireless Mouse| Electronics |   29.99 | 200
    Coffee Maker  | Appliances  |   89.99 |  75
    Monitor 4K    | Electronics |  449.99 |  60
    Standing Desk | Furniture   |  599.99 |  30
    Laptop Pro    | Electronics | 1299.99 |  50
*/


-- ────────────────────────────────────────────────────────────
-- QUERY 2  ·  EASY-MEDIUM
-- Show all completed orders with the customer's name and city.
-- ────────────────────────────────────────────────────────────
SELECT
    o.order_id,
    c.name       AS customer_name,
    c.city,
    o.order_date,
    o.total
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.status = 'completed'
ORDER BY o.order_date;

/*  Expected output (4 rows):
    1 | John Doe | New York | 2024-01-10 | 1329.98
    2 | Jane Roe | London   | 2024-01-15 |  599.99
    4 | John Doe | New York | 2024-02-14 |   89.99
    6 | Tom Ng   | New York | 2024-03-15 | 1749.98
*/


-- ────────────────────────────────────────────────────────────
-- QUERY 3  ·  MEDIUM
-- For each department, show the number of employees,
-- the average salary, and the highest salary.
-- ────────────────────────────────────────────────────────────
SELECT
    d.name                          AS department,
    COUNT(e.employee_id)            AS headcount,
    ROUND(AVG(e.salary), 2)        AS avg_salary,
    MAX(e.salary)                   AS max_salary
FROM departments d
LEFT JOIN employees e ON e.department_id = d.department_id
GROUP BY d.department_id, d.name
ORDER BY avg_salary DESC;

/*  Expected output (4 rows):
    Engineering | 3 | 108333.33 | 120000
    Sales       | 2 |  87500.00 |  90000
    Marketing   | 1 |  80000.00 |  80000
    HR          | 1 |  70000.00 |  70000
*/


-- ────────────────────────────────────────────────────────────
-- QUERY 4  ·  MEDIUM-HARD
-- Find the total revenue generated per customer,
-- including only completed orders.
-- Show customers ranked by revenue, highest first.
-- ────────────────────────────────────────────────────────────
SELECT
    c.name                          AS customer_name,
    c.city,
    COUNT(o.order_id)               AS completed_orders,
    ROUND(SUM(o.total), 2)         AS total_revenue
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
WHERE o.status = 'completed'
GROUP BY c.customer_id, c.name, c.city
ORDER BY total_revenue DESC;

/*  Expected output (3 rows):
    Tom Ng   | New York | 1 | 1749.98
    John Doe | New York | 2 | 1419.97
    Jane Roe | London   | 1 |  599.99
*/


-- ────────────────────────────────────────────────────────────
-- QUERY 5  ·  ADVANCED
-- For each product, calculate:
--   • how many times it was ordered
--   • total units sold
--   • total revenue from that product
--   • % share of overall revenue
-- Only include products that have been ordered at least once.
-- Sort by revenue descending.
-- ────────────────────────────────────────────────────────────
WITH product_revenue AS (
    SELECT
        p.product_id,
        p.name                              AS product_name,
        p.category,
        COUNT(DISTINCT oi.order_id)         AS times_ordered,
        SUM(oi.quantity)                    AS units_sold,
        ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
    FROM products p
    JOIN order_items oi ON oi.product_id = p.product_id
    GROUP BY p.product_id, p.name, p.category
),
total AS (
    SELECT SUM(revenue) AS grand_total FROM product_revenue
)
SELECT
    pr.product_name,
    pr.category,
    pr.times_ordered,
    pr.units_sold,
    pr.revenue,
    ROUND(pr.revenue * 100.0 / t.grand_total, 1) AS revenue_pct
FROM product_revenue pr, total t
ORDER BY pr.revenue DESC;

/*  Expected output:
    Laptop Pro    | Electronics | 2 | 2 | 2599.98 | 57.5
    Standing Desk | Furniture   | 2 | 2 | 1049.98 | 23.2
    Monitor 4K    | Electronics | 1 | 1 |  449.99 |  9.9
    Coffee Maker  | Appliances  | 1 | 1 |   89.99 |  2.0
    Wireless Mouse| Electronics | 1 | 1 |   29.99 |  0.7
    Notebook Set  | Stationery  | 1 | 1 |   12.99 |  0.3
*/
