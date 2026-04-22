#!/bin/bash
rclone sync nut:/ $HOME/Nut \
  -v \
  --exclude "*.pth" \
  --exclude "*cs61A/*" \
  --tpslimit 10 \
  --transfers 5 \
  >>/tmp/nutdown.log 2>&1 &
sleep 2
