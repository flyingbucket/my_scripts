#!/usr/bin/env bash
set -euo pipefail

# ==========================================================
# Safer Git history rewrite using git filter-repo
# - Only rewrites commits whose (author/committer) email matches OLD_EMAILS
# - Default: change email only; optionally change name
# - Includes dry-run check, clean-worktree check, unshallow, backups
# - Backups & restores remotes to avoid losing 'origin' on older versions
# ==========================================================

# ---------- helpers ----------
err() {
  echo "ERROR: $*" >&2
  exit 1
}
info() { echo "[$(date +%H:%M:%S)] $*"; }
need() { command -v "$1" >/dev/null 2>&1 || err "Missing command: $1"; }

# ---------- defaults ----------
DRY_RUN=0
ASSUME_YES=0
NEW_NAME=""
OLD_EMAILS=()
NEW_EMAIL=""

# ---------- parse args ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
  --old-email)
    [[ $# -ge 2 ]] || err "--old-email requires a value"
    OLD_EMAILS+=("$2")
    shift 2
    ;;
  --new-email)
    [[ $# -ge 2 ]] || err "--new-email requires a value"
    NEW_EMAIL="$2"
    shift 2
    ;;
  --new-name)
    [[ $# -ge 2 ]] || err "--new-name requires a value"
    NEW_NAME="$2"
    shift 2
    ;;
  --dry-run)
    DRY_RUN=1
    shift
    ;;
  --yes | -y)
    ASSUME_YES=1
    shift
    ;;
  -h | --help)
    cat <<'EOF'
Usage:
  safe_rewrite_email.sh --old-email OLD [...] --new-email NEW [--new-name "NAME"] [--dry-run] [--yes]
EOF
    exit 0
    ;;
  *) err "Unknown argument: $1" ;;
  esac
done

# ---------- validation ----------
need git
if ! git filter-repo -h >/dev/null 2>&1; then
  err "git filter-repo not found. Install: https://github.com/newren/git-filter-repo
  On many systems: pip install git-filter-repo"
