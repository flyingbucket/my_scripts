#!/usr/bin/bash

# 显式指定参数，脚本里不需要复杂的转义
/usr/bin/google-chrome-stable \
  --proxy-server="http=127.0.0.1:7897;https=127.0.0.1:7897" \
  --proxy-bypass-list="<local>" \
  "$@"
