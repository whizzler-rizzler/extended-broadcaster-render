import { useState, useEffect, useRef } from 'react';
import { supabase } from '@/integrations/supabase/client';

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
  markPrice?: string;
  createdAt: number;
  updatedAt: number;
}

interface AccountBalance {
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

interface Trade {
  id: string;
  accountId: number;
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

interface MarketData {
  positions: Position[];
  balance: AccountBalance | null;
  trades: Trade[];
  lastUpdate: Date;
  error: string | null;
}

const POLL_INTERVAL = 1000; // Poll every 1 second

export const useSupabaseMarketData = () => {
  const [data, setData] = useState<MarketData>({
    positions: [],
    balance: null,
    trades: [],
    lastUpdate: new Date(),
    error: null,
  });
  const intervalRef = useRef<NodeJS.Timeout>();

  const fetchMarketData = async () => {
    try {
      const { data: snapshot, error } = await supabase
        .from('market_data_snapshots')
        .select('positions, balance, trades, updated_at')
        .order('updated_at', { ascending: false })
        .limit(1)
        .maybeSingle();

      if (error) {
        console.error('❌ [useSupabaseMarketData] Error:', error);
        setData(prev => ({ ...prev, error: error.message }));
        return;
      }

      if (snapshot) {
        setData({
          positions: (snapshot.positions as any as Position[]) || [],
          balance: (snapshot.balance as any) as AccountBalance | null,
          trades: (snapshot.trades as any as Trade[]) || [],
          lastUpdate: new Date(snapshot.updated_at),
          error: null,
        });
        console.log('✅ [useSupabaseMarketData] Data updated from Supabase');
      }
    } catch (error) {
      console.error('❌ [useSupabaseMarketData] Error:', error);
      setData(prev => ({ 
        ...prev, 
        error: error instanceof Error ? error.message : 'Unknown error' 
      }));
    }
  };

  useEffect(() => {
    // Initial fetch
    fetchMarketData();
    
    // Set up polling
    intervalRef.current = setInterval(fetchMarketData, POLL_INTERVAL);
    
    // Set up realtime subscription
    const channel = supabase
      .channel('market_data_changes')
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'market_data_snapshots'
        },
        () => {
          console.log('🔄 [useSupabaseMarketData] Realtime update detected');
          fetchMarketData();
        }
      )
      .subscribe();
    
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
      supabase.removeChannel(channel);
    };
  }, []);

  return data;
};
