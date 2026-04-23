#!/usr/bin/env bash
set -euo pipefail

# === 基本设置 ===
REMOTE_HOST="A30"
REMOTE_USER="flyingbucket"
REMOTE_BASE="/home/${REMOTE_USER}"

# 本地路径
LOCAL_NVIM="$HOME/apps/neovim"
LOCAL_STATE="$HOME/.local/state/nvim"
LOCAL_SHARE="$HOME/.local/share/nvim"
LOCAL_CONFIG="$HOME/dotfiles/nvim"

# 远程路径
REMOTE_APPS="${REMOTE_BASE}/apps/"
REMOTE_STATE="${REMOTE_BASE}/.local/state/"
REMOTE_SHARE="${REMOTE_BASE}/.local/share/"
REMOTE_CONFIG="${REMOTE_BASE}/.config/"

# rsync 常用选项
RSYNC_OPTS="-ah --info=progress2"

# echo "[*] Sync neovim binary..."
# rsync $RSYNC_OPTS "$LOCAL_NVIM" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_APPS}"

echo "[*] Sync nvim state..."
rsync $RSYNC_OPTS "$LOCAL_STATE" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_STATE}"

echo "[*] Sync nvim share (plugins, etc.)..."
rsync $RSYNC_OPTS "$LOCAL_SHARE" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_SHARE}"

echo "[*] Sync nvim config..."
rsync $RSYNC_OPTS "$LOCAL_CONFIG" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_CONFIG}"

echo "[✓] Neovim sync finished."
