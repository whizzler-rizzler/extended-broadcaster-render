# Multi-Account Trading Dashboard

Multi-account trading dashboard (React + Python FastAPI) monitoring real-time accounts across multiple exchanges: Extended (36 accounts), Reya (8 accounts), EdgeX (4 accounts - hidden on frontend), Hibachi (2 accounts), GRVT (6 accounts), 01 Exchange (8 accounts), Pacifica (2 accounts), Nado (8 accounts), Hotstuff (8 accounts). Total: 82 accounts in API, 78 displayed on frontend (without EdgeX).

## Architecture

```
MergedApp/
  backend/
    main.py              - FastAPI application with REST endpoints, WebSocket server, local poller
    edgex_client.py      - EdgeX exchange client (4 accounts) with REST polling
    hibachi_client.py    - Hibachi exchange client (2 accounts) with REST polling
    grvt_client.py       - GRVT exchange client (6 accounts) with cookie-based auth and REST polling
    reya_client.py       - Reya exchange client (8 accounts) with REST polling
    zero_one_client.py   - 01 Exchange client (8 accounts) with public REST API polling
    pacifica_client.py   - Pacifica exchange client (2 accounts) with public REST API polling
    nado_client.py       - Nado exchange client (8 accounts) with public REST API polling
    hotstuff_client.py   - Hotstuff exchange client (8 accounts) with public REST API polling
  src/
    components/
      MultiAccountDashboard.tsx  - Main dashboard component
      AccountCardCompact.tsx     - Individual account card component
      FrequencyMonitor.tsx       - Broadcaster monitor with heartbeats
    hooks/
      useMultiAccountData.ts     - Data fetching hook with WebSocket support
    types/
      multiAccount.ts            - TypeScript type definitions
  vite.config.ts         - Vite config with API proxy to backend
  package.json           - Frontend dependencies
```

## Operating Mode

Backend runs in `FRONTEND_ONLY` mode:
- **Extended**: Proxied from remote backend (`REMOTE_API_BASE`)
- **Reya**: Polled locally (8 accounts)
- **EdgeX**: Polled locally (4 accounts) - hidden on frontend
- **Hibachi**: Polled locally (2 accounts)
- **GRVT**: Polled locally (6 accounts) with cookie-based authentication
- **01 Exchange**: Polled locally (8 accounts) via public REST API
- **Pacifica**: Polled locally (2 accounts) via public REST API
- **Nado**: Polled locally (8 accounts) via public REST API (uses same wallets as Reya)
- **Hotstuff**: Polled locally (8 accounts) via public REST API (uses same wallets as Reya)

## Exchange Integration Details

### 01 Exchange
- **API**: Public REST API at `https://zo-mainnet.n1.xyz` - NO authentication required for reads
- **Endpoints**: `GET /user/{pubkey}` (resolve account ID), `GET /account/{id}` (balances, positions, orders, margins), `GET /info` (market info)
- **Secrets**: `_01exchange_account_N` = Solana wallet pubkey (not Ethereum addresses)
- **Account resolution**: Wallet pubkey → account_id via `/user/{pubkey}` at startup
- **Data**: USDC balance, perp positions (BTC, ETH, SOL, HYPE, etc.), open orders, margin health
- **Frontend key**: `01_` prefix, exchange name `01exchange`, color `text-cyan-400`

### GRVT
- **Auth**: Cookie-based – POST to `edge.grvt.io/auth/api_key/login` with `{"api_key": "..."}` and `Cookie: rm=true;`
- **Response**: `Set-Cookie: gravity=...` + `x-grvt-account-id` header; session ~58 minutes
- **Endpoints**: `account_summary`, `positions`, `open_orders` – all POST to `trades.grvt.io/full/v1/`
- **Secrets**: `GRVT_N_api_key`, `GRVT_N_trading_account_ID`, `GRVT_N_Secret_Private_Key`, `GRVT_N_account_ID`
- **Geo-blocking**: API geo-blocked – requires proxy; proxy fallback tries `Rest_account_N_proxy` sequentially

### Hibachi
- `maintenanceMargin / balance` = margin ratio
- Leverage fallback from `total_notional / balance`
- Secrets: `Hibachi_N_AccountID` or `Hibachi_N_trading_Account_ID`, `Hibachi_N_api_key` or `Hibachi_N_priv_key`

### Reya
- Secrets: `Reya_N_wallet_main` or `Reya_N_wallet_adress`, `Reya_N_priv_key`

