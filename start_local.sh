#!/bin/bash
echo "================================================="
echo "🚀 Starting RS Industry CRM Local Servers..."
echo "================================================="

# Kill any existing processes running on port 8001 just in case
lsof -ti:8001 | xargs kill -9 2>/dev/null

echo "1️⃣ Starting Local HTTP Server on Port 8001 (with Caffeine)..."
caffeinate -i python3 server.py &
SERVER_PID=$!

echo "2️⃣ Starting Telegram Bot (with Caffeine)..."
caffeinate -i python3 main.py &
BOT_PID=$!

echo "✅ Both servers are running in the background."
echo "🌍 Open http://localhost:8001 in your browser."
echo "🛑 To stop the servers, close this terminal window or press Ctrl+C."

# Wait for all background processes
wait $SERVER_PID
wait $BOT_PID
