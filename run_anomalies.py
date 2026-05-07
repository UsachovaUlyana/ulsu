"""
Автоматическая демонстрация аномалий изоляции SQL.
Использует PostgreSQL + psycopg2 с параллельными потоками.

Выполнила: Усачева Ульяна, К0709-23/3

Для запуска:
  1. Запустить PostgreSQL через Docker:
     docker run --name pg-anomalies -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:16

  2. Установить зависимости:
     pip install psycopg2-binary

  3. Запустить:
     python run_anomalies.py
"""

import os
import sys
import time
import threading
from datetime import datetime

try:
    import psycopg2
    from psycopg2.extensions import (
        ISOLATION_LEVEL_READ_COMMITTED,
        ISOLATION_LEVEL_REPEATABLE_READ,
        ISOLATION_LEVEL_SERIALIZABLE,
    )
except ImportError:
    print("ERROR: psycopg2 не установлен. Выполните: pip install psycopg2-binary")
    sys.exit(1)


# ──────────────────────────────────────────────
# Параметры подключения
# ──────────────────────────────────────────────
DB_PARAMS = {
    "host":     os.getenv("PGHOST", "localhost"),
    "port":     int(os.getenv("PGPORT", "5432")),
    "dbname":   os.getenv("PGDATABASE", "postgres"),
    "user":     os.getenv("PGUSER", "postgres"),
    "password": os.getenv("PGPASSWORD", "postgres"),
}

LOG_LINES = []  # Сохраняем лог для отчёта


def get_conn(autocommit=False):
    """Создаёт новое подключение к БД."""
    conn = psycopg2.connect(**DB_PARAMS)
    conn.autocommit = autocommit
    return conn


