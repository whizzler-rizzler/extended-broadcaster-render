import type { PortfolioData, WsHealthData } from './types';

const API_BASE = '';

export async function fetchPortfolio(): Promise<PortfolioData> {
  const res = await fetch(`${API_BASE}/api/portfolio`);
  if (!res.ok) throw new Error('Failed to fetch portfolio');
  return res.json();
}

export async function fetchWsHealth(): Promise<WsHealthData> {
  const res = await fetch(`${API_BASE}/api/ws/health`);
  if (!res.ok) throw new Error('Failed to fetch WS health');
  return res.json();
}

export async function reconnectWs(accountIndex?: number): Promise<{ success: boolean }> {
  const url = accountIndex !== undefined 
    ? `${API_BASE}/api/ws/reconnect?account_index=${accountIndex}`
    : `${API_BASE}/api/ws/reconnect`;
  const res = await fetch(url, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to reconnect');
  return res.json();
}
