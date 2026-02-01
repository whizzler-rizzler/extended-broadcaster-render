import { useState, useEffect, useRef } from 'react';
import { getApiUrl } from '@/config/api';

interface AccountStats {
  id: string;
  name: string;
  positions_initialized: boolean;
  balance_initialized: boolean;
  trades_initialized: boolean;
  orders_initialized: boolean;
  positions_age_seconds: number;
  balance_age_seconds: number | null;
}

export interface BroadcasterStats {
  broadcaster?: {
    connected_clients: number;
    accounts_configured: number;
    extended_api_rate: string;
  };
  accounts?: AccountStats[];
  timestamp?: number;
  // Legacy format support
  cache?: {
    positions_age_seconds: number;
    balance_age_seconds: number;
    trades_age_seconds: number;
    orders_age_seconds?: number;
  };
}

interface BroadcasterStatsData {
  stats: BroadcasterStats | null;
  lastUpdate: Date;
  error: string | null;
  pollInterval: number;
  lastPollDuration: number;
}

const POLL_INTERVAL = 2000;

export const useBroadcasterStats = () => {
  const [data, setData] = useState<BroadcasterStatsData>({
    stats: null,
    lastUpdate: new Date(),
    error: null,
    pollInterval: POLL_INTERVAL,
    lastPollDuration: 0,
  });
  const intervalRef = useRef<NodeJS.Timeout>();
  const lastFetchTimeRef = useRef<number>(Date.now());

  const fetchStats = async () => {
    const fetchStart = Date.now();
    const timeSinceLastFetch = fetchStart - lastFetchTimeRef.current;
    
    try {
      const response = await fetch(getApiUrl('/api/broadcaster/stats'));
      const result = await response.json();
      const fetchDuration = Date.now() - fetchStart;
      
      lastFetchTimeRef.current = fetchStart;
      
      setData({
        stats: result,
        lastUpdate: new Date(),
        error: null,
        pollInterval: timeSinceLastFetch,
        lastPollDuration: fetchDuration,
      });
    } catch (error) {
      console.error('❌ [useBroadcasterStats] Error fetching broadcaster stats:', error);
      setData(prev => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Unknown error',
      }));
    }
  };

  useEffect(() => {
    fetchStats();
    
    intervalRef.current = setInterval(fetchStats, POLL_INTERVAL);
    
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, []);

  return data;
};