def log(tag, msg):
    """Логирование с метками времени и тегом."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"  [{ts}] {tag:22s} | {msg}"
    print(line)
    LOG_LINES.append(line)


def separator(title):
    """Визуальный разделитель в логе."""
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)
    LOG_LINES.append("")
    LOG_LINES.append("=" * 72)
    LOG_LINES.append(f"  {title}")
    LOG_LINES.append("=" * 72)


# ──────────────────────────────────────────────
# Подготовка БД
# ──────────────────────────────────────────────
def setup_database():
    """Создаёт таблицы и заполняет тестовыми данными."""
    conn = get_conn(autocommit=True)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS accounts CASCADE;")
    cur.execute("DROP TABLE IF EXISTS products CASCADE;")

    cur.execute("""
        CREATE TABLE accounts (
            id         SERIAL PRIMARY KEY,
            owner      VARCHAR(100) NOT NULL,
            balance    NUMERIC(12,2) NOT NULL DEFAULT 0.00,
            currency   VARCHAR(3) NOT NULL DEFAULT 'RUB',
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    cur.execute("""
        INSERT INTO accounts (owner, balance, currency) VALUES
            ('Иванов Алексей',    50000.00, 'RUB'),
            ('Петрова Мария',    120000.00, 'RUB'),
            ('Сидоров Дмитрий',   75000.00, 'RUB'),
            ('Козлова Анна',      30000.00, 'RUB'),
            ('Новиков Сергей',   200000.00, 'RUB'),
            ('Морозова Елена',    95000.00, 'RUB'),
            ('Волков Андрей',     15000.00, 'RUB'),
            ('Соколова Ольга',    60000.00, 'RUB');
    """)

    cur.execute("""
        CREATE TABLE products (
            id         SERIAL PRIMARY KEY,
            name       VARCHAR(200) NOT NULL,
            category   VARCHAR(100) NOT NULL,
            price      NUMERIC(10,2) NOT NULL,
            in_stock   BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    cur.execute("""
        INSERT INTO products (name, category, price, in_stock) VALUES
            ('MacBook Pro 14"',       'Ноутбуки',    189990.00, TRUE),
            ('ASUS ROG Strix',        'Ноутбуки',    145000.00, TRUE),
            ('Lenovo ThinkPad X1',    'Ноутбуки',    112000.00, TRUE),
            ('iPhone 16 Pro',         'Смартфоны',    129990.00, TRUE),
            ('Samsung Galaxy S25',    'Смартфоны',     89990.00, TRUE),
            ('Xiaomi 15 Ultra',       'Смартфоны',     74990.00, TRUE),
            ('Sony WH-1000XM5',      'Наушники',      32990.00, TRUE),
            ('AirPods Pro 3',         'Наушники',      24990.00, TRUE),
            ('JBL Tune 770NC',       'Наушники',       7990.00, TRUE),
            ('Dell U2723QE',          'Мониторы',      49990.00, TRUE),
            ('LG 27GP950',            'Мониторы',      64990.00, TRUE),
            ('Logitech MX Master 3S', 'Аксессуары',    8490.00, TRUE),
            ('Keychron K8 Pro',       'Аксессуары',   12990.00, TRUE);
    """)

    cur.close()
    conn.close()
    log("SETUP", "✓ База данных подготовлена (8 accounts, 13 products)")


def show_table(table, where=""):
    """Выводит текущее состояние таблицы."""
    conn = get_conn(autocommit=True)
    cur = conn.cursor()
    q = f"SELECT * FROM {table}"
    if where:
        q += f" WHERE {where}"
    q += " ORDER BY id"
    cur.execute(q)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]

    header = f"  {'  '.join(f'{c:>15s}' for c in cols)}"
    divider = f"  {'-' * len(header)}"
    lines = [f"\n  ┌─ Таблица {table}" + (f" (WHERE {where})" if where else "") + " ─┐"]
    lines.append(header)
    lines.append(divider)
    for row in rows:
        lines.append(f"  {'  '.join(f'{str(v):>15s}' for v in row)}")
    lines.append("")

    for line in lines:
        print(line)
        LOG_LINES.append(line)

    cur.close()
    conn.close()


def reset_account(owner, balance):
    """Сброс баланса к начальному значению."""
    conn = get_conn(autocommit=True)
    cur = conn.cursor()
    cur.execute("UPDATE accounts SET balance = %s WHERE owner = %s", (balance, owner))
    cur.close()
    conn.close()


# ════════════════════════════════════════════════
# 1. DIRTY READ
# ════════════════════════════════════════════════
def demo_dirty_read():
    separator("АНОМАЛИЯ 1: DIRTY READ (Грязное чтение)")
    print("""
  Описание: Транзакция B читает данные, изменённые транзакцией A,
  которая ещё НЕ выполнила COMMIT. Если A откатится — B получила
  «грязные» (несуществующие) данные.

  Уровень изоляции: READ UNCOMMITTED
  ПРИМЕЧАНИЕ: PostgreSQL защищает от dirty read даже при READ UNCOMMITTED.
""")

    OWNER = "Иванов Алексей"
    ORIGINAL = 50000.00
    DIRTY = 500000.00

    reset_account(OWNER, ORIGINAL)

    barrier = threading.Barrier(2)
    results = {}

    def txn_a():
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
        log("TXN_A", f"UPDATE balance {ORIGINAL} → {DIRTY} (без COMMIT)")
        cur.execute("UPDATE accounts SET balance = %s WHERE owner = %s", (DIRTY, OWNER))
        barrier.wait()
        time.sleep(1.5)
        log("TXN_A", "ROLLBACK — откатываем изменения")
        conn.rollback()
        conn.close()

    def txn_b():
        time.sleep(0.3)
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
        barrier.wait()
        time.sleep(0.3)
        cur.execute("SELECT balance FROM accounts WHERE owner = %s", (OWNER,))
        val = cur.fetchone()[0]
        log("TXN_B", f"SELECT balance → {val}")
        results["b_read"] = float(val)
        conn.commit()
        conn.close()

    t1 = threading.Thread(target=txn_a)
    t2 = threading.Thread(target=txn_b)
    t1.start(); t2.start()
    t1.join();  t2.join()

    show_table("accounts", f"owner = '{OWNER}'")

    if results["b_read"] == DIRTY:
        log("РЕЗУЛЬТАТ", f"⚠ Dirty read ПРОИЗОШЁЛ! B прочитала {DIRTY} (незафиксированные данные)")
    else:
        log("РЕЗУЛЬТАТ", f"✓ Dirty read НЕ произошёл. B прочитала {results['b_read']}")
        log("РЕЗУЛЬТАТ", "  PostgreSQL автоматически защищает от dirty read.")
        log("РЕЗУЛЬТАТ", "  Даже при READ UNCOMMITTED уровень повышается до READ COMMITTED.")
    print()


# ════════════════════════════════════════════════
# 2. NON-REPEATABLE READ
# ════════════════════════════════════════════════
def demo_non_repeatable_read():
    separator("АНОМАЛИЯ 2: NON-REPEATABLE READ (Неповторяемое чтение)")
    print("""
  Описание: Транзакция A читает строку, затем транзакция B изменяет
  и коммитит эту строку. Транзакция A читает повторно — значение
  изменилось внутри одной транзакции!

  Уровень изоляции: READ COMMITTED (по умолчанию в PostgreSQL)
""")

    OWNER = "Иванов Алексей"
    ORIGINAL = 50000.00
    NEW_VAL = 95000.00

    reset_account(OWNER, ORIGINAL)

    step1_done = threading.Event()
    step2_done = threading.Event()
    results = {}

    def txn_a():
        conn = get_conn()
        conn.set_isolation_level(ISOLATION_LEVEL_READ_COMMITTED)
        cur = conn.cursor()
        cur.execute("BEGIN")

        cur.execute("SELECT balance FROM accounts WHERE owner = %s", (OWNER,))
        val1 = cur.fetchone()[0]
        log("TXN_A", f"Первое чтение:  balance = {val1}")
        results["read_1"] = float(val1)
        step1_done.set()

        step2_done.wait()
        time.sleep(0.3)

        cur.execute("SELECT balance FROM accounts WHERE owner = %s", (OWNER,))
        val2 = cur.fetchone()[0]
        log("TXN_A", f"Второе чтение:  balance = {val2}")
        results["read_2"] = float(val2)

        conn.commit()
        conn.close()

    def txn_b():
        step1_done.wait()
        time.sleep(0.3)
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("BEGIN")
        log("TXN_B", f"UPDATE balance → {NEW_VAL}")
        cur.execute("UPDATE accounts SET balance = %s WHERE owner = %s", (NEW_VAL, OWNER))
        conn.commit()
        log("TXN_B", "COMMIT выполнен")
        conn.close()
        step2_done.set()

    t1 = threading.Thread(target=txn_a)
    t2 = threading.Thread(target=txn_b)
    t1.start(); t2.start()
    t1.join();  t2.join()

    show_table("accounts", f"owner = '{OWNER}'")

    if results["read_1"] != results["read_2"]:
        log("РЕЗУЛЬТАТ", "⚠ Non-repeatable read ПРОИЗОШЁЛ!")
        log("РЕЗУЛЬТАТ", f"  Первое чтение:  {results['read_1']}")
        log("РЕЗУЛЬТАТ", f"  Второе чтение:  {results['read_2']}")
        log("РЕЗУЛЬТАТ", "  Значения ОТЛИЧАЮТСЯ внутри одной транзакции!")
    else:
        log("РЕЗУЛЬТАТ", "✓ Non-repeatable read НЕ произошёл.")
    print()


# ════════════════════════════════════════════════
# 3. PHANTOM READ
# ════════════════════════════════════════════════
def demo_phantom_read():
    separator("АНОМАЛИЯ 3: PHANTOM READ (Фантомное чтение)")
    print("""
  Описание: Транзакция A выполняет SELECT с WHERE дважды. Между
  чтениями транзакция B вставляет новую строку, удовлетворяющую
  условию. Второй SELECT возвращает БОЛЬШЕ строк — «фантом».

  Уровень изоляции: READ COMMITTED
""")

    CATEGORY = "Смартфоны"
    PHANTOM_NAME = "Google Pixel 9 Pro"
    PHANTOM_PRICE = 84990.00

    # Сброс
    conn_setup = get_conn(autocommit=True)
    conn_setup.cursor().execute("DELETE FROM products WHERE name = %s", (PHANTOM_NAME,))
    conn_setup.close()

    step1_done = threading.Event()
    step2_done = threading.Event()
    results = {}

    def txn_a():
        conn = get_conn()
        conn.set_isolation_level(ISOLATION_LEVEL_READ_COMMITTED)
        cur = conn.cursor()
        cur.execute("BEGIN")

        cur.execute("SELECT COUNT(*) FROM products WHERE category = %s", (CATEGORY,))
        cnt1 = cur.fetchone()[0]
        cur.execute(
            "SELECT name, price FROM products WHERE category = %s ORDER BY price",
            (CATEGORY,),
        )
        rows1 = cur.fetchall()
        log("TXN_A", f"Первый SELECT: {cnt1} строк → {[r[0] for r in rows1]}")
        results["count_1"] = cnt1
        step1_done.set()

        step2_done.wait()
        time.sleep(0.3)

        cur.execute("SELECT COUNT(*) FROM products WHERE category = %s", (CATEGORY,))
        cnt2 = cur.fetchone()[0]
        cur.execute(
            "SELECT name, price FROM products WHERE category = %s ORDER BY price",
            (CATEGORY,),
        )
        rows2 = cur.fetchall()
        log("TXN_A", f"Второй SELECT: {cnt2} строк → {[r[0] for r in rows2]}")
        results["count_2"] = cnt2

        conn.commit()
        conn.close()

    def txn_b():
        step1_done.wait()
        time.sleep(0.3)
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("BEGIN")
        log("TXN_B", f"INSERT '{PHANTOM_NAME}' в {CATEGORY} ({PHANTOM_PRICE}₽)")
        cur.execute(
            "INSERT INTO products (name, category, price) VALUES (%s, %s, %s)",
            (PHANTOM_NAME, CATEGORY, PHANTOM_PRICE),
        )
        conn.commit()
        log("TXN_B", "COMMIT выполнен")
        conn.close()
        step2_done.set()

    t1 = threading.Thread(target=txn_a)
    t2 = threading.Thread(target=txn_b)
    t1.start(); t2.start()
    t1.join();  t2.join()

    show_table("products", f"category = '{CATEGORY}'")

    if results["count_1"] != results["count_2"]:
        log("РЕЗУЛЬТАТ", "⚠ Phantom read ПРОИЗОШЁЛ!")
        log("РЕЗУЛЬТАТ", f"  Первый SELECT:  {results['count_1']} строк")
        log("РЕЗУЛЬТАТ", f"  Второй SELECT:  {results['count_2']} строк")
        log("РЕЗУЛЬТАТ", f"  Строка '{PHANTOM_NAME}' — это фантом!")
    else:
        log("РЕЗУЛЬТАТ", "✓ Phantom read НЕ произошёл.")
    print()


# ════════════════════════════════════════════════
# 4. LOST UPDATE
# ════════════════════════════════════════════════
def demo_lost_update():
    separator("АНОМАЛИЯ 4: LOST UPDATE (Потерянное обновление)")
    print("""
  Описание: Два оператора одновременно пополняют счёт клиента.
  Оператор 1 добавляет +15000 (зарплата),
  Оператор 2 добавляет +30000 (перевод).
  Ожидаемый результат: 50000 + 15000 + 30000 = 95000

  Уровень изоляции: READ COMMITTED
""")

    OWNER = "Иванов Алексей"
    ORIGINAL = 50000.00
    ADD_A = 15000.00
    ADD_B = 30000.00

    reset_account(OWNER, ORIGINAL)

    step1_done = threading.Event()
    step2_done = threading.Event()
    results = {}

    def txn_a():
        conn = get_conn()
        conn.set_isolation_level(ISOLATION_LEVEL_READ_COMMITTED)
        cur = conn.cursor()
        cur.execute("BEGIN")

        cur.execute("SELECT balance FROM accounts WHERE owner = %s", (OWNER,))
        balance = float(cur.fetchone()[0])
        log("TXN_A (Оператор 1)", f"Читает balance = {balance}")
        results["a_read"] = balance
        step1_done.set()

        step2_done.wait()
        time.sleep(0.3)

        new_balance = balance + ADD_A
        log("TXN_A (Оператор 1)", f"UPDATE balance → {new_balance} (= {balance} + {ADD_A})")
        cur.execute("UPDATE accounts SET balance = %s WHERE owner = %s", (new_balance, OWNER))
        conn.commit()
        log("TXN_A (Оператор 1)", "COMMIT выполнен")
        results["a_write"] = new_balance
        conn.close()

    def txn_b():
        step1_done.wait()
        time.sleep(0.2)
        conn = get_conn()
        conn.set_isolation_level(ISOLATION_LEVEL_READ_COMMITTED)
        cur = conn.cursor()
        cur.execute("BEGIN")

        cur.execute("SELECT balance FROM accounts WHERE owner = %s", (OWNER,))
        balance = float(cur.fetchone()[0])
        log("TXN_B (Оператор 2)", f"Читает balance = {balance}")
        results["b_read"] = balance

        new_balance = balance + ADD_B
        log("TXN_B (Оператор 2)", f"UPDATE balance → {new_balance} (= {balance} + {ADD_B})")
        cur.execute("UPDATE accounts SET balance = %s WHERE owner = %s", (new_balance, OWNER))
        conn.commit()
        log("TXN_B (Оператор 2)", "COMMIT выполнен")
        results["b_write"] = new_balance
        conn.close()
        step2_done.set()

    t1 = threading.Thread(target=txn_a)
    t2 = threading.Thread(target=txn_b)
    t1.start(); t2.start()
    t1.join();  t2.join()

    # Проверяем итог
    conn = get_conn(autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT balance FROM accounts WHERE owner = %s", (OWNER,))
    final = float(cur.fetchone()[0])
    conn.close()

    show_table("accounts", f"owner = '{OWNER}'")

    expected = ORIGINAL + ADD_A + ADD_B
    log("РЕЗУЛЬТАТ", f"Ожидаемый баланс:    {expected}")
    log("РЕЗУЛЬТАТ", f"Фактический баланс:  {final}")
    if final != expected:
        lost = expected - final
        log("РЕЗУЛЬТАТ", f"⚠ Lost update ПРОИЗОШЁЛ! Потеряно: {lost}")
        log("РЕЗУЛЬТАТ", f"  Оператор 1: {ORIGINAL} + {ADD_A} = {ORIGINAL + ADD_A}")
        log("РЕЗУЛЬТАТ", f"  Оператор 2: {ORIGINAL} + {ADD_B} = {ORIGINAL + ADD_B}")
        log("РЕЗУЛЬТАТ", f"  COMMIT оператора 1 перезаписал результат оператора 2.")
    else:
        log("РЕЗУЛЬТАТ", "✓ Lost update НЕ произошёл.")
    print()


# ════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════
def main():
    print()
    print("╔══════════════════════════════════════════════════════════════════════════╗")
    print("║     ДЕМОНСТРАЦИЯ АНОМАЛИЙ ИЗОЛЯЦИИ ТРАНЗАКЦИЙ SQL                      ║")
    print("║     Выполнила: Усачева Ульяна, К0709-23/3                              ║")
    print("║     СУБД: PostgreSQL 16 (Docker)                                       ║")
    print(f"║     Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):60s}   ║")
    print("╚══════════════════════════════════════════════════════════════════════════╝")
    print()

    try:
        log("SETUP", "Подготовка базы данных...")
        setup_database()
    except Exception as e:
        print(f"\n  ❌ Ошибка подключения к PostgreSQL: {e}")
        print("  Убедитесь, что PostgreSQL запущен:")
        print("  docker run --name pg-anomalies -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:16")
        sys.exit(1)

    # Показываем начальное состояние таблиц
    separator("НАЧАЛЬНОЕ СОСТОЯНИЕ ТАБЛИЦ")
    show_table("accounts")
    show_table("products")

    # Запускаем демонстрации
    demo_dirty_read()
    demo_non_repeatable_read()
    demo_phantom_read()
    demo_lost_update()

    # Финальное состояние
    separator("ФИНАЛЬНОЕ СОСТОЯНИЕ ТАБЛИЦ")
    show_table("accounts")
    show_table("products")

    # Итоговая сводка
    separator("ИТОГОВАЯ СВОДКА")
    summary = """
  ┌──────────────────────┬──────────────────┬───────────────────────────────┐
  │ Аномалия             │ Воспроизведена?  │ Как избежать                  │
  ├──────────────────────┼──────────────────┼───────────────────────────────┤
  │ Dirty Read           │ Нет (PG защищён) │ READ COMMITTED и выше         │
  │ Non-Repeatable Read  │ Да ⚠             │ REPEATABLE READ               │
  │ Phantom Read         │ Да ⚠             │ SERIALIZABLE / REPEATABLE*    │
  │ Lost Update          │ Да ⚠             │ SELECT FOR UPDATE / атомарные │
  └──────────────────────┴──────────────────┴───────────────────────────────┘

  Уровни изоляции по стандарту SQL:
  ┌──────────────────────┬───────┬─────────────────┬─────────┬─────────────┐
  │ Уровень              │ Dirty │ Non-Repeatable  │ Phantom │ Lost Update │
  │                      │ Read  │ Read            │ Read    │             │
  ├──────────────────────┼───────┼─────────────────┼─────────┼─────────────┤
  │ READ UNCOMMITTED     │  Да   │      Да         │   Да    │     Да      │
  │ READ COMMITTED       │  Нет  │      Да         │   Да    │     Да      │
  │ REPEATABLE READ      │  Нет  │      Нет        │   Да*   │     Нет     │
  │ SERIALIZABLE         │  Нет  │      Нет        │   Нет   │     Нет     │
  └──────────────────────┴───────┴─────────────────┴─────────┴─────────────┘
  * В PostgreSQL REPEATABLE READ также предотвращает phantom read.
"""
    print(summary)
    for line in summary.strip().split("\n"):
        LOG_LINES.append(line)

    # Сохраняем лог в файл
    log_filename = f"anomalies_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(log_filename, "w", encoding="utf-8") as f:
        f.write("ДЕМОНСТРАЦИЯ АНОМАЛИЙ ИЗОЛЯЦИИ ТРАНЗАКЦИЙ SQL\n")
        f.write(f"Выполнила: Усачева Ульяна, К0709-23/3\n")
        f.write(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"СУБД: PostgreSQL 16 (Docker)\n")
        f.write("=" * 72 + "\n\n")
        for line in LOG_LINES:
            f.write(line + "\n")

    print(f"\n  ✓ Лог сохранён в файл: {log_filename}")
    print("  ✓ Демонстрация завершена.\n")


if __name__ == "__main__":
    main()
