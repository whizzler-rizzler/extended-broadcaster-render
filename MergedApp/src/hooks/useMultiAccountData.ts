import { useState, useEffect, useRef, useCallback } from 'react';
import {
  SingleAccountData,
  MultiAccountState,
  AggregatedPortfolio,
  createEmptyAccount,
  computeAccountStats,
  aggregatePortfolio,
} from '@/types/multiAccount';
import { getApiUrl, getWsUrl } from '@/config/api';

const REST_POLL_INTERVAL = 250; // 4x per second
const WS_RECONNECT_DELAY = 3000;

interface UseMultiAccountDataReturn {
  accounts: Map<string, SingleAccountData>;
  activeAccounts: SingleAccountData[];
  portfolio: AggregatedPortfolio;
  isConnected: boolean;
  error: string | null;
  lastUpdate: Date;
  lastWsUpdate: Date;
  lastRestUpdate: Date;
  wsMessageCount: number;
  restRequestCount: number;
  restFetchDuration: number;
  forceReconnect: () => void;
}

export const useMultiAccountData = (): UseMultiAccountDataReturn => {
  const [state, setState] = useState<MultiAccountState>({
    accounts: new Map(),
    activeAccountIds: [],
    lastGlobalUpdate: new Date(),
    isConnected: false,
    error: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const restIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastUpdateTimeRef = useRef<number>(Date.now());
  
  // Separate tracking for WS and REST updates
  const [lastWsUpdate, setLastWsUpdate] = useState<Date>(new Date());
  const [lastRestUpdate, setLastRestUpdate] = useState<Date>(new Date());
  const [wsMessageCount, setWsMessageCount] = useState(0);
  const [restRequestCount, setRestRequestCount] = useState(0);
  const [restFetchDuration, setRestFetchDuration] = useState(0);

  // Process incoming account data and auto-detect new accounts
  const processAccountData = useCallback((accountId: string, data: any) => {
    setState(prev => {
      const accounts = new Map(prev.accounts);
      
      if (!accounts.has(accountId)) {
        console.log(`🆕 [MultiAccount] Auto-detected new account: ${accountId}`);
        accounts.set(accountId, createEmptyAccount(accountId, data.name || accountId));
      }

      const existing = accounts.get(accountId)!;
      
      // Extract data from API response format (could be {status, data: [...]} or raw array)
      const extractData = (value: any, fallback: any[] = []) => {
        if (Array.isArray(value)) return value;
        if (value?.data && Array.isArray(value.data)) return value.data;
        return fallback;
      };

      const updated: SingleAccountData = {
        ...existing,
        id: accountId,
        name: data.name || existing.name || accountId,
        isActive: true,
        lastUpdate: new Date(),
        balance: data.balance?.data || data.balance || existing.balance,
        positions: extractData(data.positions, existing.positions),
        orders: extractData(data.orders, existing.orders),
        trades: extractData(data.trades, existing.trades),
        computed: existing.computed,
      };

      updated.computed = computeAccountStats(updated);
      accounts.set(accountId, updated);

      const activeAccountIds = Array.from(accounts.keys()).filter(
        id => accounts.get(id)?.isActive
      );

      lastUpdateTimeRef.current = Date.now();
      return {
        ...prev,
        accounts,
        activeAccountIds,
        lastGlobalUpdate: new Date(),
      };
    });
  }, []);

  const knownAccountCountRef = useRef(0);

  // Process multi-account snapshot from broadcaster
  const processMultiAccountSnapshot = useCallback((data: any) => {
    if (data.accounts && typeof data.accounts === 'object') {
      const incomingCount = Object.keys(data.accounts).length;
      
      if (knownAccountCountRef.current > 0 && incomingCount < knownAccountCountRef.current) {
        console.warn(`⚠️ [MultiAccount] Ignoring degraded snapshot: got ${incomingCount} accounts, expected ${knownAccountCountRef.current}`);
        return;
      }
      
      if (incomingCount > knownAccountCountRef.current) {
        knownAccountCountRef.current = incomingCount;
      }
      
      console.log(`📊 [MultiAccount] Processing ${incomingCount} accounts`);
      Object.entries(data.accounts).forEach(([accountId, accountData]: [string, any]) => {
        processAccountData(accountId, {
          name: accountData.name || accountId,
          balance: accountData.balance?.data || accountData.balance,
          positions: accountData.positions?.data || accountData.positions || [],
          orders: accountData.orders?.data || accountData.orders || [],
          trades: accountData.trades?.data || accountData.trades || [],
        });
      });
    } 
    else {
      const accountId = data.account_id || 'account_1';
      const accountName = data.account_name || 'Main Account';
      processAccountData(accountId, {
        name: accountName,
        balance: data.balance?.data || data.balance,
        positions: data.positions?.data || data.positions || [],
        orders: data.orders?.data || data.orders || [],
        trades: data.trades?.data || data.trades || [],
      });
    }
  }, [processAccountData]);

  // WebSocket connection
  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const wsUrl = getWsUrl('/ws/broadcast');
    console.log('🔌 [MultiAccount] Connecting WebSocket:', wsUrl);

    try {
      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onopen = () => {
        console.log('✅ [MultiAccount] WebSocket connected');
        reconnectAttemptsRef.current = 0;
        setState(prev => ({ ...prev, isConnected: true, error: null }));
      };

      wsRef.current.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          
          // Track WS update timing
          setLastWsUpdate(new Date());
          setWsMessageCount(prev => prev + 1);
          
          if (message.type === 'snapshot') {
            // Full snapshot of all accounts
            processMultiAccountSnapshot(message);
          } else if (message.type === 'account_update') {
            const accountId = message.account_id || 'account_1';
            const updateData: any = {
              name: message.account_name,
              balance: message.balance,
              positions: message.positions,
            };
            if (message.orders) updateData.orders = message.orders;
            if (message.trades) updateData.trades = message.trades;
            processAccountData(accountId, updateData);
          } else if (message.type === 'trades_update') {
            const accountId = message.account_id || 'account_1';
            processAccountData(accountId, { trades: message.trades });
          } else if (message.type === 'orders_update') {
            const accountId = message.account_id || 'account_1';
            processAccountData(accountId, { orders: message.orders });
          } else if (message.type === 'balance' || message.type === 'positions' || message.type === 'orders') {
            // Legacy format
            const accountId = message.account_id || 'account_1';
            processAccountData(accountId, { [message.type]: message.data });
          }
        } catch (err) {
          console.error('❌ [MultiAccount] WebSocket parse error:', err);
        }
      };

      wsRef.current.onerror = (error) => {
        console.error('❌ [MultiAccount] WebSocket error:', error);
      };

      wsRef.current.onclose = () => {
        console.log('🔌 [MultiAccount] WebSocket disconnected');
        wsRef.current = null;

        // Always try to reconnect
        const delay = Math.min(WS_RECONNECT_DELAY * Math.pow(1.5, reconnectAttemptsRef.current), 30000);
        console.log(`⏳ [MultiAccount] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current + 1})`);
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectAttemptsRef.current++;
          connectWebSocket();
        }, delay);
      };
    } catch (err) {
      console.error('❌ [MultiAccount] WebSocket setup error:', err);
      setState(prev => ({ ...prev, error: 'Failed to setup WebSocket' }));
    }
  }, [processAccountData, processMultiAccountSnapshot]);

  // Force reconnect WebSocket
  const forceReconnect = useCallback(() => {
    console.log('🔄 [MultiAccount] Force reconnecting...');
    if (wsRef.current) {
      wsRef.current.close();
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    reconnectAttemptsRef.current = 0;
    setTimeout(connectWebSocket, 100);
  }, [connectWebSocket]);

  // REST API fallback - fetch from broadcaster
  const fetchRestData = useCallback(async () => {
    const fetchStartTime = Date.now();
    
    try {
      // Try multi-account endpoint first
      const multiResponse = await fetch(getApiUrl('/api/cached-accounts'));
      
      if (multiResponse.ok) {
        const data = await multiResponse.json();
        const fetchDuration = Date.now() - fetchStartTime;
        
        // Track REST timing AFTER successful response
        setLastRestUpdate(new Date());
        setRestRequestCount(prev => prev + 1);
        setRestFetchDuration(fetchDuration);
        
        console.log('📊 [MultiAccount] Got multi-account data:', Object.keys(data.accounts || data).length, 'accounts', `(${Date.now() - fetchStartTime}ms)`);
        processMultiAccountSnapshot(data);
        lastUpdateTimeRef.current = Date.now();
        setState(prev => ({ ...prev, isConnected: true, error: null }));
        return;
      }

      // Fallback to single account endpoint
      const singleResponse = await fetch(getApiUrl('/api/cached-account'));
      if (singleResponse.ok) {
        const data = await singleResponse.json();
        const fetchDuration = Date.now() - fetchStartTime;
        
        // Track REST timing AFTER successful response
        setLastRestUpdate(new Date());
        setRestRequestCount(prev => prev + 1);
        setRestFetchDuration(fetchDuration);
        
        console.log('📊 [MultiAccount] Got single account data from broadcaster', `(${Date.now() - fetchStartTime}ms)`);
        
        // Extract account ID from balance data if available
        const accountId = data.balance?.data?.accountId?.toString() || 'account_1';
        
        processAccountData(accountId, {
          name: `Account ${accountId}`,
          balance: data.balance?.data || data.balance,
          positions: data.positions?.data || data.positions || [],
          orders: data.orders?.data || data.orders || [],
          trades: data.trades?.data || data.trades || [],
        });
        
        lastUpdateTimeRef.current = Date.now();
        setState(prev => ({ ...prev, isConnected: true, error: null }));
      } else {
        console.warn('⚠️ [MultiAccount] Both endpoints failed');
      }
    } catch (err) {
      console.error('❌ [MultiAccount] REST fetch error:', err);
    }
  }, [processMultiAccountSnapshot, processAccountData]);

  // Initialize connections
  useEffect(() => {
    connectWebSocket();
    fetchRestData();
    restIntervalRef.current = setInterval(fetchRestData, REST_POLL_INTERVAL);

    // Heartbeat - check for stale data every 10 seconds
    const heartbeatInterval = setInterval(() => {
      const now = Date.now();
      const staleDuration = now - lastUpdateTimeRef.current;
      
      // If no update for 30 seconds, force reconnect WebSocket
      if (staleDuration > 30000 && wsRef.current?.readyState !== WebSocket.OPEN) {
        console.warn(`💓 [MultiAccount] Heartbeat: Data stale for ${Math.round(staleDuration/1000)}s - force reconnecting`);
        if (wsRef.current) {
          wsRef.current.close();
        }
        reconnectAttemptsRef.current = 0;
        connectWebSocket();
      }
    }, 10000);

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (restIntervalRef.current) {
        clearInterval(restIntervalRef.current);
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      clearInterval(heartbeatInterval);
    };
  }, [connectWebSocket, fetchRestData]);

  const HIDDEN_EXCHANGES = ['edgex_'];
  // Derive active accounts list (sorted: extended first by number, then reya by number)
  const activeAccounts = Array.from(state.accounts.values())
    .filter(a => a.isActive && !HIDDEN_EXCHANGES.some(prefix => a.id.startsWith(prefix)))
    .sort((a, b) => {
      const aIsReya = a.id.startsWith('reya_');
      const bIsReya = b.id.startsWith('reya_');
      if (aIsReya !== bIsReya) return aIsReya ? 1 : -1;
      const numA = parseInt(a.id.replace('account_', '').replace('reya_', '')) || 0;
      const numB = parseInt(b.id.replace('account_', '').replace('reya_', '')) || 0;
      return numA - numB;
    });
  
  // Compute aggregated portfolio (excluding hidden exchanges)
  const filteredAccountsMap = new Map(
    Array.from(state.accounts.entries()).filter(([id]) => !HIDDEN_EXCHANGES.some(prefix => id.startsWith(prefix)))
  );
  const portfolio = aggregatePortfolio(filteredAccountsMap);

  return {
    accounts: state.accounts,
    activeAccounts,
    portfolio,
    isConnected: state.isConnected,
    error: state.error,
    lastUpdate: state.lastGlobalUpdate,
    lastWsUpdate,
    lastRestUpdate,
    wsMessageCount,
    restRequestCount,
    restFetchDuration,
    forceReconnect,
  };
};
