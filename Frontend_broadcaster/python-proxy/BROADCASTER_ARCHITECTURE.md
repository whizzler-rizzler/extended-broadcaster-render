# 🎯 Extended API Broadcaster - Architektura Systemu

## 📋 Spis Treści
1. [Przegląd Systemu](#przegląd-systemu)
2. [Problem Który Rozwiązujemy](#problem-który-rozwiązujemy)
3. [Architektura Broadcastera](#architektura-broadcastera)
4. [Komponenty Systemu](#komponenty-systemu)
5. [Przepływ Danych](#przepływ-danych)
6. [Implementacja Backend (Python Proxy)](#implementacja-backend-python-proxy)
7. [Implementacja Frontend (React Hooks)](#implementacja-frontend-react-hooks)
8. [Rate Limiting i Optymalizacja](#rate-limiting-i-optymalizacja)
9. [Monitoring i Debugging](#monitoring-i-debugging)
10. [Deployment](#deployment)

---

## 🎯 Przegląd Systemu

**Broadcaster** to system pośredniczący między Extended API a wieloma klientami frontendowymi, który:
- **Centralizuje** odpytywanie Extended API (tylko 4 req/s niezależnie od liczby klientów)
- **Broadcastuje** zmiany danych do wszystkich podłączonych klientów przez WebSocket
- **Cache'uje** dane w pamięci dla nieograniczonego dostępu przez REST API
- **Wykrywa różnice** (diff-based broadcasting) - wysyła tylko to co się zmieniło

---

## ⚠️ Problem Który Rozwiązujemy

### Przed Broadcasterem:
```
Frontend 1 → REST 4x/s → Python Proxy → Extended API (4 req/s)
Frontend 2 → REST 4x/s → Python Proxy → Extended API (4 req/s)  
Frontend 3 → REST 4x/s → Python Proxy → Extended API (4 req/s)
-----------------------------------------------------------
TOTAL: 12 requests/second do Extended API ❌
```

**Problemy:**
- Każdy frontend mnoży obciążenie Extended API
- Rate limity Extended API łatwo przekroczyć
- Koszty rosną liniowo z liczbą klientów
- Brak synchronizacji między klientami

### Po Broadcasterze:
```
Python Proxy Background Task → Extended API (4 req/s TOTAL)
                              ↓
                    [BROADCASTER CACHE]
                              ↓
              ┌───────────────┼───────────────┐
              ↓               ↓               ↓
        Frontend 1      Frontend 2      Frontend 3
     (WebSocket)     (WebSocket)     (WebSocket)
     
Backup REST: /api/cached-account (unlimited, from memory)
-----------------------------------------------------------
TOTAL: 4 requests/second do Extended API ✅
```

**Zalety:**
- **Stały rate limit**: 4 req/s niezależnie od liczby frontendów
- **Nieograniczony dostęp**: Frontend może pytać cache 100x/s przez REST
- **Real-time updates**: WebSocket wysyła tylko zmiany
- **Natychmiastowy snapshot**: Klient dostaje pełne dane przy połączeniu
- **Backup REST**: Jeśli WebSocket padnie, REST dalej działa

---

## 🏗️ Architektura Broadcastera

### Globalny Stan (Python Proxy)
```python
BROADCASTER_CACHE = {
    "positions": None,      # Lista aktywnych pozycji
    "balance": None,        # Stan konta (equity, margin ratio, etc.)
    "trades": None,         # Historia transakcji
    "last_update": {
        "positions": 0,     # Timestamp ostatniej aktualizacji
        "balance": 0,
        "trades": 0,
    }
}

BROADCAST_CLIENTS: Set[WebSocket] = set()  # Podłączeni klienci WebSocket
```

### Background Poller (4x/s + 1x/5s)
```python
async def background_poller():
    """
    Główna pętla pollująca Extended API:
    - Co 250ms (4x/s): positions + balance
    - Co 5000ms (1x/5s): trades
    """
    while True:
        # Fast polling
        await poll_fast_data()  # positions + balance
        
        # Slow polling (co 20 cykli = 5 sekund)
        if TRADES_POLL_COUNTER >= 20:
            await poll_trades()
            
        await asyncio.sleep(0.25)  # 250ms
```

### Diff-Based Broadcasting
```python
async def poll_fast_data():
    new_positions = await fetch_extended_api("/user/positions")
    new_balance = await fetch_extended_api("/user/balance")
    
    # Porównaj z cache - broadcast TYLKO jeśli się zmieniło
    if data_changed(CACHE["positions"], new_positions):
        CACHE["positions"] = new_positions
        await broadcast_to_clients({
            "type": "positions",
            "data": new_positions
        })
```

---

## 🧩 Komponenty Systemu

### Backend (Python Proxy)

#### 1. Background Poller
**Lokalizacja:** `python-proxy/main.py` - funkcja `background_poller()`

**Zadanie:**
- Odpytuje Extended API w tle (niezależnie od klientów)
- Aktualizuje `BROADCASTER_CACHE`
- Broadcastuje zmiany do wszystkich klientów

**Częstotliwość:**
```python
# Fast polling (4x/s)
poll_fast_data()  # /user/positions + /user/balance
await asyncio.sleep(0.25)

# Slow polling (1x/5s) 
if counter >= 20:
    poll_trades()  # /user/trades
```

#### 2. WebSocket `/ws/broadcast`
**Lokalizacja:** `python-proxy/main.py` - endpoint `websocket_broadcast()`

**Flow:**
```
1. Client connects
   ↓
2. Add to BROADCAST_CLIENTS set
   ↓
3. Send immediate SNAPSHOT (full data)
   ↓
4. Wait for broadcasts (diff updates only)
   ↓
5. Keep-alive ping every 30s
```

**Message Types:**
- `snapshot` - Pełne dane przy połączeniu
- `positions` - Aktualizacja pozycji (diff)
- `balance` - Aktualizacja balansu (diff)
- `trades` - Aktualizacja historii (diff)
- `ping` - Keep-alive

#### 3. REST `/api/cached-account`
**Lokalizacja:** `python-proxy/main.py` - endpoint `get_cached_account()`

**Zadanie:**
- Zwraca dane z `BROADCASTER_CACHE`
- Zero limitów (serwowane z pamięci)
- Backup dla WebSocket

**Response:**
```json
{
  "positions": [...],
  "balance": {...},
  "trades": [...],
  "cache_age_ms": {
    "positions": 123,
    "balance": 234,
    "trades": 5001
  }
}
```

#### 4. Monitoring `/api/broadcaster/stats`
**Lokalizacja:** `python-proxy/main.py` - endpoint `broadcaster_stats()`

**Informacje:**
```json
{
  "broadcaster": {
    "connected_clients": 3,
    "extended_api_rate": "4 req/s total"
  },
  "cache": {
    "positions_initialized": true,
    "balance_age_seconds": 2,
    "trades_age_seconds": 3
  }
}
```

---

### Frontend (React Hooks)

#### 1. `useExtendedWebSocket.ts`
**Zadanie:** Połączenie WebSocket do broadcastera

**Zmiany:**
```typescript
// Stary URL
const ws = new WebSocket('/ws/account');

// Nowy URL (broadcaster)
const ws = new WebSocket('/ws/broadcast');
```

**Message Handling:**
```typescript
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  // Snapshot - pełne dane przy połączeniu
  if (message.type === 'snapshot') {
    setExtendedData({
      balance: message.balance,
      positions: message.positions,
      trades: message.trades
    });
  }
  
  // Diff update - tylko zmiany
  if (message.type === 'balance') {
    setExtendedData(prev => ({
      ...prev,
      balance: message.data
    }));
  }
};
```

#### 2. `useAccountRestAPI.ts`
**Zadanie:** Pollowanie REST API dla danych konta

**Zmiany:**
```typescript
// Stary endpoint
const response = await fetch('/api/account');

// Nowy endpoint (cached)
const response = await fetch('/api/cached-account');
const data = await response.json();

// Dane już nie są w data.balance.data, tylko data.balance
setData({
  balance: data.balance,      // Bezpośrednio
  positions: data.positions,  // Bezpośrednio
});
```

**Częstotliwość:** Można ustawić nawet 100x/s - zero limitów Extended API

#### 3. `useTradeHistory.ts`
**Zadanie:** Pobieranie historii transakcji

**Zmiany:**
```typescript
// Stary endpoint
const response = await fetch('/api/trades');

// Nowy endpoint (cached)
const response = await fetch('/api/cached-account');
const data = await response.json();

// Wyciągamy tylko trades z cache
setData({
  trades: data.trades
});
```

#### 4. `useMarketDataSync.ts` - **USUNIĘTY**
**Powód:** Nie synchronizujemy już do Supabase, broadcaster cache jest jedynym źródłem prawdy

---

## 🔄 Przepływ Danych

### 1. Startup (Background Poller)
```
Python Proxy startuje
         ↓
@app.on_event("startup")
         ↓
asyncio.create_task(background_poller())
         ↓
Poller odpytuje Extended API co 250ms
         ↓
Zapisuje do BROADCASTER_CACHE
```

### 2. Klient Łączy się przez WebSocket
```
Frontend: new WebSocket('/ws/broadcast')
         ↓
Python: await websocket.accept()
         ↓
Python: BROADCAST_CLIENTS.add(websocket)
         ↓
Python: Wyślij SNAPSHOT (pełne dane)
         ↓
Frontend: Otrzymuje snapshot i renderuje UI
         ↓
Frontend: Czeka na diff updates
```

### 3. Zmiana Danych (Diff Broadcasting)
```
Background Poller: poll_fast_data()
         ↓
new_positions = fetch("/user/positions")
         ↓
data_changed(cache, new_positions)?
         ↓ (TAK)
CACHE["positions"] = new_positions
         ↓
broadcast_to_clients({
  "type": "positions",
  "data": new_positions
})
         ↓
Wszyscy klienci WebSocket otrzymują update
         ↓
Frontend: Aktualizuje tylko positions
```

### 4. REST Backup (Unlimited)
```
Frontend: fetch('/api/cached-account')
         ↓
Python: Zwraca BROADCASTER_CACHE
         ↓
Frontend: Otrzymuje dane z pamięci (instant)
```

---

## 🛠️ Implementacja Backend (Python Proxy)

### Struktura Pliku `main.py`

```
1. Imports & Setup
2. Global State (BROADCASTER_CACHE, BROADCAST_CLIENTS)
3. Utility Functions (data_changed, fetch_extended_api, broadcast_to_clients)
4. Background Poller (poll_fast_data, poll_trades, background_poller)
5. Startup Event (@app.on_event("startup"))
6. REST Endpoints (/health, /api/cached-account, /api/broadcaster/stats)
7. WebSocket Endpoint (/ws/broadcast)
8. Legacy Endpoints (backward compatibility)
```

### Kluczowe Funkcje

#### `data_changed(old, new)`
```python
def data_changed(old_data: Any, new_data: Any) -> bool:
    """
    Porównuje dwie struktury danych.
    Returns: True jeśli dane się różnią.
    """
    if old_data is None and new_data is not None:
        return True
    return json.dumps(old_data, sort_keys=True) != json.dumps(new_data, sort_keys=True)
```

**Dlaczego JSON dumps?**
- Porównuje głębokie struktury (nested dicts/lists)
- `sort_keys=True` zapewnia stabilność
- Szybkie (Python C extension)

#### `broadcast_to_clients(message)`
```python
async def broadcast_to_clients(message: Dict[str, Any]):
    """
    Wysyła wiadomość do wszystkich podłączonych klientów.
    Automatycznie usuwa disconnected clients.
    """
    disconnected = set()
    message_json = json.dumps(message)
    
    for client in BROADCAST_CLIENTS:
        try:
            await client.send_text(message_json)
        except Exception:
            disconnected.add(client)
    
    # Cleanup
    for client in disconnected:
        BROADCAST_CLIENTS.discard(client)
```

---

## 🎨 Implementacja Frontend (React Hooks)

### Hook Flow

```
Index.tsx (główny komponent)
    ↓
useExtendedWebSocket()  → WebSocket /ws/broadcast (real-time critical fields)
    ↓
useAccountRestAPI()     → REST /api/cached-account (polling 4x/s, unlimited)
    ↓
useTradeHistory()       → REST /api/cached-account (polling 1x/5s)
    ↓
usePublicPricesWebSocket() → Paradex prices (independent)
```

### useExtendedWebSocket - WebSocket Hook

**Zadania:**
1. Połączenie z `/ws/broadcast`
2. Odbiór snapshot przy połączeniu
3. Odbiór diff updates (tylko zmiany)
4. Reconnect z exponential backoff
5. Ekstrakcja tylko krytycznych pól z balance

**Krytyczne Pola Balance (4):**
```typescript
const criticalBalance = {
  marginRatio: bal.marginRatio,
  equity: bal.equity,
  availableForTrade: bal.availableForTrade,
  availableForWithdrawal: bal.availableForWithdrawal,
};
```

**Dlaczego tylko 4 pola?**
- Minimalizacja state updates (performance)
- Wykrywanie krytycznych zmian (margin call, liquidation)
- Pozostałe dane z REST API (szybsze, bardziej aktualne)

### useAccountRestAPI - REST Polling Hook

**Zadania:**
1. Pollowanie `/api/cached-account` co 250ms
2. Główne źródło danych dla UI
3. Backup dla WebSocket

**Rate Limiting:**
```typescript
// Można ustawić nawet 100x/s - zero limitów Extended API
const interval = setInterval(fetchAccountData, 250); // 4x/s default
```

**Response Handling:**
```typescript
const response = await fetch('/api/cached-account');
const data = await response.json();

// Cache age info dla debuggingu
console.log('Cache age:', data.cache_age_ms);

setData({
  balance: data.balance,      // Bezpośrednio z cache
  positions: data.positions,  // Bezpośrednio z cache
});
```

---

## ⚡ Rate Limiting i Optymalizacja

### Extended API Limits
```
PRZED: N frontendów × 4 req/s = 4N requests/s ❌
PO:    1 broadcaster × 4 req/s = 4 requests/s ✅
```

### Optymalizacje

#### 1. Diff-Based Broadcasting
```python
# TYLKO wysyła jeśli dane się zmieniły
if data_changed(cache, new_data):
    broadcast_to_clients(new_data)
```

**Redukcja ruchu:**
- Pozycje zmieniają się rzadko → mało broadcasts
- Balance zmienia się często → więcej broadcasts (ale tylko 4 pola)
- Trades zmieniają się bardzo rzadko (1x/5s) → prawie nigdy

#### 2. In-Memory Cache
```python
# Zero disk I/O
BROADCASTER_CACHE = {...}  # RAM tylko
```

**Zyski:**
- Instant response (sub-millisecond)
- Nieograniczona liczba requestów do cache
- Brak database bottlenecks

#### 3. WebSocket Keep-Alive
```python
# Ping co 30s żeby utrzymać połączenie
await asyncio.sleep(30)
await websocket.send_json({"type": "ping"})
```

**Dlaczego 30s?**
- Load balancery często mają 60s timeout
- 30s = bezpieczny margines
- Nie obciąża sieci (1 ping co 30s)

---

## 🔍 Monitoring i Debugging

### Endpoint: `/api/broadcaster/stats`

**Informacje:**
```json
{
  "broadcaster": {
    "connected_clients": 3,
    "extended_api_rate": "4 req/s total",
    "total_requests_to_extended": "4 req/s"
  },
  "cache": {
    "positions_initialized": true,
    "balance_initialized": true,
    "trades_initialized": true,
    "positions_age_seconds": 2,
    "balance_age_seconds": 1,
    "trades_age_seconds": 3
  },
  "last_poll": {
    "positions": 1234567890.123,
    "balance": 1234567890.456,
    "trades": 1234567890.789
  }
}
```

### Console Logs (Frontend)

**WebSocket:**
```
🔌 [WebSocket] Connection attempt #1
✅ [WebSocket] Connected (handshake OK)
📸 [Broadcaster] Received full snapshot
💰 [Broadcaster] Balance update (diff)
📊 [Broadcaster] Positions update (ignored - using REST)
```

**REST API:**
```
🔄 [Cached REST API] Fetched data (cache age: 123 ms)
✅ [useAccountRestAPI] Updated with cached data
📜 [useTradeHistory] Updated with 15 trades from cache
```

### Console Logs (Backend)

**Broadcaster:**
```
🚀 [Broadcaster] Background poller started
📊 [Broadcaster] Positions changed - broadcasting to 3 clients
💰 [Broadcaster] Balance changed - broadcasting to 3 clients
📜 [Broadcaster] Trades changed - broadcasting to 3 clients
```

**WebSocket:**
```
✅ [WS] New client connected (total: 3)
📸 [WS] Sent snapshot to client
👋 [WS] Client disconnected gracefully
🗑️ [WS] Client removed (remaining: 2)
```

---

## 🚀 Deployment

### Python Proxy (Render.com)

**Build Command:**
```bash
pip install -r requirements.txt
```

**Start Command:**
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

**Environment Variables:**
```
EXTENDED_API_KEY=your_api_key_here
EXTENDED_API_BASE_URL=https://api.starknet.extended.exchange/api/v1
```

**Health Check:**
```
GET /health
```

### Frontend (Lovable/Vercel)

**Environment Variables:**
```
VITE_PYTHON_PROXY_URL=https://extended-account-stream.onrender.com
```

**WebSocket URL:**
```typescript
const wsUrl = process.env.VITE_PYTHON_PROXY_URL
  .replace('https', 'wss')
  .replace('http', 'ws') + '/ws/broadcast';
```

---

## 📊 Performance Metrics

### Before Broadcaster
```
Extended API Requests:
  - 3 frontends × 4 req/s = 12 req/s

Network Usage:
  - High (every client polls independently)

Scalability:
  - Linear cost with clients (bad)

Sync Issues:
  - Clients see different data
```

### After Broadcaster
```
Extended API Requests:
  - 1 broadcaster × 4 req/s = 4 req/s

Network Usage:
  - Low (diff-based broadcasting)

Scalability:
  - Constant cost (amazing)

Sync Issues:
  - All clients see same data instantly
```

### Latency
```
REST /api/cached-account: <10ms (from RAM)
WebSocket broadcast: <50ms (diff update)
Extended API → Cache: ~250ms (polling interval)
```

---

## 🎓 Kluczowe Koncepty

### 1. Diff-Based Broadcasting
**Co to jest:**
- Wysyłanie tylko zmian, nie całego datasetu
- Porównywanie nowych danych ze starymi (cache)
- Broadcasting TYLKO gdy `data_changed() == True`

**Zalety:**
- 90% redukcja ruchu sieciowego
- Niższe obciążenie CPU (mniej renderów)
- Lepsza user experience (brak flashing)

### 2. Snapshot on Connect
**Co to jest:**
- Natychmiastowe wysłanie pełnych danych przy połączeniu WebSocket
- Klient nie musi czekać na pierwszy diff

**Implementacja:**
```python
await websocket.accept()
await websocket.send_json({
    "type": "snapshot",
    "positions": CACHE["positions"],
    "balance": CACHE["balance"],
    "trades": CACHE["trades"]
})
```

### 3. REST as Backup
**Co to jest:**
- WebSocket dla real-time updates
- REST dla fallback i unlimited access

**Use Cases:**
- WebSocket offline → REST dalej działa
- Bulk operations → REST jest szybszy
- Debugging → REST jest łatwiejszy do testowania

---

## 🔧 Troubleshooting

### Problem: WebSocket nie łączy się
**Debug:**
```typescript
console.log('WS URL:', wsUrl);
console.log('WS readyState:', ws.readyState);
```

**Check:**
- Czy URL jest poprawny (`wss://` dla HTTPS)
- Czy Python proxy działa (`/health`)
- Czy firewall blokuje WebSocket

### Problem: Dane nie aktualizują się
**Debug:**
```bash
curl https://proxy.com/api/broadcaster/stats
```

**Check:**
- Czy background poller działa (`"cache_age_seconds"`)
- Czy Extended API odpowiada (logs)
- Czy `data_changed()` działa poprawnie

### Problem: Wysokie opóźnienia
**Debug:**
```json
{
  "cache_age_ms": {"balance": 5000}  // 5 sekund opóźnienia!
}
```

**Check:**
- Czy poller działa (`asyncio.sleep(0.25)`)
- Czy Extended API jest wolny (network logs)
- Czy Python proxy ma dość RAM/CPU

---

## 📚 Dokumentacja API

### POST nie jest wspierany - tylko GET/WebSocket

### GET `/health`
**Response:**
```json
{
  "status": "ok",
  "service": "extended-broadcaster-proxy",
  "broadcaster": {
    "connected_clients": 3,
    "cache_initialized": true
  }
}
```

### GET `/api/cached-account`
**Response:**
```json
{
  "positions": [...],
  "balance": {...},
  "trades": [...],
  "cache_age_ms": {
    "positions": 123,
    "balance": 234,
    "trades": 5001
  }
}
```

**Rate Limit:** Unlimited (served from RAM)

### GET `/api/broadcaster/stats`
**Response:**
```json
{
  "broadcaster": {...},
  "cache": {...},
  "last_poll": {...}
}
```

### WebSocket `/ws/broadcast`

**Messages (Server → Client):**

**Snapshot (on connect):**
```json
{
  "type": "snapshot",
  "positions": [...],
  "balance": {...},
  "trades": [...],
  "timestamp": 1234567890.123
}
```

**Diff Update:**
```json
{
  "type": "balance",
  "data": {...},
  "timestamp": 1234567890.456
}
```

**Keep-Alive:**
```json
{
  "type": "ping",
  "timestamp": 1234567890.789
}
```

---

## 🎉 Podsumowanie

**Broadcaster to:**
- ✅ Centralizacja pollowania Extended API
- ✅ Diff-based broadcasting (tylko zmiany)
- ✅ In-memory cache (unlimited access)
- ✅ WebSocket dla real-time + REST dla backup
- ✅ Stały rate limit (4 req/s) niezależnie od klientów
- ✅ Monitoring i debugging built-in

**Kluczowe Metryki:**
- **4 req/s** do Extended API (zamiast 4N)
- **Unlimited** requests do cache
- **<10ms** latency dla REST
- **<50ms** latency dla WebSocket broadcasts

**Deployment:**
- Backend: Python Proxy na Render.com
- Frontend: React na Lovable/Vercel
- Communication: WebSocket (`/ws/broadcast`) + REST (`/api/cached-account`)

---

**Autor:** Extended Trading System  
**Wersja:** 2.0  
**Data:** 2025-11-23  
