import { useState, useEffect, useCallback } from 'react';
import { getApiUrl } from '@/config/api';

interface AccountPoints {
  account_name: string;
  points: number;
  last_update: number;
}

interface PointsData {
  accounts: Record<string, AccountPoints>;
  total_points: number;
  last_update: number;
  cache_age_seconds: number | null;
  poll_interval_seconds: number;
}

interface UseEarnedPointsResult {
  points: PointsData | null;
  totalPoints: number;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  lastUpdate: Date | null;
}

export const useEarnedPoints = (): UseEarnedPointsResult => {
  const [points, setPoints] = useState<PointsData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const fetchPoints = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      
      const response = await fetch(getApiUrl('/api/points'));
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      
      const data: PointsData = await response.json();
      setPoints(data);
      setLastUpdate(new Date());
      console.log(`💎 [Points] Fetched: ${data.total_points.toLocaleString()} total points`);
    } catch (err) {
      console.error('❌ [Points] Fetch error:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      
      const response = await fetch(getApiUrl('/api/points/refresh'), {
        method: 'POST'
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      
      await fetchPoints();
    } catch (err) {
      console.error('❌ [Points] Refresh error:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
      setIsLoading(false);
    }
  }, [fetchPoints]);

  useEffect(() => {
    fetchPoints();
    
    const interval = setInterval(fetchPoints, 60000);
    
    return () => clearInterval(interval);
  }, [fetchPoints]);

  return {
    points,
    totalPoints: points?.total_points ?? 0,
    isLoading,
    error,
    refresh,
    lastUpdate
  };
};
