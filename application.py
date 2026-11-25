import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

import db
from scraper import SiteUnavailable, download_cover, search_books

ISTANBUL = ZoneInfo("Europe/Istanbul")


def create_app(test_config=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "gelistirme-icin-degistirilmis")
    app.config["DATABASE"] = os.getenv("KITAP_DB", "data/kitap.db")

    if test_config:
        app.config.update(test_config)

    os.makedirs(os.path.dirname(app.config["DATABASE"]) or ".", exist_ok=True)
    os.makedirs(os.path.join(app.static_folder, "kapaklar"), exist_ok=True)
    db.init_db(app.config["DATABASE"])

    @app.before_request
    def require_login():
        if request.endpoint not in ("login", "static"):
            if not session.get("logged_in"):
                return redirect(url_for("login"))

    def today_text():
        return datetime.now(ISTANBUL).strftime("%Y-%m-%d")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            if request.form.get("username") == "test" and request.form.get("password") == "123":
                session.clear()
                session["logged_in"] = True
                return redirect(url_for("library"))
            flash("Kullanıcı adı veya şifre hatalı.", "danger")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    def library():
        status = request.args.get("status", "okunuyor")
        if status not in ("okunacak", "okunuyor", "okundu"):
            status = "okunuyor"
        books = db.list_books(app.config["DATABASE"], status)
        counts = db.status_counts(app.config["DATABASE"])
        return render_template("library.html", books=books, status=status, counts=counts)

    @app.route("/arama", methods=["GET", "POST"])
    def search():
        results = []
        query = ""
        message = ""
        if request.method == "POST":
            query = request.form.get("q", "").strip()
            if query:
                try:
                    results = search_books(query)
                    if not results:
                        message = "Kitap bulunamadı, elle ekleyebilirsin"
                except SiteUnavailable:
                    message = "Şu an kitap aranamıyor, elle ekleyebilirsin"
            else:
                message = "Aramak için kitap adı, yazar veya ISBN gir."
        return render_template("search.html", results=results, query=query, message=message)

    @app.route("/kitap/ekle-arama", methods=["POST"])
    def add_from_search():
        if db.book_exists(app.config["DATABASE"], isbn=request.form.get("isbn"), title=request.form.get("title")):
            flash("Bu kitap zaten kitaplığında.", "warning")
            return redirect(url_for("library"))

        cover_local = download_cover(request.form.get("cover_url"), app.static_folder)
        status = request.form.get("status", "okunacak")
        if status not in ("okunacak", "okunuyor", "okundu"):
            status = "okunacak"
        page_count = int(request.form.get("page_count") or 0)
        if page_count < 0:
            page_count = 0

        book_id = db.add_book(app.config["DATABASE"], {
            "title": request.form.get("title", "").strip(),
            "author": request.form.get("author", "").strip(),
            "publisher": request.form.get("publisher", "").strip(),
            "cover_url": request.form.get("cover_url", "").strip(),
            "local_cover": cover_local,
            "page_count": page_count,
            "isbn": request.form.get("isbn", "").strip(),
            "publication_year": request.form.get("publication_year", "").strip(),
            "status": status,
            "finished_at": today_text() if status == "okundu" else None,
        })
        if status == "okunuyor":
            flash("Kitap Okunuyor rafına eklendi.", "success")
        elif status == "okundu":
            flash("Kitap Okundu rafına eklendi.", "success")
        else:
            flash("Kitap Okunacak rafına eklendi.", "success")
        return redirect(url_for("library", status=status))

    @app.route("/kitap/elle-ekle", methods=["POST"])
    def add_manual():
        title = request.form.get("title", "").strip()
        if not title:
            flash("Kitap adı zorunlu.", "danger")
            return redirect(request.referrer or url_for("search"))
        if db.book_exists(app.config["DATABASE"], title=title):
            flash("Bu kitap zaten kitaplığında.", "warning")
            return redirect(url_for("library"))

        try:
            page_count = int(request.form.get("page_count") or 0)
        except ValueError:
            page_count = 0
        if page_count < 0:
            page_count = 0

        status = request.form.get("status", "okunacak")
        if status not in ("okunacak", "okunuyor", "okundu"):
            status = "okunacak"
        db.add_book(app.config["DATABASE"], {
            "title": title,
            "author": request.form.get("author", "").strip(),
            "publisher": request.form.get("publisher", "").strip(),
            "cover_url": "",
            "local_cover": "",
            "page_count": page_count,
            "isbn": request.form.get("isbn", "").strip(),
            "publication_year": request.form.get("publication_year", "").strip(),
            "status": status,
            "finished_at": today_text() if status == "okundu" else None,
        })
        flash("Kitap elle eklendi.", "success")
        return redirect(url_for("library", status=status))

    @app.route("/kitap/<int:book_id>/durum", methods=["POST"])
    def change_status(book_id):
        status = request.form.get("status")
        if status not in ("okunacak", "okunuyor", "okundu"):
            flash("Geçersiz raf.", "danger")
            return redirect(url_for("library"))
        book = db.get_book(app.config["DATABASE"], book_id)
        if not book:
            flash("Kitap bulunamadı.", "danger")
            return redirect(url_for("library"))
        db.update_status(app.config["DATABASE"], book_id, status, today_text() if status == "okundu" else None)
        flash("Raf durumu güncellendi.", "success")
        return redirect(url_for("library", status=status))

    @app.route("/kitap/<int:book_id>/okuma", methods=["POST"])
    def add_reading_log(book_id):
        book = db.get_book(app.config["DATABASE"], book_id)
        if not book:
            flash("Kitap bulunamadı.", "danger")
            return redirect(url_for("library"))
        try:
            pages = int(request.form.get("pages", "0"))
        except ValueError:
            flash("Geçerli bir sayfa numarası gir.", "danger")
            return redirect(url_for("library", status=book["status"]))

        previous = db.latest_page(app.config["DATABASE"], book_id)
        if pages <= 0:
            flash("Sayfa sayısı 0'dan büyük olmalı.", "danger")
            return redirect(url_for("library", status=book["status"]))
        if book["page_count"] > 0 and pages > book["page_count"]:
            flash("Okunan sayfa toplam sayfadan fazla olamaz.", "danger")
            return redirect(url_for("library", status=book["status"]))
        if pages < previous:
            flash("Yeni kayıt önceki kayıttan küçük olamaz.", "danger")
            return redirect(url_for("library", status=book["status"]))

        db.add_reading_log(app.config["DATABASE"], book_id, pages, today_text())
        status = "okunuyor"
        finished_at = None
        if book["page_count"] > 0 and pages == book["page_count"]:
            status = "okundu"
            finished_at = today_text()
        db.update_status(app.config["DATABASE"], book_id, status, finished_at)
        flash("Okuma kaydı eklendi.", "success")
        return redirect(url_for("library", status=status))

    @app.route("/okuma/<int:log_id>/sil", methods=["POST"])
    def delete_reading_log(log_id):
        log = db.get_reading_log(app.config["DATABASE"], log_id)
        if log:
            db.delete_reading_log(app.config["DATABASE"], log_id)
            latest = db.latest_page(app.config["DATABASE"], log["book_id"])
            book = db.get_book(app.config["DATABASE"], log["book_id"])
            if book and book["status"] == "okundu" and latest < book["page_count"]:
                db.update_status(app.config["DATABASE"], book["id"], "okunuyor", None)
            flash("Son okuma kaydı silindi.", "success")
        return redirect(url_for("library", status=request.form.get("status", "okunuyor")))

    @app.route("/kitap/<int:book_id>/puan", methods=["POST"])
    def update_rating(book_id):
        try:
            rating = int(request.form.get("rating") or 0)
        except ValueError:
            rating = 0
        rating = min(5, max(0, rating))
        db.update_rating(app.config["DATABASE"], book_id, rating, request.form.get("note", "").strip())
        flash("Puan ve not kaydedildi.", "success")
        return redirect(url_for("library", status=request.form.get("status", "okundu")))

    @app.route("/ayarlar", methods=["GET", "POST"])
    def settings():
        if request.method == "POST":
            try:
                goal = int(request.form.get("yearly_goal", "24"))
            except ValueError:
                goal = 24
            goal = max(1, goal)
            db.set_setting(app.config["DATABASE"], "yearly_goal", str(goal))
            flash("Yıllık hedef güncellendi.", "success")
        goal = db.get_setting(app.config["DATABASE"], "yearly_goal", "24")
        return render_template("settings.html", yearly_goal=int(goal))

    @app.route("/istatistik")
    def statistics():
        year = datetime.now(ISTANBUL).year
        goal = int(db.get_setting(app.config["DATABASE"], "yearly_goal", "24"))
        finished = db.finished_count(app.config["DATABASE"], year)
        difference = finished - goal
        if difference >= 0:
            status_text = f"Bu yıl {finished}/{goal}, hedefi {difference} kitap geçtin"
        else:
            status_text = f"Bu yıl {finished}/{goal}, hedefin {abs(difference)} kitap gerisindesin"
        monthly = db.monthly_pages(app.config["DATABASE"], year)
        streak = db.reading_streak(app.config["DATABASE"])
        return render_template(
            "statistics.html",
            status_text=status_text,
            monthly=monthly,
            yearly_goal=goal,
            finished=finished,
            streak=streak,
        )

    @app.route("/kitap/<int:book_id>/tahmin")
    def estimate(book_id):
        book = db.get_book(app.config["DATABASE"], book_id)
        if not book or book["status"] != "okunuyor" or book["page_count"] <= 0:
            return jsonify({"text": "Tahmin için Okunuyor rafında ve toplam sayfa bilgisinde olan bir kitap gerekli."})
        logs = db.recent_reading_logs(app.config["DATABASE"], book_id, 7)
        text = db.estimate_finish_text(book, logs)
        return jsonify({"text": text})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5010)
