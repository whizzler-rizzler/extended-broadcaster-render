import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.39.3';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

// Exchange configurations with correct URLs
  const EXCHANGES = {
    lighter: {
      url: 'wss://mainnet.zklighter.elliot.ai/stream',
      marketsUrl: 'https://mainnet.zklighter.elliot.ai/api/v1/orderBooks',
      name: 'Lighter',
    },
    extended: {
      priceUrl: 'wss://api.starknet.extended.exchange/stream.extended.exchange/v1/prices/mark',
      name: 'Extended',
    },
    paradex: {
      url: 'wss://ws.api.prod.paradex.trade/v1',
      marketsUrl: 'https://api.prod.paradex.trade/v1/markets',
      name: 'Paradex',
    },
  };

  // Static mapping for Lighter markets based on provided MARKET_INDEX list
  const LIGHTER_MARKETS: string[] = [
    'ETH', // 0
    'BTC', // 1
    'SOL', // 2
    'DOGE', // 3
    '1000PEPE', // 4
    'WIF', // 5
    'WLD', // 6
    'XRP', // 7
    'LINK', // 8
    'AVAX', // 9
    'NEAR', // 10
    'DOT', // 11
    'TON', // 12
    'TAO', // 13
    'POL', // 14
    'TRUMP', // 15
    'SUI', // 16
    '1000SHIB', // 17
    '1000BONK', // 18
    '1000FLOKI', // 19
    'BERA', // 20
    'FARTCOIN', // 21
    'AI16Z', // 22
    'POPCAT', // 23
    'HYPE', // 24
    'BNB', // 25
    'JUP', // 26
    'AAVE', // 27
    'MKR', // 28
    'ENA', // 29
    'UNI', // 30
    'APT', // 31
    'SEI', // 32
    'KAITO', // 33
    'IP', // 34
    'LTC', // 35
    'CRV', // 36
    'PENDLE', // 37
    'ONDO', // 38
    'ADA', // 39
    'S', // 40
    'VIRTUAL', // 41
    'SPX', // 42
    'TRX', // 43
    'SYRUP', // 44
    'PUMP', // 45
    'LDO', // 46
    'PENGU', // 47
    'PAXG', // 48
    'EIGEN', // 49
    'ARB', // 50
    'RESOLV', // 51
    'GRASS', // 52
    'ZORA', // 53
    'LAUNCHCOIN', // 54
    'OP', // 55
    'ZK', // 56
    'PROVE', // 57
    'BCH', // 58
    'HBAR', // 59
    'ZRO', // 60
    'GMX', // 61
    'DYDX', // 62
    'MNT', // 63
    'ETHFI', // 64
    'AERO', // 65
    'USELESS', // 66
    'TIA', // 67
    'MORPHO', // 68
    'VVV', // 69
    'YZY', // 70
    'XPL', // 71
    'WLFI', // 72
    'CRO', // 73
    'NMR', // 74
    'DOLO', // 75
    'LINEA', // 76
    'XMR', // 77
    'PYTH', // 78
    'SKY', // 79
    'MYX', // 80
    '1000TOSHI', // 81
    'AVNT', // 82
    'ASTER', // 83
    '0G', // 84
    'STBL', // 85
    'APEX', // 86
    'FF', // 87
    '2Z', // 88
    'EDEN', // 89
    'ZEC', // 90
    'MON', // 91
    'XAU', // 92
    'XAG', // 93
    'MEGA', // 94
    'MET', // 95
    'EURUSD', // 96
    'GBPUSD', // 97
    'USDJPY', // 98
    'USDCHF', // 99
    'USDCAD', // 100
    'CC', // 101
    'ICP', // 102
    'FIL', // 103
    'STRK', // 104
  ];

interface PriceData {
  exchange: string;
  symbol: string;
  price: string;
  timestamp: number;
  volume?: string;
  bid?: string;
  ask?: string;
  priceChange?: string; // Percentage change, e.g. "+1.23" or "-0.45"
  fundingRate?: string; // Annual funding rate, e.g. "0.0001" (0.01%)
}

// Normalize symbol names across exchanges
// BTC-USD-PERP -> BTC, APT-USD -> APT, ETH -> ETH
const normalizeSymbol = (symbol: string): string => {
  if (!symbol) return '';
  return symbol
    .replace(/-USD-PERP$/i, '')
    .replace(/-PERP$/i, '')
    .replace(/-USD$/i, '')
    .toUpperCase();
};

