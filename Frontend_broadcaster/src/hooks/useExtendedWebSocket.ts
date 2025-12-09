import { useEffect, useRef, useState } from 'react';

const PYTHON_PROXY_URL = import.meta.env.VITE_PYTHON_PROXY_URL || 'https://ws-trader-pulse.onrender.com';

// Convert HTTP URL to WebSocket URL for BROADCASTER
const getWebSocketUrl = (httpUrl: string): string => {
  return httpUrl.replace(/^https/, 'wss').replace(/^http/, 'ws') + '/ws/broadcast';
};

interface ExtendedMessage {
  type: 'snapshot' | 'positions' | 'balance' | 'trades' | 'orders' | 'ping';
  data?: any;
  positions?: any[];
  balance?: any;
  trades?: any[];
  orders?: any;
  timestamp?: number;
}

interface UseExtendedWebSocketReturn {
  isConnected: boolean;
  lastMessage: ExtendedMessage | null;
  error: string | null;
  extendedData: {
    balance?: any;
    positions?: any[];
    orders?: any[];
    lastUpdate: Record<string, string>;
  };
}

export type { UseExtendedWebSocketReturn };

export const useExtendedWebSocket = (): UseExtendedWebSocketReturn => {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<ExtendedMessage | null>(null);
  const [error, setError] = useState<string | null>(null);
  // WebSocket now only tracks critical balance fields for event detection
  const [extendedData, setExtendedData] = useState<{
    balance?: {
      marginRatio?: string;
      equity?: string;
      availableForTrade?: string;
      availableForWithdrawal?: string;
    };
    orders?: any[];
    lastUpdate: {
      balance?: string;
      orders?: string;
    };
  }>({
    lastUpdate: {},
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const maxReconnectAttempts = 50; // Keep trying for a while

  const connect = () => {
    try {
      // Clear any existing reconnect timeout
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }

      const wsUrl = getWebSocketUrl(PYTHON_PROXY_URL);
      console.log(`🔌 [WebSocket] Connection attempt #${reconnectAttemptsRef.current + 1}`);
      console.log('🔌 [WebSocket] Proxy URL:', PYTHON_PROXY_URL);
      console.log('🔌 [WebSocket] Full WS URL:', wsUrl);
      
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('✅ [WebSocket] Connected (handshake OK)');
        console.log('✅ [WebSocket] Connection state:', ws.readyState);
        console.log('✅ [WebSocket] URL:', ws.url);
        reconnectAttemptsRef.current = 0; // Reset counter on successful connection
        setError(null);
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          const now = new Date().toLocaleTimeString('en-US', { hour12: false });
          
          // Handle snapshot (full data on connect)
          if (message.type === 'snapshot') {
            console.log('📸 [Broadcaster] Received full snapshot');
            setIsConnected(true);
            setError(null);
            
            const updates: any = { lastUpdate: {} };
            
            // Extract critical balance fields from snapshot
            if (message.balance) {
              const bal = message.balance.balance ?? message.balance;
              const criticalBalance = {
                marginRatio: bal.marginRatio,
                equity: bal.equity,
                availableForTrade: bal.availableForTrade,
                availableForWithdrawal: bal.availableForWithdrawal,
              };
              
              updates.balance = criticalBalance;
              updates.lastUpdate.balance = now;
            }
            
            // Extract orders from snapshot
            if (message.orders) {
              const ordersData = message.orders.data ?? message.orders;
              updates.orders = ordersData;
              updates.lastUpdate.orders = now;
            }
            
            setExtendedData(updates);
            return;
          }

          // Handle ping (keep-alive)
          if (message.type === 'ping') {
            return; // Ignore pings
          }

          // Handle balance diff update
          if (message.type === 'balance' && message.data) {
            console.log('💰 [Broadcaster] Balance update (diff)');
            
            const bal = message.data.balance ?? message.data;
            const criticalBalance = {
              marginRatio: bal.marginRatio,
              equity: bal.equity,
              availableForTrade: bal.availableForTrade,
              availableForWithdrawal: bal.availableForWithdrawal,
            };

            setExtendedData(prev => ({
              ...prev,
              balance: criticalBalance,
              lastUpdate: {
                ...prev.lastUpdate,
                balance: now,
              }
            }));

            setLastMessage(message as ExtendedMessage);
          }

          // Handle positions diff update (we ignore these, using REST instead)
          if (message.type === 'positions') {
            console.log('📊 [Broadcaster] Positions update (ignored - using REST)');
          }

          // Handle trades diff update
          if (message.type === 'trades') {
            console.log('📜 [Broadcaster] Trades update (diff)');
            setLastMessage(message as ExtendedMessage);
          }

          // Handle orders diff update
          if (message.type === 'orders' && message.data) {
            console.log('📋 [Broadcaster] Orders update (diff)');
            
            const ordersData = message.data.data ?? message.data;
            
            setExtendedData(prev => ({
              ...prev,
              orders: ordersData,
              lastUpdate: {
                ...prev.lastUpdate,
                orders: now,
              }
            }));

            setLastMessage(message as ExtendedMessage);
          }

        } catch (err) {
          console.error('🔴 Error parsing WebSocket message:', err);
        }
      };

      ws.onerror = (event) => {
        console.error('🔴 [WebSocket] Error event');
        console.error('🔴 [WebSocket] Ready state:', ws.readyState);
        console.error('🔴 [WebSocket] URL:', ws.url);
        setError('WebSocket connection error');
      };

      ws.onclose = (event) => {
        console.log('🔌 [WebSocket] Connection closed');
        console.log('🔌 [WebSocket] Close code:', event.code);
        console.log('🔌 [WebSocket] Close reason:', event.reason);
        console.log('🔌 [WebSocket] Was clean:', event.wasClean);
        setIsConnected(false);
        
        // Reconnect with exponential backoff (max 30s)
        reconnectAttemptsRef.current++;
        if (reconnectAttemptsRef.current <= maxReconnectAttempts) {
          const delay = Math.min(1000 * Math.pow(1.5, reconnectAttemptsRef.current - 1), 30000);
          console.log(`🔌 [WebSocket] Reconnecting in ${(delay / 1000).toFixed(1)}s... (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})`);
          
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, delay);
        } else {
          console.error('🔴 [WebSocket] Max reconnection attempts reached');
          setError('Max reconnection attempts reached');
        }
      };
    } catch (err) {
      console.error('🔴 Error creating WebSocket:', err);
      setError(err instanceof Error ? err.message : 'Unknown error occurred');
      
      // Retry on error
      reconnectAttemptsRef.current++;
      if (reconnectAttemptsRef.current <= maxReconnectAttempts) {
        const delay = Math.min(1000 * Math.pow(1.5, reconnectAttemptsRef.current - 1), 30000);
        console.log(`🔌 [WebSocket] Retrying after error in ${(delay / 1000).toFixed(1)}s...`);
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      }
    }
  };

  useEffect(() => {
    console.log('🚀 [WebSocket] Initializing connection to Extended API via Python Proxy...');
    connect();

    return () => {
      console.log('🛑 [WebSocket] Cleaning up...');
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return { isConnected, lastMessage, error, extendedData };
};
