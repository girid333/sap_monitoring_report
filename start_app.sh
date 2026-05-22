#!/bin/bash

# Ensure old processes are killed
echo "Cleaning up existing processes..."
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:3000 | xargs kill -9 2>/dev/null
sleep 1

# Start the Python FastAPI Backend
export DYLD_LIBRARY_PATH=/Users/giri/nwrfc/nwrfcsdk/lib:$DYLD_LIBRARY_PATH
echo "Starting Backend API..."

# Auto-detect the virtual environment with pyrfc
if [ -f "/Users/giri/pyrfc-env/bin/python3" ]; then
    PYTHON_BIN="/Users/giri/pyrfc-env/bin/python3"
    echo "Using python environment: $PYTHON_BIN"
else
    PYTHON_BIN="python3"
    echo "Using system python: $PYTHON_BIN"
fi

echo "Python version: $($PYTHON_BIN --version)"
echo "Python path: $PYTHON_BIN"
$PYTHON_BIN -c "import pyrfc; print('pyrfc is available')" || echo "ERROR: pyrfc is NOT available in this environment"
$PYTHON_BIN -c "import uvicorn; print('uvicorn is available')" || echo "ERROR: uvicorn is NOT available in this environment"

cd backend
$PYTHON_BIN -m uvicorn main:app --host 0.0.0.0 --port 8000 2>&1 | tee ../backend.log &
BACKEND_PID=$!
cd ..

# Start the Next.js Frontend
echo "Starting Next.js Frontend..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo "Servers are running."
echo "Frontend is available at http://localhost:3000"
echo "Backend is available at http://localhost:8000"
echo "Press Ctrl+C to stop both servers."

trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT TERM
wait
