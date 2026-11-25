import sqlite3
from datetime import datetime


def connect(database):
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(database):
    with connect(database) as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT,
                publisher TEXT,
                cover_url TEXT,
                local_cover TEXT,
                page_count INTEGER NOT NULL DEFAULT 0,
                isbn TEXT,
                publication_year TEXT,
                status TEXT NOT NULL DEFAULT 'okunacak',
                rating INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                finished_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reading_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                pages INTEGER NOT NULL,
                logged_at TEXT NOT NULL,
                FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )


def add_book(database, book):
    with connect(database) as con:
        cur = con.execute(
            """
            INSERT INTO books (
                title, author, publisher, cover_url, local_cover, page_count,
                isbn, publication_year, status, finished_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                book["title"], book["author"], book["publisher"], book["cover_url"],
                book["local_cover"], book["page_count"], book["isbn"],
                book["publication_year"], book["status"], book["finished_at"],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        return cur.lastrowid


def book_exists(database, isbn=None, title=None):
    with connect(database) as con:
        if isbn:
            row = con.execute("SELECT 1 FROM books WHERE isbn = ? AND isbn != ''", (isbn,)).fetchone()
            if row:
                return True
        if title:
            row = con.execute("SELECT 1 FROM books WHERE lower(trim(title)) = lower(trim(?))", (title,)).fetchone()
            return row is not None
    return False


def list_books(database, status):
    with connect(database) as con:
        books = con.execute(
            "SELECT * FROM books WHERE status = ? ORDER BY created_at DESC",
            (status,),
        ).fetchall()
        result = []
        for book in books:
            item = dict(book)
            latest = con.execute(
                "SELECT pages FROM reading_logs WHERE book_id = ? ORDER BY logged_at DESC, id DESC LIMIT 1",
                (book["id"],),
            ).fetchone()
            item["current_page"] = latest["pages"] if latest else 0
            item["logs"] = [dict(row) for row in con.execute(
                "SELECT * FROM reading_logs WHERE book_id = ? ORDER BY logged_at DESC, id DESC",
                (book["id"],),
            ).fetchall()]
            result.append(item)
        return result


def status_counts(database):
    with connect(database) as con:
        rows = con.execute(
            "SELECT status, COUNT(*) AS count FROM books GROUP BY status"
        ).fetchall()
    counts = {"okunacak": 0, "okunuyor": 0, "okundu": 0}
    for row in rows:
        counts[row["status"]] = row["count"]
    return counts


def get_book(database, book_id):
    with connect(database) as con:
        row = con.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        return dict(row) if row else None


def update_status(database, book_id, status, finished_at):
    with connect(database) as con:
        con.execute(
            "UPDATE books SET status = ?, finished_at = ? WHERE id = ?",
            (status, finished_at, book_id),
        )


def add_reading_log(database, book_id, pages, logged_at):
    with connect(database) as con:
        con.execute(
            "INSERT INTO reading_logs(book_id, pages, logged_at) VALUES (?, ?, ?)",
            (book_id, pages, logged_at),
        )


def latest_page(database, book_id):
    with connect(database) as con:
        row = con.execute(
            "SELECT pages FROM reading_logs WHERE book_id = ? ORDER BY logged_at DESC, id DESC LIMIT 1",
            (book_id,),
        ).fetchone()
        return row["pages"] if row else 0


def get_reading_log(database, log_id):
    with connect(database) as con:
        row = con.execute("SELECT * FROM reading_logs WHERE id = ?", (log_id,)).fetchone()
        return dict(row) if row else None


def delete_reading_log(database, log_id):
    with connect(database) as con:
        con.execute("DELETE FROM reading_logs WHERE id = ?", (log_id,))


def update_rating(database, book_id, rating, note):
    with connect(database) as con:
        con.execute(
            "UPDATE books SET rating = ?, note = ? WHERE id = ?",
            (rating, note, book_id),
        )


def set_setting(database, key, value):
    with connect(database) as con:
        con.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_setting(database, key, default):
    with connect(database) as con:
        row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def finished_count(database, year):
    with connect(database) as con:
        row = con.execute(
            "SELECT COUNT(*) AS count FROM books "
            "WHERE status = 'okundu' AND substr(finished_at, 1, 4) = ?",
            (str(year),),
        ).fetchone()
        return row["count"]


def monthly_pages(database, year):
    with connect(database) as con:
        rows = con.execute(
            "SELECT book_id, pages, logged_at FROM reading_logs "
            "WHERE substr(logged_at, 1, 4) = ? "
            "ORDER BY book_id, logged_at, id",
            (str(year),),
        ).fetchall()
    values = [0] * 12
    previous_by_book = {}
    for row in rows:
        month = int(row["logged_at"][5:7]) - 1
        current = row["pages"]
        previous = previous_by_book.get(row["book_id"], 0)
        values[month] += max(0, current - previous)
        previous_by_book[row["book_id"]] = current
    return values


def reading_streak(database):
    with connect(database) as con:
        rows = con.execute(
            "SELECT DISTINCT logged_at FROM reading_logs ORDER BY logged_at DESC"
        ).fetchall()
    if not rows:
        return 0
    streak = 0
    previous = None
    for row in rows:
        day = datetime.strptime(row["logged_at"], "%Y-%m-%d").date()
        if previous is None:
            previous = day
            streak = 1
        else:
            if (previous - day).days == 1:
                streak += 1
                previous = day
            elif (previous - day).days == 0:
                continue
            else:
                break
    return streak


def recent_reading_logs(database, book_id, days):
    with connect(database) as con:
        rows = con.execute(
            "SELECT * FROM reading_logs WHERE book_id = ? "
            "AND logged_at >= date('now', ?) "
            "ORDER BY logged_at ASC",
            (book_id, f"-{days} days"),
        ).fetchall()
    return [dict(row) for row in rows]


def estimate_finish_text(book, logs):
    if not logs:
        return "Son 7 gün için okuma kaydı yok."
    previous = 0
    total_read = 0
    for log in sorted(
        logs,
        key=lambda item: (
            item.get("logged_at", ""),
            item.get("id", 0),
        ),
    ):
        current = int(log["pages"])
        total_read += max(0, current - previous)
        previous = current
    daily = total_read / 7
    remaining = max(0, book["page_count"] - logs[-1]["pages"])
    if daily <= 0:
        return "Bu hızla bitirme tahmini yapılamıyor."
    days = max(1, int((remaining / daily) + 0.5))
    return f"Bu hızla {days} günde bitirirsin"
