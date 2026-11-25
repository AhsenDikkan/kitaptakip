import os
import tempfile

import pytest

from application import create_app
import db


@pytest.fixture
def app(tmp_path):
    database = tmp_path / "test.db"
    test_app = create_app({
        "TESTING": True,
        "DATABASE": str(database),
        "SECRET_KEY": "test-secret",
    })
    yield test_app


@pytest.fixture
def client(app):
    client = app.test_client()
    client.post("/login", data={"username": "test", "password": "123"})
    return client


def test_login_required(app):
    response = app.test_client().get("/")
    assert response.status_code == 302
    assert "/login" in response.location


def test_page_rules(client, app):
    db.add_book(app.config["DATABASE"], {
        "title": "Suç ve Ceza", "author": "Dostoyevski", "publisher": "",
        "cover_url": "", "local_cover": "", "page_count": 400,
        "isbn": "123", "publication_year": "2020", "status": "okunuyor",
        "finished_at": None,
    })
    book_id = db.connect(app.config["DATABASE"]).execute("SELECT id FROM books").fetchone()["id"]

    too_small = client.post(f"/kitap/{book_id}/okuma", data={"pages": "50"}, follow_redirects=True)
    client.post(f"/kitap/{book_id}/okuma", data={"pages": "100"})
    too_small_again = client.post(f"/kitap/{book_id}/okuma", data={"pages": "90"}, follow_redirects=True)
    assert b"Yeni kay" in too_small_again.data or b"okuma" in too_small_again.data
    assert db.latest_page(app.config["DATABASE"], book_id) == 100

    client.post(f"/kitap/{book_id}/okuma", data={"pages": "400"})
    book = db.get_book(app.config["DATABASE"], book_id)
    assert book["status"] == "okundu"
    assert book["finished_at"]


def test_duplicate_books(app, client):
    client.post("/kitap/elle-ekle", data={"title": "Aynı Kitap", "page_count": "200"})
    client.post("/kitap/elle-ekle", data={"title": "Aynı Kitap", "page_count": "300"}, follow_redirects=True)
    with db.connect(app.config["DATABASE"]) as con:
        assert con.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 1


def test_finish_estimate():
    book = {"page_count": 400}
    logs = [{"pages": 100}, {"pages": 200}, {"pages": 300}]
    text = db.estimate_finish_text(book, logs)
    assert "günde bitirirsin" in text


def test_yearly_goal(app, client):
    db.set_setting(app.config["DATABASE"], "yearly_goal", "24")
    response = client.post("/ayarlar", data={"yearly_goal": "30"}, follow_redirects=True)
    assert response.status_code == 200
    assert db.get_setting(app.config["DATABASE"], "yearly_goal", "24") == "30"
