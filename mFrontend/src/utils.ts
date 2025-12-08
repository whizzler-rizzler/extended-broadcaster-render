export function formatMoney(value: string | number | undefined): string {
  const num = parseFloat(String(value)) || 0;
  return '$' + num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function formatAccountName(name: string): string {
  const match = name.match(/Lighter_(\d+)_([a-fA-F0-9]+)/);
  if (match) {
    return `Lighter ${match[1]} (${match[2]})`;
  }
  return name;
}

export function getPositionSymbol(marketIndex: number | undefined): string {
  const markets: Record<string, string> = {
    '1': 'BTC', '2': 'ETH', '3': 'SOL', '4': 'AVAX', '5': 'ARB',
    '6': 'OP', '7': 'MATIC', '8': 'DOGE', '9': 'LINK', '10': 'SUI',
    '11': 'PEPE', '12': 'WIF', '13': 'NEAR', '14': 'FTM', '15': 'TIA'
  };
  return markets[String(marketIndex)] || `MKT${marketIndex}`;
}

export function formatTime(timestamp: number | undefined): string {
  if (!timestamp) return '-';
  const ts = timestamp > 10000000000 ? timestamp / 1000 : timestamp;
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
