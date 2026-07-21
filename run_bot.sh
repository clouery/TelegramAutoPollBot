#!/bin/bash
cd "$(dirname "$0")"
while true; do
  python3 bot.py >> bot.log 2>&1
  sleep 2
done
