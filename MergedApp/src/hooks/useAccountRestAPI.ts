import { useState, useEffect, useRef } from 'react';
import { getApiUrl } from '@/config/api';

interface Position {
  market: string;
  status: string;
  side: string;
  leverage: string;
  size: string;
  value: string;
  openPrice: string;
  liquidationPrice: string;
  margin: string;
  unrealisedPnl: string;
  midPriceUnrealisedPnl: string;
  realisedPnl: string;
  createdAt: number;
  updatedAt: number;
}

interface AccountData {
  collateralName: string;
  balance: string;
  status: string;
  equity: string;
  availableForTrade: string;
  availableForWithdrawal: string;
  unrealisedPnl: string;
  initialMargin: string;
  marginRatio: string;
  updatedTime: number;
  exposure: string;
  leverage: string;
}

interface RestAPIData {
  balance: AccountData | null;
  positions: Position[];
  lastUpdate: Date;
  error: string | null;
}

export const useAccountRestAPI = () => {
  const [data, setData] = useState<RestAPIData>({
    balance: null,
    positions: [],
    lastUpdate: new Date(),
    error: null,
  });

  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const fetchAccountData = async () => {
    try {
      const response = await fetch(getApiUrl('/api/cached-account'));
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const jsonData = await response.json();
      console.log('🔄 [Cached REST API] Fetched data (cache age:', jsonData.cache_age_ms, 'ms)');

      setData({
        balance: jsonData.balance?.data || null,
        positions: jsonData.positions?.data || [],
        lastUpdate: new Date(),
        error: null,
      });
    } catch (error) {
      console.error('❌ [REST API] Error fetching data:', error);
      setData(prev => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Unknown error',
        lastUpdate: new Date(),
      }));
    }
  };

  useEffect(() => {
    // Initial fetch
    fetchAccountData();

    // Poll 4 times per second (every 250ms)
    intervalRef.current = setInterval(fetchAccountData, 250);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, []);

  return data;
};
