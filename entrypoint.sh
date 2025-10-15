#!/bin/sh
set -e

# This script acts as the main entry point for the Docker container.
# It checks the value of the first argument ($1) to decide whether
# to start the web server or the background workers.

if [ "$1" = "web" ]; then
  echo "Starting Gunicorn web server with DEBUG logging..."
  
  # Set environment variables for the Uvicorn workers.
  export UVICORN_PROXY_HEADERS="True"
  export UVICORN_FORWARDED_ALLOW_IPS="*"
  export UVICORN_WS="websockets"

  # Execute gunicorn with --log-level debug to get verbose output.
  exec gunicorn -w 4 -k uvicorn.workers.UvicornWorker src.ingress.api:app --bind 0.0.0.0:8000 --log-level debug --preload
  # uvicorn src.ingress.api:app --host 0.0.0.0 --port 8000 --log-level debug --ws websockets
elif [ "$1" = "worker" ]; then
  echo "Starting background workers..."
  exec python run_workers.py
else
  # If no argument is provided, or an unknown argument is provided,
  # execute the command passed to the script. This is useful for debugging.
  exec "$@"
fi
