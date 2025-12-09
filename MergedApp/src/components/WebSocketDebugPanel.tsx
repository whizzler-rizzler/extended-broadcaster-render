import { useEffect, useState, useRef, useCallback } from 'react';
import { Card } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@/components/ui/button';
import { RefreshCw } from 'lucide-react';

interface RawEvent {
  timestamp: string;
  rawData: string;
}

export const WebSocketDebugPanel = () => {
  const [events, setEvents] = useState<RawEvent[]>([]);
  const [eventCount, setEventCount] = useState(0);
  const [isConnected, setIsConnected] = useState(false);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const maxEvents = 100;
  const WS_RECONNECT_DELAY = 3000;

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/broadcast`;
    
    console.log('🔍 Debug panel connecting to:', wsUrl);
    
    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('🔍 Debug WebSocket connected');
        setIsConnected(true);
        setReconnectAttempt(0);
      };

      ws.onmessage = (event) => {
        const now = new Date();
        const timestamp = `${now.toLocaleTimeString('pl-PL')}:${now.getMilliseconds().toString().padStart(3, '0')}`;
        
        setEventCount(prev => prev + 1);
        
        setEvents(prev => {
          const newEvents = [{
            timestamp,
            rawData: event.data
          }, ...prev];
          
          return newEvents.slice(0, maxEvents);
        });
      };

      ws.onerror = (error) => {
        console.error('🔍 Debug WebSocket error:', error);
      };

      ws.onclose = () => {
        console.log('🔍 Debug WebSocket disconnected');
        setIsConnected(false);
        wsRef.current = null;

        // Reconnect with exponential backoff
        const delay = Math.min(WS_RECONNECT_DELAY * Math.pow(1.5, reconnectAttempt), 30000);
        console.log(`🔍 Debug panel reconnecting in ${delay}ms (attempt ${reconnectAttempt + 1})`);
        
        reconnectTimeoutRef.current = setTimeout(() => {
          setReconnectAttempt(prev => prev + 1);
          connect();
        }, delay);
      };
    } catch (err) {
      console.error('🔍 Debug WebSocket setup error:', err);
    }
  }, [reconnectAttempt]);

  const forceReconnect = useCallback(() => {
    console.log('🔍 Force reconnecting debug panel...');
    if (wsRef.current) {
      wsRef.current.close();
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    setReconnectAttempt(0);
    setTimeout(connect, 100);
  }, [connect]);

  useEffect(() => {
    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [connect]);

  return (
    <Card className="bg-black border-destructive/50 p-4">
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-destructive">🔍 RAW WEBSOCKET DEBUG</h3>
          <div className="flex items-center gap-4 text-sm">
            <Button
              variant="outline"
              size="sm"
              onClick={forceReconnect}
              className="h-7 px-2"
            >
              <RefreshCw className="h-3 w-3 mr-1" />
              Reconnect
            </Button>
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-success animate-pulse' : 'bg-destructive'}`} />
              <span className="text-muted-foreground">
                {isConnected ? 'Połączono' : reconnectAttempt > 0 ? `Łączenie... (${reconnectAttempt})` : 'Rozłączono'}
              </span>
            </div>
            <div className="text-primary font-mono">
              Łącznie eventów: {eventCount}
            </div>
          </div>
        </div>

        <ScrollArea className="h-[600px] rounded-md border border-destructive/30 bg-black/50 p-4">
          <div className="space-y-2 font-mono text-xs">
            {events.length === 0 ? (
              <div className="text-muted-foreground text-center py-8">
                Oczekiwanie na dane WebSocket...
              </div>
            ) : (
              events.map((event, index) => (
                <div 
                  key={index} 
                  className="border border-primary/20 rounded p-3 bg-primary/5 hover:bg-primary/10 transition-colors"
                >
                  <div className="flex items-center justify-between mb-2 pb-2 border-b border-primary/20">
                    <span className="text-destructive font-bold">#{eventCount - index}</span>
                    <span className="text-success">{event.timestamp}</span>
                  </div>
                  <pre className="text-foreground whitespace-pre-wrap break-all">
                    {event.rawData}
                  </pre>
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </div>
    </Card>
  );
};
