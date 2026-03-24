#!/bin/bash
echo "Starting Council..."
cd "$(dirname "$0")"
source venv/bin/activate

# Start the Council server in background
python -c "import uvicorn; from server import app; uvicorn.run(app, host='0.0.0.0', port=8001)" &
SERVER_PID=$!

echo "Council server running on http://localhost:8001"
echo "Server PID: $SERVER_PID"
echo ""
echo "To expose publicly: ngrok http 8001"
echo "Then open the ngrok URL on your phone and Add to Home Screen"
echo ""
echo "Press Ctrl+C to stop"
wait $SERVER_PID
