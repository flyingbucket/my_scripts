#!/bin/bash
nohup rclone sync $HOME/Nut nut:/ \
  -v \
  --exclude ".pth" \
  --exclude "*cs61A/*" \
  --tpslimit 5 \
  --transfers 3 \
  >>/tmp/nutup.txt 2>&1 &
sleep 2
