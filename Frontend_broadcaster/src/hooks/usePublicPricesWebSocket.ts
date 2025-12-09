import { useEffect, useState, useRef } from 'react';

interface PriceData {
  symbol: string;
  exchange: string;
  price: string;
  priceChange?: string;
  fundingRate?: string;
  volume?: string;
  timestamp: number;
}

interface UsePublicPricesWebSocketReturn {
  prices: Map<string, PriceData>;
  isConnected: boolean;
  error: string | null;
}

export const usePublicPricesWebSocket = (): UsePublicPricesWebSocketReturn => {
  const [prices, setPrices] = useState<Map<string, PriceData>>(new Map());
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
  const reconnectAttemptsRef = useRef(0);

  const MAX_RECONNECT_ATTEMPTS = 5;
  const INITIAL_RECONNECT_DELAY = 1000;

  useEffect(() => {
    const WS_URL = 'wss://ujtavgmgeefutsadbyzv.supabase.co/functions/v1/crypto-data-stream';
    console.log('🎬 [PublicPrices] useEffect starting, WS_URL:', WS_URL);
    
    const connect = () => {
      try {
        console.log('🔌 [PublicPrices] Attempting connection to:', WS_URL);
        const ws = new WebSocket(WS_URL);
        wsRef.current = ws;
        
        console.log('🔌 [PublicPrices] WebSocket object created, readyState:', ws.readyState);

        ws.onopen = () => {
          console.log('✅ [PublicPrices] WebSocket connected to broadcaster');
          setIsConnected(true);
          setError(null);
          reconnectAttemptsRef.current = 0;
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);

            // Broadcaster może wysyłać dane w dwóch formatach:
            // 1. Pojedynczy obiekt: { exchange, symbol, price, ... }
            // 2. Zagnieżdżony: { public_prices: { exchange: { symbol: {...} } } }
            
            if (data.exchange && data.symbol && data.price) {
              // Format 1: Pojedynczy update ceny
              const key = `${data.exchange}-${data.symbol}`;
              setPrices(prev => {
                const newPrices = new Map(prev);
                newPrices.set(key, {
                  symbol: data.symbol,
                  exchange: data.exchange,
                  price: data.price,
                  priceChange: data.priceChange,
                  fundingRate: data.fundingRate,
                  volume: data.volume,
                  timestamp: data.timestamp || Date.now()
                });
                return newPrices;
              });
            } else if (data.public_prices && typeof data.public_prices === 'object') {
              // Format 2: Batch update - zagnieżdżone dane
              setPrices(prev => {
                const newPrices = new Map(prev);
                
                Object.entries(data.public_prices).forEach(([exchange, symbols]: [string, any]) => {
                  if (symbols && typeof symbols === 'object') {
                    Object.entries(symbols).forEach(([symbol, priceData]: [string, any]) => {
                      const key = `${exchange}-${symbol}`;
                      newPrices.set(key, {
                        symbol,
                        exchange,
                        price: priceData.price || priceData,
                        priceChange: priceData.priceChange,
                        fundingRate: priceData.fundingRate,
                        volume: priceData.volume,
                        timestamp: priceData.timestamp || Date.now()
                      });
                    });
                  }
                });
                
                return newPrices;
              });
            }
          } catch (err) {
            console.error('❌ [PublicPrices] Error parsing message:', err);
          }
        };

        ws.onerror = (error) => {
          console.error('❌ [PublicPrices] WebSocket error:', error);
          console.error('❌ [PublicPrices] WebSocket readyState on error:', ws.readyState);
          console.error('❌ [PublicPrices] URL was:', WS_URL);
          setError('Connection error - cannot reach server');
        };

        ws.onclose = () => {
          console.log('🔌 [PublicPrices] WebSocket disconnected');
          setIsConnected(false);
          wsRef.current = null;

          if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
            const delay = INITIAL_RECONNECT_DELAY * Math.pow(2, reconnectAttemptsRef.current);
            console.log(`⏳ [PublicPrices] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current + 1}/${MAX_RECONNECT_ATTEMPTS})`);
            
            reconnectTimeoutRef.current = setTimeout(() => {
              reconnectAttemptsRef.current++;
              connect();
            }, delay);
          } else {
            setError('Maximum reconnection attempts reached');
          }
        };
      } catch (err) {
        console.error('❌ [PublicPrices] Connection error:', err);
        setError(err instanceof Error ? err.message : 'Unknown error');
      }
    };

    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return {
    prices,
    isConnected,
    error
  };
};
