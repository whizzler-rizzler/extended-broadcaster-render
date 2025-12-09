# Extended API Proxy Service

Ten serwis działa jako pośrednik między aplikacją web a Extended API.

## Instalacja

1. Zainstaluj zależności:
```bash
pip install -r requirements.txt
```

2. Utwórz plik `.env` na podstawie `.env.example`:
```bash
cp .env.example .env
```

3. Dodaj swój API key do pliku `.env`:
```
EXTENDED_API_KEY=twoj_klucz_api
```

## Uruchomienie

### Lokalnie (development)
```bash
python main.py
```

Serwis będzie dostępny na: `http://localhost:8000`

### Produkcja (z uvicorn)
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Endpointy API

- `GET /health` - Health check
- `GET /api/account` - Kompletne dane konta (account info + positions + balance)
- `GET /api/account/info` - Informacje o koncie
- `GET /api/positions` - Aktualne pozycje
- `GET /api/balance` - Stan konta

## Testowanie

```bash
# Health check
curl http://localhost:8000/health

# Pobierz dane konta
curl http://localhost:8000/api/account
```

## Deployment

### Docker (opcjonalnie)
Możesz utworzyć `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Uruchom:
```bash
docker build -t extended-proxy .
docker run -p 8000:8000 --env-file .env extended-proxy
```

### Railway / Render / Heroku
1. Połącz repozytorium z platformą
2. Dodaj zmienne środowiskowe (EXTENDED_API_KEY)
3. Deploy automatycznie zbuduje i uruchomi serwis