// Try to robustly extract a numeric volume field from an exchange payload.
// Many exchanges use slightly different key names, so we look for any key
// that contains "vol" (e.g. volume, volume_24h, volumeUsd24h) and pick
// a sensible candidate, preferring 24h-style fields when requested.
const extractVolumeNumber = (source: any, prefer24h = false): number | undefined => {
  if (!source || typeof source !== 'object') return undefined;

  const entries = Object.entries(source) as [string, any][];

  let candidates = entries.filter(([key, value]) => {
    const k = key.toLowerCase();
    if (!k.includes('vol')) return false;
    if (k.includes('change')) return false;
    if (value === null || value === undefined) return false;
    return true;
  });

  if (prefer24h) {
    candidates = candidates.sort((a, b) => {
      const aKey = a[0].toLowerCase();
      const bKey = b[0].toLowerCase();
      const aIs24h = aKey.includes('24h') || aKey.includes('24_h');
      const bIs24h = bKey.includes('24h') || bKey.includes('24_h');
      if (aIs24h === bIs24h) return 0;
      return aIs24h ? -1 : 1;
    });
  }

  for (const [, value] of candidates) {
    const num = parseFloat(String(value));
    if (!Number.isNaN(num) && num > 0) {
      return num;
    }
  }

  return undefined;
};

