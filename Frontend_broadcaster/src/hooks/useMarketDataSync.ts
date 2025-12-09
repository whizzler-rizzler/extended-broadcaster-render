import { useEffect, useRef } from 'react';
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

interface ExtendedData {
  marginRatio?: string;
  equity?: string;
  availableBalance?: string;
  [key: string]: any;
}

interface PublicPrices {
  [key: string]: {
    price: string;
    exchange: string;
    symbol: string;
    priceChange?: string;
    fundingRate?: string;
    volume?: string;
  };
}

interface MarketDataSyncProps {
  positions: Position[];
  balance: AccountBalance | null;
  extendedData: ExtendedData | null;
  publicPrices: PublicPrices;
  trades: any[];
}

export const useMarketDataSync = ({ positions, balance, extendedData, publicPrices, trades }: MarketDataSyncProps) => {
  const lastSyncRef = useRef<number>(0);
  const dataRef = useRef({ positions, balance, extendedData, publicPrices, trades });

  // Update ref when data changes (no re-render, no new interval)
  useEffect(() => {
    dataRef.current = { positions, balance, extendedData, publicPrices, trades };
  }, [positions, balance, extendedData, publicPrices, trades]);

  const syncToDatabase = async () => {
    try {
      // Throttle to max once per 250ms (same as REST API polling)
      const now = Date.now();
      if (now - lastSyncRef.current < 250) {
        return;
      }
      lastSyncRef.current = now;

      const { positions: pos, balance: bal, extendedData: ext, publicPrices: prices, trades: trd } = dataRef.current;

      // Get current snapshot to check if we need to update
      const { data: existing } = await supabase
        .from('market_data_snapshots')
        .select('id, updated_at')
        .order('updated_at', { ascending: false })
        .limit(1)
        .maybeSingle();

      const dataToSync = {
        positions: pos as any,
        balance: bal as any,
        extended_data: ext as any,
        public_prices: prices as any,
        trades: trd as any,
        updated_at: new Date().toISOString(),
      };

      if (existing) {
        // Update existing snapshot
        const { error } = await supabase
          .from('market_data_snapshots')
          .update(dataToSync)
          .eq('id', existing.id);

        if (error) {
          console.error('❌ [Sync] Error updating snapshot:', error);
        }
      } else {
        // Create new snapshot
        const { error } = await supabase
          .from('market_data_snapshots')
          .insert([dataToSync]);

        if (error) {
          console.error('❌ [Sync] Error creating snapshot:', error);
        }
      }
    } catch (error) {
      console.error('❌ [Sync] Error syncing data:', error);
    }
  };

  // Set up interval ONCE - only on mount
  useEffect(() => {
    const interval = setInterval(syncToDatabase, 250);

    return () => {
      clearInterval(interval);
    };
  }, []); // Empty deps - interval created only once

  return null;
};