### EdgeX
- Hidden on frontend via `HIDDEN_EXCHANGES` in `useMultiAccountData.ts`, `FrequencyMonitor.tsx`, `MultiAccountDashboard.tsx`
- Secrets: `EdgeX_N_AccountID`, `EdgeX_N_priv_key`, `EdgeX_N_publicKeyYCoordinate`

### Pacifica
- **API**: Public REST API at `https://api.pacifica.fi/api/v1` - NO authentication required for reads
- **Endpoints**: `GET /account?account={pubkey}` (balance, equity, margin), `GET /positions?account={pubkey}`, `GET /orders?account={pubkey}`
- **Secrets**: `Pacifica_account_N_adress` = Solana wallet pubkey, `Pacifica_N_api_key` (optional, for rate limits only - currently NOT sent)
- **PNL calculation**: API doesn't provide mark price or unrealised PNL per position; PNL is computed as `account_equity - balance` from account endpoint and distributed across positions proportionally by notional
- **Frontend key**: `pacifica_` prefix, exchange name `pacifica`, color `text-teal-400`
- **Proxy**: Only uses dedicated `Pacifica_N_proxy` (no fallback to Rest_account proxy)

### Nado
- **API**: Public REST API at `https://gateway.prod.nado.xyz/v1` - NO authentication required for reads
- **Endpoints**: `POST /query` with `{"type": "subaccount_info", "subaccount": "0x{addr}{default_hex}"}` (balance, positions, orders, health), `{"type": "symbols"}` (market info)
- **Secrets**: Uses same wallets as Reya (`Reya_N_wallet_main`), no additional secrets needed
- **Subaccount format**: wallet address (20 bytes) + "default" padded to 12 bytes hex (`64656661756c740000000000`)
- **Data format**: All amounts in x18 (divide by 1e18). Product ID 0 = USDT0 (collateral). Perp positions have amount + v_quote_balance for PNL calc
- **Frontend key**: `nado_` prefix, exchange name `nado`, color `text-lime-400`
- **Proxy**: Uses `Nado_N_proxy` or falls back to `Rest_account_N_proxy`

### Hotstuff
- **API**: Public REST API at `https://api.hotstuff.trade/info` - NO authentication required
- **Request**: `POST` with `{"method": "accountSummary", "params": {"user": "0x..."}}`
- **Response**: `total_account_equity`, `margin_balance`, `upnl`, `collateral.USDC.balance`, `perp_positions`, `initial_margin_utilization`, `maintenance_margin_utilization`, `available_balance`, `vault_balances`
- **Secrets**: Uses same wallets as Reya (`Reya_N_wallet_main`), no additional secrets needed
- **Vault balances**: Vault amounts are included in equity calculation
- **Frontend key**: `hotstuff_` prefix, exchange name `hotstuff`, color `text-orange-400`
- **Proxy**: Uses `Hotstuff_N_proxy` or falls back to `Rest_account_N_proxy`

### Extended
- 36 accounts proxied from remote backend
- Secrets: `Extended_N_{CODE}_API_KEY`, etc.

## Points System

- **Extended**: Points fetched locally from Extended API every 10 minutes (`poll_all_accounts_points`). Displayed as yellow "Ext" label in dashboard header.
- **GRVT**: Points fetched locally via `fetch_grvt_points()` every 10 minutes (`poll_all_grvt_points`). Uses cookie auth (same as trading API). Tries `edge.grvt.io` first, then `trades.grvt.io` as fallback. Handles 401 with automatic re-auth retry. Note: Cloudflare may block edge.grvt.io (403) from server IPs. Displayed as purple "GRVT" label in dashboard header. Per-account points shown on GRVT account cards.
- **Other exchanges** (Hibachi, Reya, Pacifica, 01 Exchange): No points API available.
- **Endpoints**: `/api/points` (combined Extended + GRVT), `/api/points/refresh` (force refresh both), `/api/points/grvt` (GRVT only)
- **Frontend**: `useEarnedPoints.ts` hook fetches `/api/points` every 60s; returns `totalPoints` (Extended), `grvtTotalPoints`, per-account data for cards.

## Configuration

- `BROADCASTER_MODE` = `FRONTEND_ONLY`
- `REMOTE_API_BASE` = URL of remote backend for Extended
- Backend runs on port 8000, Frontend (Vite) on port 5000

## Workflows

- **MergedApp Backend**: `cd MergedApp/backend && uvicorn main:app --host 0.0.0.0 --port 8000`
- **MergedApp Frontend**: `cd MergedApp && npm run dev`