serve(async (req) => {
  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  const { headers } = req;
  const upgradeHeader = headers.get("upgrade") || "";

  if (upgradeHeader.toLowerCase() !== "websocket") {
    return new Response("Expected WebSocket connection", { status: 400 });
  }

  const { socket, response } = Deno.upgradeWebSocket(req);
  
  // Initialize Supabase client for database operations
  const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
  const supabaseServiceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
  const supabase = createClient(supabaseUrl, supabaseServiceKey);
  
  // Store all exchange WebSocket connections
  const exchangeSockets = new Map<string, WebSocket>();
  const priceCache = new Map<string, PriceData>();
  const previousPrices = new Map<string, number>(); // Track previous prices for % change
  const paradexVolumes = new Map<string, number>(); // Track 24h volume per market for Paradex
  const fundingRates = new Map<string, string>(); // Track funding rates: "exchange_symbol" -> "rate"
  const lastSaveTime = new Map<string, number>(); // Track last save time for rate limiting
  const SAVE_INTERVAL_MS = 10000; // Save to DB only every 10 seconds per symbol
  
  // Function to save price data to database (rate limited)
  const savePriceToDatabase = async (priceData: PriceData) => {
    const key = `${priceData.exchange}_${priceData.symbol}`;
    const now = Date.now();
    const lastSave = lastSaveTime.get(key) || 0;
    
    // Only save if 10 seconds have passed since last save
    if (now - lastSave < SAVE_INTERVAL_MS) {
      return;
    }
    
    lastSaveTime.set(key, now);
    
    try {
      const { error } = await supabase
        .from('crypto_prices')
        .insert({
          exchange: priceData.exchange,
          symbol: priceData.symbol,
          price: parseFloat(priceData.price),
          volume: priceData.volume ? parseFloat(priceData.volume) : null,
          bid: priceData.bid ? parseFloat(priceData.bid) : null,
          ask: priceData.ask ? parseFloat(priceData.ask) : null,
          price_change_24h: priceData.priceChange ? parseFloat(priceData.priceChange) : null,
          funding_rate: priceData.fundingRate ? parseFloat(priceData.fundingRate) : null,
          timestamp: new Date(priceData.timestamp).toISOString(),
        });
      
      if (error) {
        console.error(`Failed to save ${priceData.exchange} ${priceData.symbol}:`, error);
      } else {
        console.log(`✓ Saved ${priceData.exchange} ${priceData.symbol} @ ${priceData.price}`);
      }
    } catch (error) {
      console.error(`Error saving to database:`, error);
    }
  };

  // Fetch markets for exchanges that need them
  const fetchMarkets = async () => {
    const lighterMarkets: Record<string, string> = {};
    LIGHTER_MARKETS.forEach((symbol, index) => {
      lighterMarkets[index.toString()] = symbol;
    });

    console.log(`Lighter: Loaded ${LIGHTER_MARKETS.length} markets`);
    return { lighter: lighterMarkets };
  };

  // Fetch Paradex markets
  const fetchParadexMarkets = async () => {
    try {
      console.log('Paradex: Fetching markets from API...');
      const response = await fetch(EXCHANGES.paradex.marketsUrl);
      
      if (!response.ok) {
        console.error(`Paradex: API returned ${response.status}`);
        return [];
      }
      
      const data = await response.json();
      console.log(`Paradex: API response received, results count: ${data?.results?.length || 0}`);
      
      if (data && data.results && Array.isArray(data.results)) {
        const allMarkets = data.results.map((m: any) => m.symbol);
        console.log(`Paradex: All markets: ${allMarkets.slice(0, 5).join(', ')}... (${allMarkets.length} total)`);
        
        const perpMarkets = data.results
          .filter((m: any) => m.symbol && m.symbol.includes('-PERP'))
          .map((m: any) => m.symbol);
        console.log(`Paradex: Loaded ${perpMarkets.length} PERP markets`);
        return perpMarkets;
      }
      console.error('Paradex: Invalid API response format');
      return [];
    } catch (error) {
      console.error('Paradex: Error fetching markets:', error);
      return [];
    }
  };

  // Fetch funding rates periodically for each exchange
  const fetchLighterFundingRates = async () => {
    try {
      const response = await fetch('https://mainnet.zklighter.elliot.ai/api/v1/funding-rates');
      if (!response.ok) {
        console.error('Lighter: Failed to fetch funding rates', response.status);
        return;
      }
      const data = await response.json();
      if (data.funding_rates && Array.isArray(data.funding_rates)) {
        data.funding_rates.forEach((fr: any) => {
          const symbol = normalizeSymbol(fr.symbol || '');
          if (symbol && fr.rate !== undefined) {
            fundingRates.set(`lighter_${symbol}`, fr.rate.toString());
          }
        });
        console.log(`Lighter: Updated ${data.funding_rates.length} funding rates`);
      }
    } catch (error) {
      console.error('Lighter: Error fetching funding rates', error);
    }
  };

  const fetchParadexFundingData = async () => {
    try {
      const response = await fetch('https://api.prod.paradex.trade/v1/markets');
      if (!response.ok) {
        console.error('Paradex: Failed to fetch markets for funding', response.status);
        return;
      }
      const data = await response.json();
      if (data.results && Array.isArray(data.results)) {
        let count = 0;
        // Log first market to see structure
        if (data.results.length > 0) {
          console.log('Paradex: Sample market data:', JSON.stringify(data.results[0]).substring(0, 500));
        }
        
        data.results.forEach((market: any) => {
          const symbol = normalizeSymbol(market.symbol || '');
          // Try different possible field names for funding rate
          const fundingRate = market.funding_rate || market.fundingRate || market.estimated_funding_rate;
          
          if (symbol && fundingRate !== undefined && fundingRate !== null) {
            fundingRates.set(`paradex_${symbol}`, fundingRate.toString());
            count++;
          }
        });
        console.log(`Paradex: Updated ${count} funding rates from ${data.results.length} markets`);
      }
    } catch (error) {
      console.error('Paradex: Error fetching funding data', error);
    }
  };

  // Extended: Get funding rates from market statistics endpoint
  const fetchExtendedFundingRates = async () => {
    try {
      const response = await fetch('https://api.starknet.extended.exchange/api/v1/info');
      if (!response.ok) {
        console.log('Extended: Failed to fetch market stats', response.status);
        return;
      }
      const data = await response.json();
      if (data.status === 'OK' && data.data && Array.isArray(data.data)) {
        let count = 0;
        // Log first market to see structure
        if (data.data.length > 0) {
          console.log('Extended: Sample market data:', JSON.stringify(data.data[0]).substring(0, 500));
        }
        
        data.data.forEach((market: any) => {
          if (market.marketStats) {
            const symbol = normalizeSymbol(market.market || '');
            const fundingRate = market.marketStats.fundingRate || market.marketStats.funding_rate;
            
            if (symbol && fundingRate !== undefined && fundingRate !== null) {
              fundingRates.set(`extended_${symbol}`, fundingRate.toString());
              count++;
            }
          }
        });
        console.log(`Extended: Updated ${count} funding rates from ${data.data.length} markets`);
      }
    } catch (error) {
      console.error('Extended: Error fetching funding rates', error);
    }
  };

  // Initialize connections to all exchanges
  const initializeExchanges = async () => {
    console.log('=== Initializing exchange connections ===');
    const markets = await fetchMarkets();
    const paradexMarkets = await fetchParadexMarkets();
    console.log(`Markets ready - Lighter: ${Object.keys(markets.lighter).length}, Paradex: ${paradexMarkets.length}`);

    // Lighter WebSocket
    try {
      console.log('Lighter: Attempting connection to', EXCHANGES.lighter.url);
      const lighterWs = new WebSocket(EXCHANGES.lighter.url);
      
      lighterWs.onopen = () => {
        console.log('Lighter: ✓ Connected to WebSocket');
        
        // Subscribe to individual market channels
        const marketIds = Object.keys(markets.lighter);
        console.log(`Lighter: Subscribing to ${marketIds.length} markets...`);
        marketIds.forEach(marketId => {
          lighterWs.send(JSON.stringify({
            type: 'subscribe',
            channel: `market_stats/${marketId}`
          }));
        });
        console.log(`Lighter: ✓ Subscribed to ${marketIds.length} markets`);
      };

      lighterWs.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'update/market_stats' && data.market_stats) {
            const stats = data.market_stats;
            const marketIdRaw = stats.market_id;
            const marketId = String(marketIdRaw);
            const symbol = markets.lighter[marketId];
            
            if (!symbol) {
              console.log('Lighter: Unknown marketId', marketIdRaw);
              return;
            }

            const price = parseFloat(stats.last_trade_price || stats.mark_price || 0);
            if (!price || price <= 0) return;

            // Normalize symbol (BTC stays BTC, etc.)
            const normalizedSymbol = normalizeSymbol(symbol);

            // Calculate price change %
            const cacheKey = `lighter_${normalizedSymbol}`;
            const prevPrice = previousPrices.get(cacheKey);
            let priceChange: string | undefined;
            if (prevPrice && prevPrice > 0) {
              const change = ((price - prevPrice) / prevPrice) * 100;
              priceChange = change >= 0 ? `+${change.toFixed(2)}` : change.toFixed(2);
            }
            previousPrices.set(cacheKey, price);

            // Try multiple possible volume fields
            // Lighter returns volume in base asset tokens, not USD
            const volumeTokens = extractVolumeNumber(stats, true);
            const volumeUsd = volumeTokens !== undefined && !Number.isNaN(volumeTokens)
              ? volumeTokens * price
              : undefined;

            const priceData: PriceData = {
              exchange: 'Lighter',
              symbol: normalizedSymbol,
              price: price.toString(),
              timestamp: Date.now(),
              volume:
                volumeUsd !== undefined && !Number.isNaN(volumeUsd)
                  ? volumeUsd.toString()
                  : undefined,
              priceChange,
              fundingRate: fundingRates.get(`lighter_${normalizedSymbol}`),
            };
            
            console.log('Lighter: Tick', { marketId, symbol: normalizedSymbol, price, volumeTokens, volumeUsd });

            const key = `lighter_${normalizedSymbol}`;
            priceCache.set(key, priceData);
            
            // Save to database
            savePriceToDatabase(priceData);
            
            if (socket.readyState === WebSocket.OPEN) {
              socket.send(JSON.stringify(priceData));
            }
          }
        } catch (error) {
          console.error('Lighter: Parse error', error);
        }
      };

      lighterWs.onerror = (error) => {
        console.error('Lighter: WebSocket error -', error);
      };

      lighterWs.onclose = (event) => {
        console.log('Lighter: Disconnected, code:', event.code, 'reason:', event.reason, '- reconnecting in 5s...');
        exchangeSockets.delete('lighter');
        setTimeout(() => initializeExchanges(), 5000);
      };

      exchangeSockets.set('lighter', lighterWs);
    } catch (error) {
      console.error('Lighter: Connection failed', error);
    }

    // Extended WebSocket - Price Stream
    try {
      console.log('Extended: Attempting connection to', EXCHANGES.extended.priceUrl);
      const extendedWs = new WebSocket(EXCHANGES.extended.priceUrl);
      
      extendedWs.onopen = () => {
        console.log('Extended: ✓ Connected to price stream');
      };

      extendedWs.onmessage = (event) => {
        try {
          const rawData = event.data;
          
          // Extended may send newline-delimited JSON
          const lines = rawData.toString().split('\n');
          
          for (const line of lines) {
            if (!line.trim()) continue;
            
            const data = JSON.parse(line);
            
            // Handle both 'MP' (mark price) and 'P' (price) message types
            if ((data.type === 'MP' || data.type === 'P') && data.data) {
              const market = data.data.m || data.data.market;
              const price = parseFloat(data.data.p || data.data.price || data.data.mark_price || 0);
              
              // Extended may return volume in base asset tokens or not at all
              const volumeTokens = extractVolumeNumber(data.data, true);
              const volumeUsd = volumeTokens !== undefined && !Number.isNaN(volumeTokens)
                ? volumeTokens * price
                : undefined;
              
              if (!market || !price || price <= 0) continue;

              // Normalize symbol (APT-USD -> APT, BTC-USD -> BTC)
              const normalizedSymbol = normalizeSymbol(market);

              // Calculate price change %
              const cacheKey = `extended_${normalizedSymbol}`;
              const prevPrice = previousPrices.get(cacheKey);
              let priceChange: string | undefined;
              if (prevPrice && prevPrice > 0) {
                const change = ((price - prevPrice) / prevPrice) * 100;
                priceChange = change >= 0 ? `+${change.toFixed(2)}` : change.toFixed(2);
              }
              previousPrices.set(cacheKey, price);

              const priceData: PriceData = {
                exchange: 'Extended',
                symbol: normalizedSymbol,
                price: price.toString(),
                timestamp: Date.now(),
                volume:
                  volumeUsd !== undefined && !Number.isNaN(volumeUsd)
                    ? volumeUsd.toString()
                    : undefined,
                priceChange,
                fundingRate: fundingRates.get(`extended_${normalizedSymbol}`),
              };
              
              console.log('Extended: Tick', { market: normalizedSymbol, price, volumeTokens, volumeUsd });
              
              const key = `extended_${normalizedSymbol}`;
              priceCache.set(key, priceData);
              
              // Save to database
              savePriceToDatabase(priceData);
              
              if (socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify(priceData));
              }
            }
          }
        } catch (error) {
          console.error('Extended: Parse error', error, 'Data sample:', event.data?.toString()?.substring(0, 100));
        }
      };

      extendedWs.onerror = (error) => {
        console.error('Extended: WebSocket error', error);
      };

      extendedWs.onclose = (event) => {
        console.log('Extended: Disconnected', event.code, event.reason, '- reconnecting in 5s...');
        exchangeSockets.delete('extended');
        setTimeout(() => initializeExchanges(), 5000);
      };

      exchangeSockets.set('extended', extendedWs);
    } catch (error) {
      console.error('Extended: Connection failed', error);
    }

    // Paradex WebSocket
    try {
      console.log('Paradex: Attempting connection to', EXCHANGES.paradex.url);
      const paradexWs = new WebSocket(EXCHANGES.paradex.url);
      
      paradexWs.onopen = () => {
        console.log('Paradex: ✓ Connected to WebSocket');
        
        // Subscribe to markets summary
        const summaryMsg = {
          jsonrpc: '2.0',
          method: 'subscribe',
          params: { channel: 'markets_summary' },
          id: 1
        };
        console.log('Paradex: Subscribing to markets_summary...');
        paradexWs.send(JSON.stringify(summaryMsg));

        // Subscribe to individual market trades
        console.log(`Paradex: Subscribing to ${paradexMarkets.length} individual markets...`);
        paradexMarkets.forEach((market: string, index: number) => {
          const channel = `trades.${market}`;
          const msg = {
            jsonrpc: '2.0',
            method: 'subscribe',
            params: { channel },
            id: index + 2,
          };
          console.log('Paradex: Sending trades subscription', msg);
          paradexWs.send(JSON.stringify(msg));
        });
        
        console.log(`Paradex: ✓ Subscriptions sent for ${paradexMarkets.length} markets`);
      };

      paradexWs.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          // Log subscription confirmations and pings
          if (data.result === 'subscribed') {
            console.log(`Paradex: Subscription confirmed for ID ${data.id}`);
            return;
          }
          if (data.method === 'ping') {
            console.log('Paradex: ping');
            return;
          }
          
          if (data.params && data.params.data) {
            const marketData = data.params.data;
            const channel = data.params.channel as string;
            
            let symbol = '';
            let price = 0;
            let volumeValue: number | undefined;
            
            if (channel && channel.startsWith('trades.')) {
              symbol = channel.replace('trades.', '');
              price = parseFloat(marketData.price || marketData.p || 0);

              // For trade ticks, reuse the last known 24h volume from markets_summary
              const volKey = normalizeSymbol(symbol);
              const cachedVolume = paradexVolumes.get(volKey);
              if (cachedVolume !== undefined) {
                volumeValue = cachedVolume;
              }
            } else if (channel === 'markets_summary') {
              symbol = marketData.market || marketData.symbol;
              price = parseFloat(marketData.mark_price || marketData.last_price || 0);

              // Extract a stable 24h-style volume from the summary payload
              const volKey = normalizeSymbol(symbol);
              const summaryVolume = extractVolumeNumber(marketData, true);
              if (summaryVolume !== undefined) {
                paradexVolumes.set(volKey, summaryVolume);
                volumeValue = summaryVolume;
              } else {
                const cachedVolume = paradexVolumes.get(volKey);
                if (cachedVolume !== undefined) {
                  volumeValue = cachedVolume;
                }
              }
            }
            
            if (!symbol || !price || price <= 0) {
              return;
            }

            // Normalize symbol (BTC-USD-PERP -> BTC)
            const normalizedSymbol = normalizeSymbol(symbol);

            // If we still don't have a volume, fall back to any cached value
            if (volumeValue === undefined) {
              const cachedVolume = paradexVolumes.get(normalizedSymbol);
              if (cachedVolume !== undefined) {
                volumeValue = cachedVolume;
              }
            }

            // Calculate price change %
            const cacheKey = `paradex_${normalizedSymbol}`;
            const prevPrice = previousPrices.get(cacheKey);
            let priceChange: string | undefined;
            if (prevPrice && prevPrice > 0) {
              const change = ((price - prevPrice) / prevPrice) * 100;
              priceChange = change >= 0 ? `+${change.toFixed(2)}` : change.toFixed(2);
            }
            previousPrices.set(cacheKey, price);

            const priceData: PriceData = {
              exchange: 'Paradex',
              symbol: normalizedSymbol,
              price: price.toString(),
              timestamp: Date.now(),
              volume:
                volumeValue !== undefined && !Number.isNaN(volumeValue)
                  ? volumeValue.toString()
                  : undefined,
              priceChange,
              fundingRate: fundingRates.get(`paradex_${normalizedSymbol}`),
            };
            
            console.log('Paradex: Tick', { symbol: normalizedSymbol, price, channel, volume: volumeValue });
            
            const key = `paradex_${normalizedSymbol}`;
            priceCache.set(key, priceData);
            
            // Save to database
            savePriceToDatabase(priceData);
            
            if (socket.readyState === WebSocket.OPEN) {
              socket.send(JSON.stringify(priceData));
            }
          } else {
            console.log('Paradex: Unhandled message', data);
          }
        } catch (error) {
          console.error('Paradex: Parse error', error, 'Data:', event.data?.substring(0, 200));
        }
      };

      paradexWs.onerror = (error) => {
        console.error('Paradex: WebSocket error', error);
      };

      paradexWs.onclose = (event) => {
        console.log('Paradex: Disconnected', event.code, event.reason, '- reconnecting in 5s...');
        exchangeSockets.delete('paradex');
        setTimeout(() => initializeExchanges(), 5000);
      };

      exchangeSockets.set('paradex', paradexWs);
    } catch (error) {
      console.error('Paradex: Connection failed', error);
    }
  };

  socket.onopen = () => {
    console.log('Client connected');
    initializeExchanges();
    
    // Fetch funding rates immediately and periodically
    fetchLighterFundingRates();
    fetchParadexFundingData();
    fetchExtendedFundingRates();
    
    const fundingInterval = setInterval(() => {
      fetchLighterFundingRates();
      fetchParadexFundingData();
      fetchExtendedFundingRates();
    }, 60000); // Update every 60 seconds
    
    // Send initial cache to client
    setTimeout(() => {
      if (socket.readyState === WebSocket.OPEN) {
        priceCache.forEach((data) => {
          socket.send(JSON.stringify(data));
        });
      }
    }, 2000);
    
    // Cleanup on close
    socket.addEventListener('close', () => {
      clearInterval(fundingInterval);
    });
  };

  socket.onclose = () => {
    console.log('Client disconnected, closing exchange connections');
    exchangeSockets.forEach((ws) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    });
  };

  socket.onerror = (error) => {
    console.error('Client WebSocket error:', error);
  };

  return response;
});
