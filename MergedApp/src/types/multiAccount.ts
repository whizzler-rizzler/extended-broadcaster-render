// Multi-Account Types for 10-account monitoring system

export interface Position {
  market: string;
  side: string;
  leverage: string;
  size: string;
  value: string;
  openPrice: number;
  markPrice: number;
  liquidationPrice: number;
  unrealisedPnl: number;
  midPriceUnrealisedPnl?: number; // Preferred PnL field from API
  realisedPnl: number;
  margin: number;
  status: string;
  createdAt: number;
  updatedAt: number;
}

export interface AccountBalance {
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

export interface Order {
  id: string;
  market: string;
  side: string;
  type: string;
  price: string;
  size: string;
  status: string;
  createdAt: number;
}

export interface Trade {
  id: string;
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

export interface SingleAccountData {
  id: string;
  name: string;
  isActive: boolean;
  lastUpdate: Date;
  balance: AccountBalance | null;
  positions: Position[];
  orders: Order[];
  trades: Trade[];
  // Computed values
  computed: {
    totalPnl: number;
    totalNotional: number;
    positionCount: number;
    equity: number;
    marginRatio: number;
    longPositions: number;
    shortPositions: number;
    longPnl: number;
    shortPnl: number;
    volume24h: number;
    volume7d: number;
    volume30d: number;
  };
}

export interface MultiAccountState {
  accounts: Map<string, SingleAccountData>;
  activeAccountIds: string[];
  lastGlobalUpdate: Date;
  isConnected: boolean;
  error: string | null;
}

export interface AggregatedPortfolio {
  totalEquity: number;
  totalPnl: number;
  totalNotional: number;
  totalPositions: number;
  totalLongPositions: number;
  totalShortPositions: number;
  totalLongPnl: number;
  totalShortPnl: number;
  averageMarginRatio: number;
  accountCount: number;
  totalVolume24h: number;
  totalVolume7d: number;
  totalVolume30d: number;
}

// Default empty account for initialization
export const createEmptyAccount = (id: string, name: string): SingleAccountData => ({
  id,
  name,
  isActive: false,
  lastUpdate: new Date(),
  balance: null,
  positions: [],
  orders: [],
  trades: [],
  computed: {
    totalPnl: 0,
    totalNotional: 0,
    positionCount: 0,
    equity: 0,
    marginRatio: 0,
    longPositions: 0,
    shortPositions: 0,
    longPnl: 0,
    shortPnl: 0,
    volume24h: 0,
    volume7d: 0,
    volume30d: 0,
  },
});

// Helper to compute derived values from account data
export const computeAccountStats = (account: SingleAccountData): SingleAccountData['computed'] => {
  // Ensure positions is always an array
  const rawPositions = Array.isArray(account.positions) ? account.positions : [];
  const positions = rawPositions.filter(p => p.status === 'OPENED');
  const longPositions = positions.filter(p => p.side === 'LONG');
  const shortPositions = positions.filter(p => p.side === 'SHORT');

  // Use midPriceUnrealisedPnl if available, fallback to unrealisedPnl
  const getPnl = (p: Position) => {
    const midPnl = Number(p.midPriceUnrealisedPnl);
    if (!isNaN(midPnl) && midPnl !== 0) return midPnl;
    return Number(p.unrealisedPnl) || 0;
  };

  const longPnl = longPositions.reduce((sum, p) => sum + getPnl(p), 0);
  const shortPnl = shortPositions.reduce((sum, p) => sum + getPnl(p), 0);
  const totalNotional = positions.reduce((sum, p) => sum + parseFloat(p.value || '0'), 0);

  // Calculate volume from trades for different periods
  const trades = Array.isArray(account.trades) ? account.trades : [];
  const now = Date.now();
  const oneDayAgo = now - 24 * 60 * 60 * 1000;
  const sevenDaysAgo = now - 7 * 24 * 60 * 60 * 1000;
  const thirtyDaysAgo = now - 30 * 24 * 60 * 60 * 1000;

  const volume24h = trades
    .filter(t => t.createdTime > oneDayAgo)
    .reduce((sum, t) => sum + parseFloat(t.value || '0'), 0);
  
  const volume7d = trades
    .filter(t => t.createdTime > sevenDaysAgo)
    .reduce((sum, t) => sum + parseFloat(t.value || '0'), 0);
  
  const volume30d = trades
    .filter(t => t.createdTime > thirtyDaysAgo)
    .reduce((sum, t) => sum + parseFloat(t.value || '0'), 0);

  return {
    totalPnl: longPnl + shortPnl,
    totalNotional,
    positionCount: positions.length,
    equity: parseFloat(account.balance?.equity || '0'),
    marginRatio: parseFloat(account.balance?.marginRatio || '0'),
    longPositions: longPositions.length,
    shortPositions: shortPositions.length,
    longPnl,
    shortPnl,
    volume24h,
    volume7d,
    volume30d,
  };
};

// Aggregate all accounts into portfolio stats
export const aggregatePortfolio = (accounts: Map<string, SingleAccountData>): AggregatedPortfolio => {
  const activeAccounts = Array.from(accounts.values()).filter(a => a.isActive);
  
  if (activeAccounts.length === 0) {
    return {
      totalEquity: 0,
      totalPnl: 0,
      totalNotional: 0,
      totalPositions: 0,
      totalLongPositions: 0,
      totalShortPositions: 0,
      totalLongPnl: 0,
      totalShortPnl: 0,
      averageMarginRatio: 0,
      accountCount: 0,
      totalVolume24h: 0,
      totalVolume7d: 0,
      totalVolume30d: 0,
    };
  }

  const totals = activeAccounts.reduce(
    (acc, account) => ({
      totalEquity: acc.totalEquity + account.computed.equity,
      totalPnl: acc.totalPnl + account.computed.totalPnl,
      totalNotional: acc.totalNotional + account.computed.totalNotional,
      totalPositions: acc.totalPositions + account.computed.positionCount,
      totalLongPositions: acc.totalLongPositions + account.computed.longPositions,
      totalShortPositions: acc.totalShortPositions + account.computed.shortPositions,
      totalLongPnl: acc.totalLongPnl + account.computed.longPnl,
      totalShortPnl: acc.totalShortPnl + account.computed.shortPnl,
      marginRatioSum: acc.marginRatioSum + account.computed.marginRatio,
      totalVolume24h: acc.totalVolume24h + account.computed.volume24h,
      totalVolume7d: acc.totalVolume7d + account.computed.volume7d,
      totalVolume30d: acc.totalVolume30d + account.computed.volume30d,
    }),
    {
      totalEquity: 0,
      totalPnl: 0,
      totalNotional: 0,
      totalPositions: 0,
      totalLongPositions: 0,
      totalShortPositions: 0,
      totalLongPnl: 0,
      totalShortPnl: 0,
      marginRatioSum: 0,
      totalVolume24h: 0,
      totalVolume7d: 0,
      totalVolume30d: 0,
    }
  );

  return {
    ...totals,
    averageMarginRatio: totals.marginRatioSum / activeAccounts.length,
    accountCount: activeAccounts.length,
  };
};
