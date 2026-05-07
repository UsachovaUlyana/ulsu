-- ============================================================
-- SETUP: Создание таблиц и тестовых данных
-- Используется PostgreSQL (запущен через Docker)
-- Выполнила: Усачева Ульяна, К0709-23/3
-- ============================================================

-- Удаляем таблицы, если существуют
DROP TABLE IF EXISTS accounts;
DROP TABLE IF EXISTS products;

-- ============================================================
-- Таблица accounts — банковские счета
-- Используется для: dirty read, non-repeatable read, lost update
-- ============================================================
CREATE TABLE accounts (
    id          SERIAL PRIMARY KEY,
    owner       VARCHAR(100) NOT NULL,
    balance     NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    currency    VARCHAR(3) NOT NULL DEFAULT 'RUB',
    created_at  TIMESTAMP DEFAULT NOW()
);

INSERT INTO accounts (owner, balance, currency) VALUES
    ('Иванов Алексей',    50000.00, 'RUB'),
    ('Петрова Мария',    120000.00, 'RUB'),
    ('Сидоров Дмитрий',   75000.00, 'RUB'),
    ('Козлова Анна',      30000.00, 'RUB'),
    ('Новиков Сергей',   200000.00, 'RUB'),
    ('Морозова Елена',    95000.00, 'RUB'),
    ('Волков Андрей',     15000.00, 'RUB'),
    ('Соколова Ольга',    60000.00, 'RUB');

-- ============================================================
-- Таблица products — интернет-магазин
-- Используется для: phantom read
-- ============================================================
CREATE TABLE products (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    category    VARCHAR(100) NOT NULL,
    price       NUMERIC(10, 2) NOT NULL,
    in_stock    BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT NOW()
);

INSERT INTO products (name, category, price, in_stock) VALUES
    ('MacBook Pro 14"',       'Ноутбуки',       189990.00, TRUE),
    ('ASUS ROG Strix',        'Ноутбуки',       145000.00, TRUE),
    ('Lenovo ThinkPad X1',    'Ноутбуки',       112000.00, TRUE),
    ('iPhone 16 Pro',         'Смартфоны',       129990.00, TRUE),
    ('Samsung Galaxy S25',    'Смартфоны',        89990.00, TRUE),
    ('Xiaomi 15 Ultra',       'Смартфоны',        74990.00, TRUE),
    ('Sony WH-1000XM5',      'Наушники',         32990.00, TRUE),
    ('AirPods Pro 3',         'Наушники',         24990.00, TRUE),
    ('JBL Tune 770NC',       'Наушники',          7990.00, TRUE),
    ('Dell U2723QE',          'Мониторы',         49990.00, TRUE),
    ('LG 27GP950',            'Мониторы',         64990.00, TRUE),
    ('Logitech MX Master 3S', 'Аксессуары',       8490.00, TRUE),
    ('Keychron K8 Pro',       'Аксессуары',       12990.00, TRUE);

-- Проверяем созданные данные
SELECT '=== ACCOUNTS ===' AS info;
SELECT id, owner, balance, currency FROM accounts ORDER BY id;

SELECT '=== PRODUCTS ===' AS info;
SELECT id, name, category, price FROM products ORDER BY category, name;

SELECT '=== СТАТИСТИКА ===' AS info;
SELECT 'accounts' AS table_name, COUNT(*) AS rows FROM accounts
UNION ALL
SELECT 'products', COUNT(*) FROM products;
