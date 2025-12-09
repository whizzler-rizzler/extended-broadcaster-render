import { useState, useEffect, useRef } from 'react';

export interface Trade {
  id: string;
  accountId: number;
  accountName: string;  // Added: which account this trade belongs to
  market: string;
  orderId: string;
  side: string;
  price: string;
  qty: string;
  value: string;
  fee: string;
  tradeType: string;
  createdTime: number;
  isTaker: boolean;
}

interface TradeHistoryData {
  trades: Trade[];
  lastUpdate: Date;
}

const API_URL = '/api/cached-accounts';
const POLL_INTERVAL = 5000; // 5 seconds

export const useTradeHistory = () => {
  const [data, setData] = useState<TradeHistoryData>({
    trades: [],
    lastUpdate: new Date(),
  });
  const intervalRef = useRef<NodeJS.Timeout>();

  const fetchTradeHistory = async () => {
    try {
      const response = await fetch(API_URL);
      const result = await response.json();
      
      console.log('📜 [useTradeHistory] Fetched all accounts:', result);
      
      // Aggregate trades from all accounts
      const allTrades: Trade[] = [];
      
      // Data is nested inside result.accounts
      const accountsData = result?.accounts || result;
      
      if (accountsData && typeof accountsData === 'object') {
        Object.entries(accountsData).forEach(([accountId, accountData]: [string, any]) => {
          // Extract account name from accountId (e.g., "Extended_1_aE42d3" -> "Extended 1")
          const accountNameMatch = accountId.match(/Extended_(\d+)/);
          const accountName = accountNameMatch ? `Extended ${accountNameMatch[1]}` : accountId;
          
          // Handle trades - can be array or {status, data} structure
          let trades: any[] = [];
          if (accountData?.trades) {
            if (Array.isArray(accountData.trades)) {
              trades = accountData.trades;
            } else if (accountData.trades.data && Array.isArray(accountData.trades.data)) {
              trades = accountData.trades.data;
            }
          }
          
          trades.forEach((t: any, index: number) => {
            // Generate truly unique ID: accountId + API id + orderId + timestamp + index
            const uniqueId = `${accountId}_${t.id || 'noid'}_${t.orderId || 'noorder'}_${t.createdTime || Date.now()}_${index}`;
            
            allTrades.push({
              id: uniqueId,
              accountId: parseInt(accountNameMatch?.[1] || '0'),
              accountName,
              market: t.market || t.symbol || 'UNKNOWN',
              orderId: t.orderId || '',
              side: t.side || 'UNKNOWN',
              price: String(t.price || '0'),
              qty: String(t.qty || t.size || '0'),
              value: String(t.value || (Number(t.price || 0) * Number(t.qty || t.size || 0))),
              fee: String(t.fee || '0'),
              tradeType: t.tradeType || t.type || 'UNKNOWN',
              createdTime: t.createdTime || t.timestamp || Date.now(),
              isTaker: t.isTaker ?? false,
            });
          });
        });
      }
      
      // Sort by time descending
      allTrades.sort((a, b) => b.createdTime - a.createdTime);
      
      setData({
        trades: allTrades.slice(0, 200), // Keep last 200 trades
        lastUpdate: new Date(),
      });
      
      console.log('✅ [useTradeHistory] Aggregated', allTrades.length, 'trades from all accounts');
    } catch (error) {
      console.error('❌ [useTradeHistory] Error fetching trade history:', error);
    }
  };

  useEffect(() => {
    fetchTradeHistory();
    intervalRef.current = setInterval(fetchTradeHistory, POLL_INTERVAL);
    
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, []);

  return data;
};
