import React, { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Activity, ArrowUpDown, ArrowUp, ArrowDown, TrendingUp, BarChart3, Filter } from "lucide-react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import { fetchLighterMarkets, getExtendedMarketSymbol } from "@/components/markets/MarketRegistry";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { base44 } from "@/api/base44Client";

export default function LiveMarkets() {
  const [marketsData, setMarketsData] = useState({});
  const [athAtl, setAthAtl] = useState({});
  const [connections, setConnections] = useState({
    lighter: false,
    extended: false,
    paradex: false
  });
  const [isRecording, setIsRecording] = useState(false);
  const [logs, setLogs] = useState([]);
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'desc' });
  const [exchangeFilter, setExchangeFilter] = useState('all');
  const [lighterMarkets, setLighterMarkets] = useState({});
  const wsRefs = useRef({});
  const volumeTracking = useRef({});
  const connectionAttempts = useRef({ lighter: 0, extended: 0, paradex: 0 });
  const healthCheck = useRef(null);
  const saveCount = useRef(0);
  const lastSaveTime = useRef(0);
  const batchBuffer = useRef([]);

  const addLog = (exchange, message) => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs(prev => [`[${timestamp}] [${exchange}] ${message}`, ...prev].slice(0, 100));
    console.log(`[${exchange}] ${message}`);
  };

  // Batch save every 5 seconds
  useEffect(() => {
    const interval = setInterval(async () => {
      const bufferSize = batchBuffer.current.length;
      addLog('💾 Buffer', `Size: ${bufferSize} records`);
      
      if (bufferSize > 0) {
        const toSave = [...batchBuffer.current];
        batchBuffer.current = [];
        
        try {
          console.log('💾 Saving batch:', toSave.length, 'records');
          console.log('Sample:', JSON.stringify(toSave[0]));
          
          // Try bulkCreate first (faster)
          try {
            const result = await base44.entities.BacktestingData.bulkCreate(toSave);
            saveCount.current += toSave.length;
            lastSaveTime.current = Date.now();
            setIsRecording(true);
            addLog('✅ DB Bulk', `Saved ${toSave.length} records`);
            console.log('✅ Bulk save successful:', toSave.length);
          } catch (bulkErr) {
            addLog('❌ Bulk Failed', bulkErr.message);
            console.error('Bulk save failed:', bulkErr);
            
            // Fallback to individual saves
            let successCount = 0;
            let failedCount = 0;
            for (const record of toSave) {
              try {
                await base44.entities.BacktestingData.create(record);
                successCount++;
              } catch (recordErr) {
                failedCount++;
                if (failedCount <= 3) {
                  console.error('❌ Failed record:', {
                    market: record.market,
                    exchange: record.exchange,
                    error: recordErr.message || recordErr
                  });
                  addLog('❌ Record', `${record.market}-${record.exchange}: ${recordErr.message}`);
                }
              }
            }
            
            if (successCount > 0) {
              saveCount.current += successCount;
              lastSaveTime.current = Date.now();
              setIsRecording(true);
              addLog('✅ Individual', `${successCount}/${toSave.length} saved, ${failedCount} failed`);
            } else {
              addLog('❌ All Failed', `${failedCount} records failed`);
            }
          }
        } catch (err) {
          console.error('Batch error:', err);
          addLog('❌ DB', `Failed: ${err.message}`);
        }
      } else {
        addLog('⏸️  Buffer', 'Empty - no data to save');
      }
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      const timeSinceLastSave = Date.now() - lastSaveTime.current;
      if (timeSinceLastSave > 3000) {
        setIsRecording(false);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  const addToBatch = (symbol, exchange, price, marketId = null) => {
    const record = {
      timestamp: new Date().toISOString(),
      market: symbol,
      market_id: marketId || 0,
      mark_price: parseFloat(price),
      exchange: exchange === 'lighter' ? 'Lighter' : exchange === 'extended' ? 'Extended' : 'Paradex'
    };
    batchBuffer.current.push(record);
    if (batchBuffer.current.length % 50 === 0) {
      console.log('📦 Buffer size:', batchBuffer.current.length);
    }
  };

  const updateAthAtl = (symbol, exchange, price) => {
    setAthAtl(prev => {
      const key = `${symbol}_${exchange}`;
      const current = prev[key] || { ath: price, atl: price };
      return {
        ...prev,
        [key]: {
          ath: Math.max(current.ath, price),
          atl: Math.min(current.atl, price)
        }
      };
    });
  };

  useEffect(() => {
    const loadMarkets = async () => {
      addLog('Lighter', '📡 Loading markets from API...');
      const markets = await fetchLighterMarkets();
      setLighterMarkets(markets);
      addLog('Lighter', `✅ Loaded ${Object.keys(markets).length} markets`);
    };
    loadMarkets();
  }, []);

  useEffect(() => {
    healthCheck.current = setInterval(() => {
      if (!connections.lighter && wsRefs.current.lighter) {
        addLog('Lighter', '🔄 Auto-reconnect triggered');
        wsRefs.current.lighter.close();
      }
      
      if (!connections.extended && wsRefs.current.extendedPrice) {
        addLog('Extended', '🔄 Auto-reconnect triggered');
        wsRefs.current.extendedPrice.close();
      }
      
      if (!connections.paradex && wsRefs.current.paradex) {
        addLog('Paradex', '🔄 Auto-reconnect triggered');
        wsRefs.current.paradex.close();
      }
    }, 15000);

    return () => {
      if (healthCheck.current) clearInterval(healthCheck.current);
    };
  }, [connections]);

  // Lighter WebSocket
  useEffect(() => {
    if (Object.keys(lighterMarkets).length === 0) return;

    let reconnectTimeout;
    let ws;

    const connect = () => {
      try {
        connectionAttempts.current.lighter++;
        addLog('Lighter', `🔌 Connecting... (attempt ${connectionAttempts.current.lighter})`);
        
        ws = new WebSocket('wss://mainnet.zklighter.elliot.ai/stream');
        wsRefs.current.lighter = ws;

        ws.onopen = () => {
          addLog('Lighter', '✅ Connected');
          setConnections(prev => ({ ...prev, lighter: true }));
          connectionAttempts.current.lighter = 0;
          
          const marketIds = Object.keys(lighterMarkets);
          marketIds.forEach(marketId => {
            ws.send(JSON.stringify({
              type: 'subscribe',
              channel: `market_stats/${marketId}`
            }));
          });
          addLog('Lighter', `📡 Subscribed to ${marketIds.length} markets`);
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            
            if (data.type === 'update/market_stats' && data.market_stats) {
              const stats = data.market_stats;
              const marketId = stats.market_id;
              const symbol = lighterMarkets[marketId];
              
              if (!symbol) return;

              const price = parseFloat(stats.last_trade_price || stats.mark_price || 0);
              const volume = parseFloat(stats.daily_quote_token_volume || 0);

              if (price > 0) {
                updateAthAtl(symbol, 'lighter', price);
                addToBatch(symbol, 'lighter', price, marketId);
                
                setMarketsData(prev => ({
                  ...prev,
                  [symbol]: {
                    ...prev[symbol],
                    lighter: { price, volume, timestamp: Date.now(), marketId }
                  }
                }));
              }
            }
          } catch (err) {}
        };

        ws.onerror = () => {
          addLog('Lighter', `❌ Error`);
          setConnections(prev => ({ ...prev, lighter: false }));
        };
        
        ws.onclose = () => {
          addLog('Lighter', '🔌 Closed, reconnecting in 5s');
          setConnections(prev => ({ ...prev, lighter: false }));
          reconnectTimeout = setTimeout(connect, 5000);
        };
      } catch (err) {
        addLog('Lighter', `❌ Failed: ${err.message}`);
        reconnectTimeout = setTimeout(connect, 5000);
      }
    };

    connect();

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, [lighterMarkets]);

  // Extended WebSocket - Price Stream
  useEffect(() => {
    let reconnectTimeout;
    let ws;

    const connect = () => {
      try {
        addLog('Extended', '🔌 Connecting to price stream...');
        ws = new WebSocket('wss://api.starknet.extended.exchange/stream.extended.exchange/v1/prices/mark');
        wsRefs.current.extendedPrice = ws;

        ws.onopen = () => {
          addLog('Extended', '✅ Price stream connected');
          setConnections(prev => ({ ...prev, extended: true }));
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            
            if (data.type === 'MP' && data.data) {
              const market = data.data.m;
              const price = parseFloat(data.data.p || 0);
              
              if (!market || price <= 0) return;
              
              const symbol = getExtendedMarketSymbol(market);
              updateAthAtl(symbol, 'extended', price);
              addToBatch(symbol, 'extended', price);
              
              setMarketsData(prev => ({
                ...prev,
                [symbol]: {
                  ...prev[symbol],
                  extended: { 
                    price, 
                    volume: prev[symbol]?.extended?.volume || 0,
                    timestamp: Date.now() 
                  }
                }
              }));
            }
          } catch (err) {
            addLog('Extended', `❌ Parse error: ${err.message}`);
          }
        };

        ws.onerror = () => {
          addLog('Extended', `❌ Error`);
          setConnections(prev => ({ ...prev, extended: false }));
        };
        
        ws.onclose = () => {
          addLog('Extended', '🔌 Closed, reconnecting');
          setConnections(prev => ({ ...prev, extended: false }));
          reconnectTimeout = setTimeout(connect, 5000);
        };
      } catch (err) {
        addLog('Extended', `❌ Failed: ${err.message}`);
        reconnectTimeout = setTimeout(connect, 5000);
      }
    };

    connect();

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, []);

  // Extended WebSocket - Trade Stream for Volume
  useEffect(() => {
    let reconnectTimeout;
    let ws;

    const connect = () => {
      try {
        ws = new WebSocket('wss://api.starknet.extended.exchange/stream.extended.exchange/v1/trades');
        wsRefs.current.extendedTrade = ws;

        ws.onopen = () => {
          addLog('Extended', '✅ Trade stream connected');
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            
            if (data.type === 'T' && data.data) {
              const market = data.data.m;
              const tradeVolume = parseFloat(data.data.q || 0) * parseFloat(data.data.p || 0);
              
              if (!market || tradeVolume <= 0) return;
              
              const symbol = getExtendedMarketSymbol(market);
              
              if (!volumeTracking.current[symbol]) {
                volumeTracking.current[symbol] = [];
              }
              
              const now = Date.now();
              const oneDayAgo = now - 24 * 60 * 60 * 1000;
              
              volumeTracking.current[symbol].push({ volume: tradeVolume, timestamp: now });
              volumeTracking.current[symbol] = volumeTracking.current[symbol].filter(t => t.timestamp > oneDayAgo);
              
              const volume24h = volumeTracking.current[symbol].reduce((sum, t) => sum + t.volume, 0);
              
              setMarketsData(prev => ({
                ...prev,
                [symbol]: {
                  ...prev[symbol],
                  extended: { 
                    price: prev[symbol]?.extended?.price || 0,
                    volume: volume24h,
                    timestamp: Date.now() 
                  }
                }
              }));
            }
          } catch (err) {}
        };

        ws.onerror = () => {
          addLog('Extended', `❌ Trade stream error`);
        };
        
        ws.onclose = () => {
          reconnectTimeout = setTimeout(connect, 5000);
        };
      } catch (err) {
        reconnectTimeout = setTimeout(connect, 5000);
      }
    };

    connect();

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, []);

  // Paradex WebSocket
  useEffect(() => {
    let reconnectTimeout;
    let ws;
    let paradexMarkets = [];

    const fetchMarkets = async () => {
      try {
        addLog('Paradex', '📡 Fetching markets...');
        const response = await fetch('https://api.prod.paradex.trade/v1/markets');
        const data = await response.json();
        
        if (data && data.results && Array.isArray(data.results)) {
          paradexMarkets = data.results
            .filter(m => m.symbol && m.symbol.includes('-PERP'))
            .map(m => m.symbol);
          addLog('Paradex', `✅ Found ${paradexMarkets.length} markets`);
          connect();
        }
      } catch (err) {
        addLog('Paradex', `❌ Market fetch failed: ${err.message}`);
      }
    };

    const connect = () => {
      if (paradexMarkets.length === 0) return;
      
      try {
        addLog('Paradex', '🔌 Connecting...');
        ws = new WebSocket('wss://ws.api.prod.paradex.trade/v1');
        wsRefs.current.paradex = ws;

        ws.onopen = () => {
          addLog('Paradex', '✅ Connected');
          setConnections(prev => ({ ...prev, paradex: true }));

          paradexMarkets.forEach((market, idx) => {
            ws.send(JSON.stringify({
              jsonrpc: '2.0',
              method: 'subscribe',
              params: {
                channel: 'markets_summary',
                market
              },
              id: idx + 1
            }));
          });
          addLog('Paradex', `📡 Subscribed to ${paradexMarkets.length} markets`);
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            
            if (data.params?.channel === 'markets_summary' && data.params?.data) {
              const marketData = data.params.data;
              
              if (!marketData.symbol || !marketData.symbol.includes('-PERP')) return;
              
              const symbol = marketData.symbol.split('-')[0];

              let price = 0;
              if (marketData.oracle_price) {
                price = parseFloat(marketData.oracle_price);
              } else if (marketData.mark_price) {
                price = parseFloat(marketData.mark_price);
              } else if (marketData.last_trade_price) {
                price = parseFloat(marketData.last_trade_price);
              }

              if (price === 0) return;

              updateAthAtl(symbol, 'paradex', price);
              addToBatch(symbol, 'paradex', price);
              
              const volume = parseFloat(marketData.volume_24h || 0);

              setMarketsData(prev => ({
                ...prev,
                [symbol]: {
                  ...prev[symbol],
                  paradex: { price, volume, timestamp: Date.now() }
                }
              }));
            }
          } catch (err) {}
        };

        ws.onerror = () => {
          addLog('Paradex', `❌ Error`);
          setConnections(prev => ({ ...prev, paradex: false }));
        };
        
        ws.onclose = () => {
          addLog('Paradex', '🔌 Closed, reconnecting');
          setConnections(prev => ({ ...prev, paradex: false }));
          reconnectTimeout = setTimeout(connect, 5000);
        };
      } catch (err) {
        addLog('Paradex', `❌ Failed: ${err.message}`);
        reconnectTimeout = setTimeout(connect, 5000);
      }
    };

    fetchMarkets();

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, []);
  
  const filteredMarkets = Object.keys(marketsData).filter(symbol => {
    const data = marketsData[symbol];
    const exchangeCount = [
      data.lighter?.price,
      data.extended?.price,
      data.paradex?.price
    ].filter(Boolean).length;

    if (exchangeFilter === 'all') return true;
    if (exchangeFilter === '3') return exchangeCount === 3;
    if (exchangeFilter === '2+') return exchangeCount >= 2;
    if (exchangeFilter === '2') return exchangeCount === 2;
    if (exchangeFilter === '1') return exchangeCount === 1;
    return true;
  });

  const sortedMarkets = [...filteredMarkets].sort((a, b) => {
    const dataA = marketsData[a];
    const dataB = marketsData[b];

    let valueA = 0;
    let valueB = 0;

    if (!sortConfig.key) {
      const volumeA = (dataA.lighter?.volume || 0) + (dataA.extended?.volume || 0) + (dataA.paradex?.volume || 0);
      const volumeB = (dataB.lighter?.volume || 0) + (dataB.extended?.volume || 0) + (dataB.paradex?.volume || 0);
      return volumeB - volumeA;
    }

    if (sortConfig.key === 'market') {
      return sortConfig.direction === 'desc' ? b.localeCompare(a) : a.localeCompare(b);
    } else if (sortConfig.key === 'l_price') {
      valueA = dataA.lighter?.price || 0;
      valueB = dataB.lighter?.price || 0;
    } else if (sortConfig.key === 'l_vol') {
      valueA = dataA.lighter?.volume || 0;
      valueB = dataB.lighter?.volume || 0;
    } else if (sortConfig.key === 'e_price') {
      valueA = dataA.extended?.price || 0;
      valueB = dataB.extended?.price || 0;
    } else if (sortConfig.key === 'e_vol') {
      valueA = dataA.extended?.volume || 0;
      valueB = dataB.extended?.volume || 0;
    } else if (sortConfig.key === 'p_price') {
      valueA = dataA.paradex?.price || 0;
      valueB = dataB.paradex?.price || 0;
    } else if (sortConfig.key === 'p_vol') {
      valueA = dataA.paradex?.volume || 0;
      valueB = dataB.paradex?.volume || 0;
    }

    return sortConfig.direction === 'desc' ? valueB - valueA : valueA - valueB;
  });

  const globalStats = {
    lighterVolume: 0,
    extendedVolume: 0,
    paradexVolume: 0,
    lighterMarkets: 0,
    extendedMarkets: 0,
    paradexMarkets: 0,
    totalMarkets: sortedMarkets.length,
    avgSpread: 0
  };

  let spreadSum = 0;
  let spreadCount = 0;

  sortedMarkets.forEach(symbol => {
    const data = marketsData[symbol];
    if (data.lighter && data.lighter.volume) {
      globalStats.lighterVolume += data.lighter.volume;
      globalStats.lighterMarkets++;
    }
    if (data.extended && data.extended.volume) {
      globalStats.extendedVolume += data.extended.volume;
      globalStats.extendedMarkets++;
    }
    if (data.paradex && data.paradex.volume) {
      globalStats.paradexVolume += data.paradex.volume;
      globalStats.paradexMarkets++;
    }

    const prices = [data.lighter?.price, data.extended?.price, data.paradex?.price].filter(Boolean);
    if (prices.length > 1) {
      const spread = (Math.max(...prices) - Math.min(...prices)) / Math.min(...prices) * 100;
      spreadSum += spread;
      spreadCount++;
    }
  });

  globalStats.avgSpread = spreadCount > 0 ? spreadSum / spreadCount : 0;

  const SortableHeader = ({ field, label }) => {
    const isActive = sortConfig.key === field;
    const Icon = isActive ? (sortConfig.direction === 'desc' ? ArrowDown : ArrowUp) : ArrowUpDown;
    
    return (
      <button
        onClick={() => handleSort(field)}
        className="font-bold text-xs text-center w-full hover:text-white transition-colors flex items-center justify-center gap-1"
      >
        {label}
        <Icon className="w-3 h-3" />
      </button>
    );
  };

  const handleSort = (field) => {
    setSortConfig(prev => ({
      key: field,
      direction: prev.key === field && prev.direction === 'desc' ? 'asc' : 'desc'
    }));
  };

  return (
    <div className="min-h-screen bg-[#0a0e27] p-4">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <Link to={createPageUrl("Dashboard")}>
            <Button variant="outline" size="icon" className="h-8 w-8 border-slate-600 hover:bg-slate-800 text-white">
              <ArrowLeft className="w-3 h-3" />
            </Button>
          </Link>
          <div className="flex-1">
            <h1 className="text-2xl font-bold text-white">Live Markets</h1>
            <p className="text-xs text-slate-400">
              Lighter ({Object.keys(lighterMarkets).length}), Extended, Paradex - {sortedMarkets.length} aktywnych
            </p>
          </div>
          <div className="flex gap-2 items-center">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-800 rounded-lg border border-slate-600">
              <div className={`w-2 h-2 rounded-full ${isRecording ? 'bg-red-500 animate-pulse' : 'bg-gray-500'}`}></div>
              <span className="text-xs text-white font-medium">
                {isRecording ? 'SAVING' : 'IDLE'}
              </span>
              <span className="text-xs text-slate-400">
                {saveCount.current} saved | {batchBuffer.current.length} pending
              </span>
            </div>
            <Badge className={`text-xs ${connections.lighter ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}`}>
              L {connections.lighter && '✓'}
            </Badge>
            <Badge className={`text-xs ${connections.extended ? 'bg-blue-500/20 text-blue-400' : 'bg-gray-500/20 text-gray-400'}`}>
              E {connections.extended && '✓'}
            </Badge>
            <Badge className={`text-xs ${connections.paradex ? 'bg-purple-500/20 text-purple-400' : 'bg-gray-500/20 text-gray-400'}`}>
              P {connections.paradex && '✓'}
            </Badge>
          </div>
        </div>

        <Card className="bg-gradient-to-br from-slate-900 to-slate-800 border-slate-700 mb-4">
          <CardHeader className="pb-2">
            <CardTitle className="text-white text-xs">Logi Połączeń i Błędów (Batch Insert co 5s)</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="bg-slate-950 rounded p-1.5 font-mono text-[8px] max-h-[200px] overflow-y-auto">
              {logs.length === 0 ? (
                <p className="text-slate-500">Oczekiwanie...</p>
              ) : (
                logs.map((log, i) => (
                  <div 
                    key={i} 
                    className={`mb-0.5 leading-tight ${
                      log.includes('❌') ? 'text-red-400' : 
                      log.includes('✅') ? 'text-green-400' : 
                      log.includes('⚠️') ? 'text-yellow-400' :
                      log.includes('💾') ? 'text-blue-400' :
                      'text-slate-300'
                    }`}
                  >
                    {log}
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-slate-900 to-slate-800 border-slate-700 mb-4">
          <CardHeader className="pb-2">
            <CardTitle className="text-white text-sm flex items-center gap-2">
              <BarChart3 className="w-4 h-4" />
              Statystyki Globalne
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-2 bg-slate-800/50 rounded border border-green-500/30">
                <div className="text-[10px] text-green-400 mb-1">Lighter Volume</div>
                <div className="text-sm font-bold text-white">${(globalStats.lighterVolume / 1000000).toFixed(1)}M</div>
                <div className="text-[9px] text-slate-400">{globalStats.lighterMarkets} markets</div>
              </div>
              <div className="p-2 bg-slate-800/50 rounded border border-blue-500/30">
                <div className="text-[10px] text-blue-400 mb-1">Extended Volume</div>
                <div className="text-sm font-bold text-white">${(globalStats.extendedVolume / 1000000).toFixed(1)}M</div>
                <div className="text-[9px] text-slate-400">{globalStats.extendedMarkets} markets</div>
              </div>
              <div className="p-2 bg-slate-800/50 rounded border border-purple-500/30">
                <div className="text-[10px] text-purple-400 mb-1">Paradex Volume</div>
                <div className="text-sm font-bold text-white">${(globalStats.paradexVolume / 1000000).toFixed(1)}M</div>
                <div className="text-[9px] text-slate-400">{globalStats.paradexMarkets} markets</div>
              </div>
              <div className="p-2 bg-slate-800/50 rounded border border-yellow-500/30">
                <div className="text-[10px] text-yellow-400 mb-1">Średni Spread</div>
                <div className="text-sm font-bold text-white">{globalStats.avgSpread.toFixed(3)}%</div>
                <div className="text-[9px] text-slate-400">cross-exchange</div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-slate-900 to-slate-800 border-slate-700">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between mb-3">
              <CardTitle className="text-white flex items-center gap-2 text-base">
                <Activity className="w-4 h-4" />
                Porównanie Giełd
              </CardTitle>
            </div>
            <div className="flex flex-wrap gap-2 items-center">
              <div className="flex items-center gap-2 ml-auto">
                <Filter className="w-3 h-3 text-slate-400" />
                <Select value={exchangeFilter} onValueChange={setExchangeFilter}>
                  <SelectTrigger className="h-8 w-[140px] bg-slate-800 border-slate-600 text-xs">
                    <SelectValue placeholder="Filter Markets" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Wszystkie</SelectItem>
                    <SelectItem value="3">3 giełdy</SelectItem>
                    <SelectItem value="2+">2+ giełdy</SelectItem>
                    <SelectItem value="2">2 giełdy</SelectItem>
                    <SelectItem value="1">1 giełda</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            {sortedMarkets.length === 0 ? (
              <div className="text-center py-8 text-slate-400">
                <Activity className="w-10 h-10 mx-auto mb-2 opacity-50 animate-pulse" />
                <p className="text-sm">Ładowanie danych...</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <div className="min-w-[1000px]">
                  <div className="grid grid-cols-[100px_repeat(9,1fr)] gap-1 p-2 bg-slate-800/70 rounded-t border-b border-slate-600 mb-1">
                    <SortableHeader field="market" label="Market" />
                    <div className="text-green-400"><SortableHeader field="l_price" label="L Price" /></div>
                    <div className="text-green-400"><SortableHeader field="l_vol" label="L Vol" /></div>
                    <div className="font-bold text-green-400 text-xs text-center">L %</div>
                    <div className="text-blue-400"><SortableHeader field="e_price" label="E Price" /></div>
                    <div className="text-blue-400"><SortableHeader field="e_vol" label="E Vol" /></div>
                    <div className="font-bold text-blue-400 text-xs text-center">E %</div>
                    <div className="text-purple-400"><SortableHeader field="p_price" label="P Price" /></div>
                    <div className="text-purple-400"><SortableHeader field="p_vol" label="P Vol" /></div>
                    <div className="font-bold text-purple-400 text-xs text-center">P %</div>
                  </div>

                  <div className="space-y-1 max-h-[400px] overflow-y-auto pr-2">
                    {sortedMarkets.map(symbol => {
                      const data = marketsData[symbol] || {};
                      const prices = [
                        data.lighter?.price,
                        data.extended?.price,
                        data.paradex?.price
                      ].filter(Boolean);
                      
                      const avgPrice = prices.length > 0 
                        ? prices.reduce((a, b) => a + b, 0) / prices.length 
                        : 0;

                      return (
                        <div key={symbol} className="grid grid-cols-[100px_repeat(9,1fr)] gap-1 p-2 bg-slate-800/50 rounded border border-slate-700 hover:border-slate-600 transition-colors items-center">
                          <div className="font-bold text-white text-sm">{symbol}</div>

                          <div className="text-xs text-white font-semibold text-center">
                            {data.lighter ? `$${data.lighter.price.toFixed(2)}` : '-'}
                          </div>
                          <div className="text-[10px] text-slate-400 text-center">
                            {data.lighter ? `$${(data.lighter.volume / 1000000).toFixed(1)}M` : '-'}
                          </div>
                          <div className="text-[10px] text-center">
                            {data.lighter && avgPrice > 0 && prices.length > 1 ? (
                              <span className={`font-medium ${data.lighter.price > avgPrice ? 'text-green-400' : 'text-red-400'}`}>
                                {data.lighter.price > avgPrice ? '+' : ''}{((data.lighter.price - avgPrice) / avgPrice * 100).toFixed(2)}%
                              </span>
                            ) : '-'}
                          </div>

                          <div className="text-xs text-white font-semibold text-center">
                            {data.extended ? `$${data.extended.price.toFixed(2)}` : '-'}
                          </div>
                          <div className="text-[10px] text-slate-400 text-center">
                            {data.extended ? `$${(data.extended.volume / 1000000).toFixed(1)}M` : '-'}
                          </div>
                          <div className="text-[10px] text-center">
                            {data.extended && avgPrice > 0 && prices.length > 1 ? (
                              <span className={`font-medium ${data.extended.price > avgPrice ? 'text-green-400' : 'text-red-400'}`}>
                                {data.extended.price > avgPrice ? '+' : ''}{((data.extended.price - avgPrice) / avgPrice * 100).toFixed(2)}%
                              </span>
                            ) : '-'}
                          </div>

                          <div className="text-xs text-white font-semibold text-center">
                            {data.paradex ? `$${data.paradex.price.toFixed(2)}` : '-'}
                          </div>
                          <div className="text-[10px] text-slate-400 text-center">
                            {data.paradex ? `$${(data.paradex.volume / 1000000).toFixed(1)}M` : '-'}
                          </div>
                          <div className="text-[10px] text-center">
                            {data.paradex && avgPrice > 0 && prices.length > 1 ? (
                              <span className={`font-medium ${data.paradex.price > avgPrice ? 'text-green-400' : 'text-red-400'}`}>
                                {data.paradex.price > avgPrice ? '+' : ''}{((data.paradex.price - avgPrice) / avgPrice * 100).toFixed(2)}%
                              </span>
                            ) : '-'}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-slate-900 to-slate-800 border-slate-700 mt-4">
          <CardHeader className="pb-2">
            <CardTitle className="text-white text-sm flex items-center gap-2">
              <TrendingUp className="w-4 h-4" />
              ATH / ATL (Session)
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="max-h-[300px] overflow-y-auto space-y-2">
              {sortedMarkets.slice(0, 20).map(symbol => {
                const lighterKey = `${symbol}_lighter`;
                const extendedKey = `${symbol}_extended`;
                const paradexKey = `${symbol}_paradex`;

                return (
                  <div key={symbol} className="p-2 bg-slate-800/50 rounded border border-slate-700">
                    <div className="font-bold text-white text-xs mb-2">{symbol}</div>
                    <div className="grid grid-cols-3 gap-3 text-[10px]">
                      <div>
                        <span className="text-green-400">Lighter:</span>
                        {athAtl[lighterKey] ? (
                          <>
                            <div className="text-green-300">ATH: ${athAtl[lighterKey].ath.toFixed(2)}</div>
                            <div className="text-red-300">ATL: ${athAtl[lighterKey].atl.toFixed(2)}</div>
                          </>
                        ) : (
                          <div className="text-slate-600">-</div>
                        )}
                      </div>
                      <div>
                        <span className="text-blue-400">Extended:</span>
                        {athAtl[extendedKey] ? (
                          <>
                            <div className="text-green-300">ATH: ${athAtl[extendedKey].ath.toFixed(2)}</div>
                            <div className="text-red-300">ATL: ${athAtl[extendedKey].atl.toFixed(2)}</div>
                          </>
                        ) : (
                          <div className="text-slate-600">-</div>
                        )}
                      </div>
                      <div>
                        <span className="text-purple-400">Paradex:</span>
                        {athAtl[paradexKey] ? (
                          <>
                            <div className="text-green-300">ATH: ${athAtl[paradexKey].ath.toFixed(2)}</div>
                            <div className="text-red-300">ATL: ${athAtl[paradexKey].atl.toFixed(2)}</div>
                          </>
                        ) : (
                          <div className="text-slate-600">-</div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}