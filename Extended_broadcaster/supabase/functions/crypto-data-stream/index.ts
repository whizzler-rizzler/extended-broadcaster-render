// Edge function to relay crypto aggregator data stream to other consumers
// This allows multiple clients to receive the same real-time data

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

Deno.serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  const { headers } = req;
  const upgradeHeader = headers.get("upgrade") || "";

  if (upgradeHeader.toLowerCase() !== "websocket") {
    return new Response("Expected WebSocket connection", { status: 400 });
  }

  const { socket, response } = Deno.upgradeWebSocket(req);
  
  let aggregatorWs: WebSocket | null = null;
  let reconnectAttempts = 0;
  let isClientConnected = true;
  let reconnectTimeout: number | null = null;
  let pingInterval: number | null = null;

  const MAX_RECONNECT_ATTEMPTS = 10;
  const BASE_RECONNECT_DELAY = 1000; // 1 second
  const MAX_RECONNECT_DELAY = 30000; // 30 seconds
  const PING_INTERVAL = 25000; // 25 seconds - keep connection alive

  const getReconnectDelay = () => {
    // Exponential backoff with jitter
    const delay = Math.min(
      BASE_RECONNECT_DELAY * Math.pow(2, reconnectAttempts),
      MAX_RECONNECT_DELAY
    );
    return delay + Math.random() * 1000; // Add jitter
  };

  const clearTimers = () => {
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout);
      reconnectTimeout = null;
    }
    if (pingInterval) {
      clearInterval(pingInterval);
      pingInterval = null;
    }
  };

  const connectToAggregator = () => {
    if (!isClientConnected) {
      console.log('Client disconnected, not reconnecting to aggregator');
      return;
    }

    try {
      const projectId = 'ujtavgmgeefutsadbyzv';
      console.log(`Connecting to crypto-aggregator (attempt ${reconnectAttempts + 1}/${MAX_RECONNECT_ATTEMPTS})...`);
      
      aggregatorWs = new WebSocket(`wss://${projectId}.supabase.co/functions/v1/crypto-aggregator`);
      
      aggregatorWs.onopen = () => {
        console.log('✓ Connected to crypto-aggregator');
        reconnectAttempts = 0; // Reset on successful connection
        
        // Start ping interval to keep connection alive
        if (pingInterval) clearInterval(pingInterval);
        pingInterval = setInterval(() => {
          if (aggregatorWs && aggregatorWs.readyState === WebSocket.OPEN) {
            try {
              aggregatorWs.send(JSON.stringify({ type: 'ping' }));
            } catch (e) {
              console.error('Failed to send ping:', e);
            }
          }
        }, PING_INTERVAL);
        
        // Send connection status to client
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ 
            type: 'status', 
            status: 'connected',
            message: 'Connected to data stream'
          }));
        }
      };

      aggregatorWs.onmessage = (event) => {
        // Relay the message to the client
        if (socket.readyState === WebSocket.OPEN) {
          try {
            socket.send(event.data);
          } catch (e) {
            console.error('Failed to relay message to client:', e);
          }
        }
      };

      aggregatorWs.onerror = (error) => {
        console.error('Aggregator WebSocket error');
      };

      aggregatorWs.onclose = (event) => {
        console.log(`Aggregator connection closed (code: ${event.code}, reason: ${event.reason})`);
        
        if (pingInterval) {
          clearInterval(pingInterval);
          pingInterval = null;
        }
        
        // Only reconnect if client is still connected and we haven't exceeded max attempts
        if (isClientConnected && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttempts++;
          const delay = getReconnectDelay();
          console.log(`Reconnecting in ${Math.round(delay)}ms...`);
          
          // Notify client about reconnection
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ 
              type: 'status', 
              status: 'reconnecting',
              attempt: reconnectAttempts,
              maxAttempts: MAX_RECONNECT_ATTEMPTS,
              message: `Reconnecting to data stream (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`
            }));
          }
          
          reconnectTimeout = setTimeout(() => {
            connectToAggregator();
          }, delay);
        } else if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
          console.log('Max reconnection attempts reached');
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ 
              type: 'status', 
              status: 'failed',
              message: 'Failed to connect to data stream after multiple attempts'
            }));
          }
        }
      };
    } catch (error) {
      console.error('Error creating aggregator connection:', error);
      
      if (isClientConnected && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttempts++;
        const delay = getReconnectDelay();
        reconnectTimeout = setTimeout(() => {
          connectToAggregator();
        }, delay);
      }
    }
  };

  socket.onopen = () => {
    console.log('Client connected to data stream');
    isClientConnected = true;
    
    // Connect to aggregator
    connectToAggregator();
  };

  socket.onmessage = (event) => {
    // Handle messages from client (e.g., ping/pong)
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'ping') {
        socket.send(JSON.stringify({ type: 'pong' }));
      }
    } catch (e) {
      // Ignore parse errors
    }
  };

  socket.onclose = () => {
    console.log('Client disconnected from data stream');
    isClientConnected = false;
    
    // Clean up
    clearTimers();
    
    if (aggregatorWs) {
      try {
        aggregatorWs.close();
      } catch (e) {
        // Ignore close errors
      }
      aggregatorWs = null;
    }
  };

  socket.onerror = (error) => {
    console.error('Client WebSocket error');
  };

  return response;
});
