import os
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
import truststore

truststore.inject_into_ssl()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
TIMEOUT = 5
class SiteUnavailable(Exception):
    pass


def fetch(url):
    with requests.Session() as session:
        response = session.get(url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        return response


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def fetch_book_detail(url):
    response = fetch(url)
    soup = BeautifulSoup(response.text, "html.parser")
    page_count = 0
    isbn = ""
    publication_year = ""
    for item in soup.select(".ky-pd-attributes__item"):
        text = clean_text(item.get_text(" ", strip=True))
        if text.startswith("Sayfa Sayısı"):
            match = re.search(r"(\d+)", text)
            if match:
                page_count = int(match.group(1))
        elif text.startswith("ISBN"):
            match = re.search(r"([0-9Xx-]+)", text)
            if match:
                isbn = match.group(1)
        elif "Yayın Yılı" in text or "Basım Yılı" in text:
            match = re.search(r"(19|20)\d{2}", text)
            if match:
                publication_year = match.group()
    return {"page_count": page_count, "isbn": isbn, "publication_year": publication_year}


def search_books(query):
    url = "https://www.kitapyurdu.com/index.php?route=product/search&filter_name=" + quote(query)
    try:
        response = fetch(url)
    except requests.RequestException as exc:
        raise SiteUnavailable("Kitapyurdu şu an yanıt vermiyor.") from exc

    soup = BeautifulSoup(response.text, "html.parser")
    books = []
    for card in soup.select(".ky-product"):
        title_link = card.select_one("a.ky-product-title")
        if not title_link:
            continue
        title = clean_text(title_link.get_text(" ", strip=True))
        href = title_link.get("href", "")
        author_node = card.select_one(".ky-product-author a")
        publisher_node = card.select_one(".ky-product-publisher a")
        cover_node = card.select_one("a.ky-product-cover img")
        cover_url = ""
        if cover_node:
            cover_url = cover_node.get("data-src") or cover_node.get("src") or ""
        if cover_url.startswith("//"):
            cover_url = "https:" + cover_url
        book = {
            "title": title,
            "author": clean_text(author_node.get_text(" ", strip=True)) if author_node else "",
            "publisher": clean_text(publisher_node.get_text(" ", strip=True)) if publisher_node else "",
            "cover_url": cover_url,
            "link": href,
            "page_count": 0,
            "isbn": "",
            "publication_year": "",
        }
        if href:
            try:
                book.update(fetch_book_detail(href))
            except requests.RequestException:
                pass
        books.append(book)
    return books


def download_cover(url, static_folder):
    if not url:
        return ""
    try:
        response = fetch(url)
        if not response.headers.get("Content-Type", "").startswith("image/"):
            return ""
        cover_dir = os.path.join(static_folder, "kapaklar")
        os.makedirs(cover_dir, exist_ok=True)
        extension = ".jpg"
        content_type = response.headers.get("Content-Type", "")
        if "png" in content_type:
            extension = ".png"
        elif "webp" in content_type:
            extension = ".webp"
        name = re.sub(r"[^A-Za-z0-9_-]", "_", url)[-80:] + extension
        path = os.path.join(cover_dir, name)
        with open(path, "wb") as cover_file:
            cover_file.write(response.content)
        return f"kapaklar/{name}"
    except (requests.RequestException, OSError):
        return ""
