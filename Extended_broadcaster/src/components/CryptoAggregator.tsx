import { useEffect, useState, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ActivityIcon, SearchIcon, TrendingUpIcon, ArrowUpIcon, ArrowDownIcon } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface PriceData {
  exchange: string;
  symbol: string;
  price: string;
  timestamp: number;
  volume?: string;
  bid?: string;
  ask?: string;
  priceChange?: string;
  fundingRate?: string;
}

const CryptoAggregator = () => {
  const [prices, setPrices] = useState<Map<string, PriceData>>(new Map());
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected'>('disconnected');
  const [searchTerm, setSearchTerm] = useState('');
  const [exchangeCountFilter, setExchangeCountFilter] = useState<'all' | '1' | '2' | '3'>('all');
  const [sortConfig, setSortConfig] = useState<{
    key:
      | 'symbol'
      | 'lighterPrice'
      | 'lighterVolume'
      | 'extendedPrice'
      | 'extendedVolume'
      | 'paradexPrice'
      | 'paradexVolume';
    direction: 'asc' | 'desc';
  } | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const { toast } = useToast();
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  const connectWebSocket = () => {
    try {
      setConnectionStatus('connecting');
      const projectId = 'ujtavgmgeefutsadbyzv';
      const ws = new WebSocket(`wss://${projectId}.supabase.co/functions/v1/crypto-aggregator`);
      
      ws.onopen = () => {
        console.log('Connected to aggregator');
        setConnectionStatus('connected');
        toast({
          title: "Połączono",
          description: "Odbieranie danych z giełd w czasie rzeczywistym",
        });
      };

      ws.onmessage = (event) => {
        try {
          const data: PriceData = JSON.parse(event.data);
          setPrices(prev => {
            const newPrices = new Map(prev);
            const key = `${data.exchange}_${data.symbol}`;
            newPrices.set(key, data);
            return newPrices;
          });
        } catch (error) {
          console.error('Error parsing message:', error);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnectionStatus('disconnected');
      };

      ws.onclose = () => {
        console.log('WebSocket closed, reconnecting in 3s...');
        setConnectionStatus('disconnected');
        reconnectTimeoutRef.current = setTimeout(connectWebSocket, 3000);
      };

      wsRef.current = ws;
    } catch (error) {
      console.error('Error connecting to WebSocket:', error);
      setConnectionStatus('disconnected');
      reconnectTimeoutRef.current = setTimeout(connectWebSocket, 3000);
    }
  };

  useEffect(() => {
    connectWebSocket();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const normalizeSymbol = (symbol: string) => {
    if (!symbol) return '';
    const upper = symbol.toUpperCase();
    const simpleMatch = upper.match(/^([A-Z0-9]+)(?:[-_](?:USD|USDC))?(?:-PERP)?$/);
    if (simpleMatch) {
      return simpleMatch[1];
    }
    return upper;
  };

  const groupedPrices = new Map<
    string,
    {
      lighter?: PriceData;
      extended?: PriceData;
      paradex?: PriceData;
    }
  >();

  Array.from(prices.values()).forEach((data) => {
    const normalizedSymbol = normalizeSymbol(data.symbol);
    if (!normalizedSymbol) return;

    if (!groupedPrices.has(normalizedSymbol)) {
      groupedPrices.set(normalizedSymbol, {});
    }
    const group = groupedPrices.get(normalizedSymbol)!;
    if (data.exchange === 'Lighter') group.lighter = data;
    else if (data.exchange === 'Extended') group.extended = data;
    else if (data.exchange === 'Paradex') group.paradex = data;
  });

  const lighterStats = {
    volume: Array.from(prices.values())
      .filter((p) => p.exchange === 'Lighter' && p.volume)
      .reduce((sum, p) => sum + parseFloat(p.volume || '0'), 0),
    markets: new Set(
      Array.from(prices.values())
        .filter((p) => p.exchange === 'Lighter')
        .map((p) => normalizeSymbol(p.symbol))
    ).size,
  };

  const extendedStats = {
    volume: Array.from(prices.values())
      .filter((p) => p.exchange === 'Extended' && p.volume)
      .reduce((sum, p) => sum + parseFloat(p.volume || '0'), 0),
    markets: new Set(
      Array.from(prices.values())
        .filter((p) => p.exchange === 'Extended')
        .map((p) => normalizeSymbol(p.symbol))
    ).size,
  };

  const paradexStats = {
    volume: Array.from(prices.values())
      .filter((p) => p.exchange === 'Paradex' && p.volume)
      .reduce((sum, p) => sum + parseFloat(p.volume || '0'), 0),
    markets: new Set(
      Array.from(prices.values())
        .filter((p) => p.exchange === 'Paradex')
        .map((p) => normalizeSymbol(p.symbol))
    ).size,
  };

  const formatPrice = (price: string) => {
    const num = parseFloat(price);
    if (num < 0.01) return num.toFixed(6);
    if (num < 1) return num.toFixed(4);
    return num.toFixed(2);
  };

  const formatVolume = (volume: number) => {
    if (volume >= 1e9) return `$${(volume / 1e9).toFixed(1)}B`;
    if (volume >= 1e6) return `$${(volume / 1e6).toFixed(1)}M`;
    if (volume >= 1e3) return `$${(volume / 1e3).toFixed(1)}K`;
    return `$${volume.toFixed(0)}`;
  };

  const formatFundingRate = (rate: string | undefined) => {
    if (!rate) return '-';
    const num = parseFloat(rate);
    if (Number.isNaN(num)) return '-';
    return `${(num * 100).toFixed(4)}%`;
  };

  const calculatePriceDeviation = (group: {
    lighter?: PriceData;
    extended?: PriceData;
    paradex?: PriceData;
  }) => {
    const prices: number[] = [];
    if (group.lighter) prices.push(parseFloat(group.lighter.price));
    if (group.extended) prices.push(parseFloat(group.extended.price));
    if (group.paradex) prices.push(parseFloat(group.paradex.price));

    if (prices.length === 0) return { avgPrice: 0, lighterDev: null, extendedDev: null, paradexDev: null };

    const avgPrice = prices.reduce((sum, p) => sum + p, 0) / prices.length;

    const lighterDev = group.lighter 
      ? ((parseFloat(group.lighter.price) - avgPrice) / avgPrice * 100).toFixed(2)
      : null;
    
    const extendedDev = group.extended
      ? ((parseFloat(group.extended.price) - avgPrice) / avgPrice * 100).toFixed(2)
      : null;
    
    const paradexDev = group.paradex
      ? ((parseFloat(group.paradex.price) - avgPrice) / avgPrice * 100).toFixed(2)
      : null;

    return { avgPrice, lighterDev, extendedDev, paradexDev };
  };

  const formatDeviation = (deviation: string | null) => {
    if (deviation === null) return '-';
    const num = parseFloat(deviation);
    return num >= 0 ? `+${deviation}%` : `${deviation}%`;
  };

  const calculateSpread = (group: {
    lighter?: PriceData;
    extended?: PriceData;
    paradex?: PriceData;
  }) => {
    const pricesArray = [
      group.lighter ? parseFloat(group.lighter.price) : null,
      group.extended ? parseFloat(group.extended.price) : null,
      group.paradex ? parseFloat(group.paradex.price) : null,
    ].filter((p) => p !== null) as number[];

    if (pricesArray.length < 2) return null;
    const max = Math.max(...pricesArray);
    const min = Math.min(...pricesArray);
    return ((max - min) / min * 100).toFixed(2);
  };

  const filteredSymbols = (() => {
    const entries = Array.from(groupedPrices.entries())
      .filter(([symbol]) =>
        symbol.toLowerCase().includes(searchTerm.toLowerCase())
      )
      .filter(([, group]) => {
        if (exchangeCountFilter === 'all') return true;
        const count =
          (group.lighter ? 1 : 0) +
          (group.extended ? 1 : 0) +
          (group.paradex ? 1 : 0);
        return count === Number(exchangeCountFilter);
      });

    if (!sortConfig) {
      return entries.sort(([a], [b]) => a.localeCompare(b));
    }

    const { key, direction } = sortConfig;

    return entries.sort(([symbolA, groupA], [symbolB, groupB]) => {
      if (key === 'symbol') {
        return direction === 'asc'
          ? symbolA.localeCompare(symbolB)
          : symbolB.localeCompare(symbolA);
      }

      const getValue = (group: {
        lighter?: PriceData;
        extended?: PriceData;
        paradex?: PriceData;
      }) => {
        switch (key) {
          case 'lighterPrice':
            return group.lighter ? parseFloat(group.lighter.price) : Number.NaN;
          case 'lighterVolume':
            return group.lighter?.volume
              ? parseFloat(group.lighter.volume)
              : Number.NaN;
          case 'extendedPrice':
            return group.extended ? parseFloat(group.extended.price) : Number.NaN;
          case 'extendedVolume':
            return group.extended?.volume
              ? parseFloat(group.extended.volume)
              : Number.NaN;
          case 'paradexPrice':
            return group.paradex ? parseFloat(group.paradex.price) : Number.NaN;
          case 'paradexVolume':
            return group.paradex?.volume
              ? parseFloat(group.paradex.volume)
              : Number.NaN;
          default:
            return Number.NaN;
        }
      };

      const valA = getValue(groupA);
      const valB = getValue(groupB);

      if (Number.isNaN(valA) && Number.isNaN(valB)) return 0;
      if (Number.isNaN(valA)) return 1;
      if (Number.isNaN(valB)) return -1;

      return direction === 'asc' ? valA - valB : valB - valA;
    });
  })();

  const avgSpread =
    filteredSymbols.length > 0
      ? (
          filteredSymbols.reduce((sum, [, group]) => {
            const spread = calculateSpread(group);
            return sum + (spread ? parseFloat(spread) : 0);
          }, 0) / filteredSymbols.length
        ).toFixed(3)
      : '0.000';

  const handleSort = (
    key:
      | 'symbol'
      | 'lighterPrice'
      | 'lighterVolume'
      | 'extendedPrice'
      | 'extendedVolume'
      | 'paradexPrice'
      | 'paradexVolume'
  ) => {
    setSortConfig((prev) =>
      prev && prev.key === key
        ? { key, direction: prev.direction === 'asc' ? 'desc' : 'asc' }
        : { key, direction: 'asc' }
    );
  };

  return (
    <div className="min-h-screen bg-background p-4 md:p-8">
      <div className="max-w-[1600px] mx-auto space-y-8">
        <div>
          <h2 className="text-2xl font-bold text-foreground mb-4 flex items-center gap-2">
            <TrendingUpIcon className="w-6 h-6" />
            Statystyki Globalne
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-success">Lighter Volume</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-foreground">{lighterStats.volume > 0 ? formatVolume(lighterStats.volume) : "Brak danych"}</div>
                <p className="text-xs text-muted-foreground mt-1">{lighterStats.markets} markets</p>
              </CardContent>
            </Card>

            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-chart-3">Extended Volume</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-foreground">{extendedStats.volume > 0 ? formatVolume(extendedStats.volume) : "Brak danych"}</div>
                <p className="text-xs text-muted-foreground mt-1">{extendedStats.markets} markets</p>
              </CardContent>
            </Card>

            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-accent">Paradex Volume</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-foreground">{paradexStats.volume > 0 ? formatVolume(paradexStats.volume) : "Brak danych"}</div>
                <p className="text-xs text-muted-foreground mt-1">{paradexStats.markets} markets</p>
              </CardContent>
            </Card>

            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-accent">Średni Spread</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-foreground">{avgSpread}%</div>
                <p className="text-xs text-muted-foreground mt-1">cross-exchange</p>
              </CardContent>
            </Card>
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-bold text-foreground flex items-center gap-2">
              <ActivityIcon className="w-6 h-6" />
              Porównanie Giełd
            </h2>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border bg-card">
                <div className={`w-2 h-2 rounded-full ${
                  connectionStatus === 'connected' ? 'bg-success animate-pulse' :
                  connectionStatus === 'connecting' ? 'bg-accent' : 'bg-danger'
                }`} />
                <span className="text-sm text-muted-foreground">
                  {connectionStatus === 'connected' ? 'Live' : 
                   connectionStatus === 'connecting' ? 'Łączenie...' : 'Rozłączono'}
                </span>
              </div>
              <Select
                value={exchangeCountFilter}
                onValueChange={(value) =>
                  setExchangeCountFilter(value as 'all' | '1' | '2' | '3')
                }
              >
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="Filtruj po liczbie giełd" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Wszystkie giełdy</SelectItem>
                  <SelectItem value="1">Na 1 giełdzie</SelectItem>
                  <SelectItem value="2">Na 2 giełdach</SelectItem>
                  <SelectItem value="3">Na 3 giełdach</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <Card className="bg-card border-border">
            <CardContent className="p-0">
              <div className="relative overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="border-border hover:bg-transparent">
                      <TableHead
                        className="font-bold text-foreground w-[100px] sticky left-0 bg-card z-10 cursor-pointer select-none"
                        onClick={() => handleSort('symbol')}
                      >
                        Market ↕
                      </TableHead>
                       <TableHead className="text-success font-semibold text-center" colSpan={4}>
                        Lighter
                      </TableHead>
                      <TableHead className="text-chart-3 font-semibold text-center" colSpan={4}>
                        Extended
                      </TableHead>
                      <TableHead className="text-accent font-semibold text-center" colSpan={4}>
                        Paradex
                      </TableHead>
                    </TableRow>
                    <TableRow className="border-border hover:bg-transparent">
                      <TableHead className="sticky left-0 bg-card z-10"></TableHead>
                      <TableHead
                        className="text-success text-xs cursor-pointer select-none"
                        onClick={() => handleSort('lighterPrice')}
                      >
                        L Price ↕
                      </TableHead>
                      <TableHead
                        className="text-success text-xs cursor-pointer select-none"
                        onClick={() => handleSort('lighterVolume')}
                      >
                        L Vol ↕
                      </TableHead>
                      <TableHead className="text-success text-xs">L %</TableHead>
                      <TableHead className="text-success text-xs">L FR</TableHead>
                      <TableHead
                        className="text-chart-3 text-xs cursor-pointer select-none"
                        onClick={() => handleSort('extendedPrice')}
                      >
                        E Price ↕
                      </TableHead>
                      <TableHead
                        className="text-chart-3 text-xs cursor-pointer select-none"
                        onClick={() => handleSort('extendedVolume')}
                      >
                        E Vol ↕
                      </TableHead>
                      <TableHead className="text-chart-3 text-xs">E %</TableHead>
                      <TableHead className="text-chart-3 text-xs">E FR</TableHead>
                      <TableHead
                        className="text-accent text-xs cursor-pointer select-none"
                        onClick={() => handleSort('paradexPrice')}
                      >
                        P Price ↕
                      </TableHead>
                      <TableHead
                        className="text-accent text-xs cursor-pointer select-none"
                        onClick={() => handleSort('paradexVolume')}
                      >
                        P Vol ↕
                      </TableHead>
                      <TableHead className="text-accent text-xs">P %</TableHead>
                      <TableHead className="text-accent text-xs">P FR</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredSymbols.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={13} className="text-center py-8 text-muted-foreground">
                          Oczekiwanie na dane...
                        </TableCell>
                      </TableRow>
                    ) : (
                      filteredSymbols.map(([symbol, group]) => {
                        const { lighterDev, extendedDev, paradexDev } = calculatePriceDeviation(group);
                        
                        return (
                        <TableRow key={symbol} className="border-border hover:bg-muted/5">
                          <TableCell className="font-bold text-foreground sticky left-0 bg-card z-10">
                            {symbol}
                          </TableCell>
                          
                          <TableCell className="text-success font-mono">
                            {group.lighter ? `$${formatPrice(group.lighter.price)}` : '-'}
                          </TableCell>
                          <TableCell className="text-success text-sm">
                            {group.lighter?.volume ? formatVolume(parseFloat(group.lighter.volume)) : '-'}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {formatDeviation(lighterDev)}
                          </TableCell>
                          <TableCell className="text-success text-xs">
                            {formatFundingRate(group.lighter?.fundingRate)}
                          </TableCell>

                          <TableCell className="text-chart-3 font-mono">
                            {group.extended ? `$${formatPrice(group.extended.price)}` : '-'}
                          </TableCell>
                          <TableCell className="text-chart-3 text-sm">
                            {group.extended?.volume ? formatVolume(parseFloat(group.extended.volume)) : '-'}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {formatDeviation(extendedDev)}
                          </TableCell>
                          <TableCell className="text-chart-3 text-xs">
                            {formatFundingRate(group.extended?.fundingRate)}
                          </TableCell>

                          <TableCell className="text-accent font-mono">
                            {group.paradex ? `$${formatPrice(group.paradex.price)}` : '-'}
                          </TableCell>
                          <TableCell className="text-accent text-sm">
                            {group.paradex?.volume ? formatVolume(parseFloat(group.paradex.volume)) : '-'}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {formatDeviation(paradexDev)}
                          </TableCell>
                          <TableCell className="text-accent text-xs">
                            {formatFundingRate(group.paradex?.fundingRate)}
                          </TableCell>
                        </TableRow>
                      )})
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default CryptoAggregator;
