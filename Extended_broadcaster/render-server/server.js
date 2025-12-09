const WebSocket = require('ws');
const http = require('http');

const PORT = process.env.PORT || 3001;
const CRYPTO_WS_URL = 'wss://ujtavgmgeefutsadbyzv.supabase.co/functions/v1/crypto-data-stream';

// Create HTTP server
const server = http.createServer((req, res) => {
  if (req.url === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', timestamp: new Date().toISOString() }));
  } else {
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end('Crypto Data Stream Relay Server');
  }
});

// Create WebSocket server
const wss = new WebSocket.Server({ server });

let upstreamWs = null;
const clients = new Set();

// Connect to upstream crypto-data-stream
function connectUpstream() {
  console.log('Connecting to upstream WebSocket...');
  
  upstreamWs = new WebSocket(CRYPTO_WS_URL);

  upstreamWs.on('open', () => {
    console.log('Connected to upstream crypto-data-stream');
  });

  upstreamWs.on('message', (data) => {
    // Broadcast to all connected clients
    const message = data.toString();
    clients.forEach((client) => {
      if (client.readyState === WebSocket.OPEN) {
        client.send(message);
      }
    });
  });

  upstreamWs.on('error', (error) => {
    console.error('Upstream WebSocket error:', error);
  });

  upstreamWs.on('close', () => {
    console.log('Upstream connection closed. Reconnecting in 3 seconds...');
    setTimeout(connectUpstream, 3000);
  });
}

// Handle client connections
wss.on('connection', (ws) => {
  console.log('New client connected. Total clients:', clients.size + 1);
  clients.add(ws);

  ws.on('close', () => {
    console.log('Client disconnected. Total clients:', clients.size - 1);
    clients.delete(ws);
  });

  ws.on('error', (error) => {
    console.error('Client WebSocket error:', error);
    clients.delete(ws);
  });
});

// Start server
server.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
  connectUpstream();
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('SIGTERM received, closing server...');
  wss.close();
  if (upstreamWs) upstreamWs.close();
  server.close(() => {
    console.log('Server closed');
    process.exit(0);
  });
});