fi
[[ ${#OLD_EMAILS[@]} -ge 1 ]] || err "At least one --old-email is required"
[[ -n "$NEW_EMAIL" ]] || err "--new-email is required"

# ---------- repo checks ----------
git rev-parse --git-dir >/dev/null 2>&1 || err "Not inside a Git repository"
if ! git diff --quiet || ! git diff --cached --quiet; then
  err "Working tree or index has changes. Commit/stash them first."
fi
if [[ -f "$(git rev-parse --git-dir)/shallow" ]]; then
  info "Repository is shallow. Fetching full history..."
  git fetch --unshallow || err "Failed to unshallow repository"
fi

# ---------- dry-run preview ----------
GREP_ARGS=()
for em in "${OLD_EMAILS[@]}"; do GREP_ARGS+=(-e "<$em>"); done

count_matches() {
  local pretty="$1" total=0 n
  for em in "${OLD_EMAILS[@]}"; do
    n=$(git log --all --pretty="$pretty" | grep -F "<$em>" | wc -l | tr -d ' ')
    total=$((total + n))
  done
  echo "$total"
}

info "Scanning commits for matching author/committer emails..."
AFFECTED_AUTHOR=$(count_matches '%H%x09%an <%ae>')
AFFECTED_COMMITTER=$(count_matches '%H%x09%cn <%ce>')

info "Potentially affected commits:"
echo "  * author-email matches   : ${AFFECTED_AUTHOR}"
echo "  * committer-email matches: ${AFFECTED_COMMITTER}"

if [[ $DRY_RUN -eq 1 ]]; then
  echo
  info "Dry-run mode enabled. Example matches (up to 20):"
  echo "  -- Author matches:"
  git log --all --pretty='%h %ad %an <%ae>' --date=short | grep -F "${GREP_ARGS[@]}" | head -n 20 || true
  echo
  echo "  -- Committer matches:"
  git log --all --pretty='%h %ad %cn <%ce>' --date=short | grep -F "${GREP_ARGS[@]}" | head -n 20 || true
  info "Dry-run finished. No changes were made."
  exit 0
fi

if [[ "$AFFECTED_AUTHOR" -eq 0 && "$AFFECTED_COMMITTER" -eq 0 ]]; then
  err "No commits match the given --old-email values."
fi

# ---------- confirmation ----------
echo
info "About to rewrite history with git filter-repo"
echo "  Old emails : ${OLD_EMAILS[*]}"
echo "  New email  : ${NEW_EMAIL}"
[[ -n "$NEW_NAME" ]] && echo "  New name   : ${NEW_NAME}" || echo "  Name change: (none, will preserve existing names)"
echo "This will change commit hashes. You will need to force push."
if [[ $ASSUME_YES -ne 1 ]]; then
  read -r -p "Proceed? [y/N]: " ans
  [[ "${ans:-N}" =~ ^[Yy]$ ]] || {
    info "Aborted."
    exit 0
  }
fi

# ---------- backup branch/tag ----------
TS=$(date +%Y%m%d_%H%M%S)
BACKUP_BRANCH="pre-filter-repo-backup-${TS}"
BACKUP_TAG="pre_filter_repo_${TS}"
info "Creating backups: branch '${BACKUP_BRANCH}', tag '${BACKUP_TAG}'"
git branch "${BACKUP_BRANCH}"
git tag -a "${BACKUP_TAG}" -m "Backup before filter-repo at ${TS}"

# ---------- snapshot remotes (for later restore) ----------
REMOTE_SNAPSHOT="$(mktemp)"
info "Saving remotes snapshot to ${REMOTE_SNAPSHOT}"
for r in $(git remote); do
  fetch_url="$(git remote get-url --fetch "$r" 2>/dev/null || true)"
  push_url="$(git remote get-url --push "$r" 2>/dev/null || true)"
  echo "$r|$fetch_url|$push_url" >>"${REMOTE_SNAPSHOT}"
done

# ---------- run filter-repo ----------
export SAFEWR_OLD_EMAILS_CSV SAFEWR_NEW_EMAIL SAFEWR_NEW_NAME
SAFEWR_OLD_EMAILS_CSV="$(
  IFS=,
  echo "${OLD_EMAILS[*]}"
)"
SAFEWR_NEW_EMAIL="$NEW_EMAIL"
SAFEWR_NEW_NAME="${NEW_NAME}"

restore_remotes() {
  local have_any="$(git remote | wc -l | tr -d ' ')"
  if [[ "$have_any" -eq 0 ]]; then
    info "Restoring remotes from snapshot..."
    while IFS='|' read -r name fetch push; do
      [[ -z "$name" ]] && continue
      # 如果 fetch 为空但 push 存在，优先用 push 作为 fetch
      if [[ -z "$fetch" && -n "$push" ]]; then
        fetch="$push"
      fi
      # 如果两者都空，才使用占位符
      if [[ -z "$fetch" && -z "$push" ]]; then
        fetch="placeholder://removed"
      fi
      # 添加 remote
      git remote add "$name" "$fetch" || true
      # 如果 push 与 fetch 不同，单独设置 push URL
      if [[ -n "$push" && "$push" != "$fetch" ]]; then
        git remote set-url --push "$name" "$push" || true
      fi
    done <"${REMOTE_SNAPSHOT}"
  fi
}

trap 'restore_remotes; rm -f "${REMOTE_SNAPSHOT}"' EXIT

if [[ -z "$NEW_NAME" ]]; then
  # --------- Only change email ----------
  EMAIL_CB=$(
    cat <<'PYCODE'
import os
old_csv  = os.environ.get("SAFEWR_OLD_EMAILS_CSV","")
old_set  = set(e.strip().encode() for e in old_csv.split(",") if e.strip())
new_email = os.environ["SAFEWR_NEW_EMAIL"].encode()
# --email-callback: must directly return bytes
return new_email if email in old_set else email
PYCODE
  )
  info "Running git filter-repo (email-callback)..."
  git filter-repo --force --quiet --email-callback "$EMAIL_CB"
else
  # --------- Change email AND (optionally) name ----------
  COMMIT_CB=$(
    cat <<'PYCODE'
import os
old_csv = os.environ.get("SAFEWR_OLD_EMAILS_CSV","")
old_set = set(e.strip().encode() for e in old_csv.split(",") if e.strip())
new_email = os.environ["SAFEWR_NEW_EMAIL"].encode()
new_name_opt = os.environ.get("SAFEWR_NEW_NAME","")
new_name = new_name_opt.encode() if new_name_opt else None
# --commit-callback: modify commit object in-place
if commit.author_email in old_set:
    commit.author_email = new_email
    if new_name is not None:
        commit.author_name = new_name
if commit.committer_email in old_set:
    commit.committer_email = new_email
    if new_name is not None:
        commit.committer_name = new_name
PYCODE
  )
  info "Running git filter-repo (commit-callback)..."
  git filter-repo --force --quiet --commit-callback "$COMMIT_CB"
fi

# trap 会自动尝试恢复 remotes（若被清空）
info "Rewrite complete."
echo
info "Post-steps:"
echo "  1) Inspect results, e.g.:"
echo "     git log --pretty='%h %an <%ae>' -n 10"
echo "  2) When satisfied, force-push:"
echo "     git push --force --all"
echo "     git push --force --tags"
echo "  3) If something looks wrong, roll back to the backup:"
echo "     git reset --hard ${BACKUP_BRANCH}"
echo "     # or: git checkout ${BACKUP_BRANCH}"
