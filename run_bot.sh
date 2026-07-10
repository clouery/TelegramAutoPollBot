#!/bin/bash
cd /home/Clouery
pkill -f bot.py 2>/dev/null
nohup python3 bot.py > bot.log 2>&1 &
