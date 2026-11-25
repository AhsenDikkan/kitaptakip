# Kitap Takip

Okuma ilerlemesini, raflarını ve yıllık hedefini takip eden Flask uygulaması.

## Kurulum

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pytest
python application.py
```

Giriş bilgileri: `test` / `123`.

## Docker

```bash
docker compose up -d --build
```

Uygulama: http://localhost:5010