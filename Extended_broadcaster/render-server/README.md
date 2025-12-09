# Crypto Data Relay Server for Render

## Deployment na Render.com

### Krok 1: Przygotowanie
1. Skopiuj folder `render-server` do osobnego repozytorium Git
2. Pushuj na GitHub/GitLab

### Krok 2: Deploy na Render
1. Zaloguj się na [Render.com](https://render.com)
2. Kliknij "New +" → "Web Service"
3. Połącz swoje repozytorium
4. Render automatycznie wykryje `render.yaml`

### Krok 3: Połączenie z klientem
Po deploymencie otrzymasz URL np: `https://your-app.onrender.com`

Połącz się z WebSocket:
```javascript
const ws = new WebSocket('wss://your-app.onrender.com');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data);
};
```

## Lokalne testowanie

```bash
cd render-server
npm install
npm start
```

Serwer uruchomi się na `http://localhost:3001`

WebSocket: `ws://localhost:3001`

## Health Check

```bash
curl http://localhost:3001/health
```

## Funkcjonalność

- Automatyczne łączenie z upstream WebSocket
- Reconnect po rozłączeniu (3s delay)
- Broadcasting do wszystkich połączonych klientów
- Health check endpoint dla Render
- Graceful shutdown
