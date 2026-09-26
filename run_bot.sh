#!/bin/bash
# Local dev convenience runner: restart the bot with exponential backoff so a
# persistent config error doesn't busy-loop at 2s. Backoff resets after a
# healthy run of at least 60 seconds.
cd "$(dirname "$0")"
delay=2
while true; do
  start=$(date +%s)
  python3 bot.py >> bot.log 2>&1
  ran=$(( $(date +%s) - start ))
  if [ "$ran" -ge 60 ]; then
    delay=2
  elif [ "$delay" -lt 60 ]; then
    delay=$(( delay * 2 ))
  fi
  sleep "$delay"
done
