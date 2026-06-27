#!/usr/bin/env bash
# Lock Orrin's program tree during long runs, then restore original modes.
#
# This is a practical run guard, not a same-user security boundary. It prevents
# accidental edits by making source files read-only/private and, on macOS, user
# immutable. Live mind/state folders are intentionally excluded.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="$(cd "${ORRIN_RUN_LOCK_REPO:-$DEFAULT_REPO}" && pwd)"
LOCK_DIR="${ORRIN_RUN_LOCK_DIR:-$REPO/.run_lock}"
MANIFEST="$LOCK_DIR/manifest.tsv"
STATE_FILE="$LOCK_DIR/state"
OWNER_FILE="$LOCK_DIR/owner.pid"

CHFLAGS_BIN="$(command -v chflags 2>/dev/null || true)"

SOURCE_ROOTS=(
    ".github"
    "backend"
    "brain"
    "docs"
    "frontend"
    "goals"
    "memory"
    "observability"
    "packaging"
    "reaper"
    "runtime"
    "scripts"
    "tests"
)

TOP_LEVEL_FILES=(
    ".coverage-floor"
    ".dockerignore"
    ".env"
    ".env.example"
    ".gitignore"
    "Dockerfile"
    "LICENSE"
    "Makefile"
    "ORRIN_ACTIVITY_REPORT.md"
    "README.md"
    "TEMPLATES.md"
    "docker-compose.yml"
    "expose_orrin.command"
    "main.py"
    "pyproject.toml"
    "pytest.ini"
    "requirements.lock"
    "requirements.txt"
    "reset_orrin.py"
    "run_orrin.bat"
    "run_orrin.sh"
    "start_orrin.command"
    "tailscale_funnel.command"
    "watchdogs.py"
)

usage() {
    cat <<'USAGE'
Usage:
  scripts/orrin_run_lock.sh lock [--owner-pid PID]
  scripts/orrin_run_lock.sh unlock
  scripts/orrin_run_lock.sh status
  scripts/orrin_run_lock.sh list

Environment:
  ORRIN_RUN_LOCK_REPO=/path/to/repo       override repo root, mainly for tests
  ORRIN_RUN_LOCK_DIR=/path/to/lock-dir    override manifest directory
  ORRIN_RUN_LOCK_IMMUTABLE=0              skip macOS chflags uchg/nouchg
USAGE
}

mode_of() {
    local path="$1"
    stat -f "%OLp" "$path" 2>/dev/null || stat -c "%a" "$path"
}

use_chflags() {
    case "${ORRIN_RUN_LOCK_IMMUTABLE:-auto}" in
        0|false|False|FALSE|no|No|NO) return 1 ;;
    esac
    [ -n "$CHFLAGS_BIN" ]
}

record_path() {
    local path="$1"
    local kind mode

    [ -e "$path" ] || return 0
    [ ! -L "$path" ] || return 0

    case "$path" in
        "$LOCK_DIR"|"$LOCK_DIR"/*) return 0 ;;
    esac

    if [ -d "$path" ]; then
        kind="d"
    elif [ -f "$path" ]; then
        kind="f"
    else
        return 0
    fi

    mode="$(mode_of "$path")"
    printf '%s\t%s\t%s\n' "$kind" "$mode" "$path"
}

collect_paths() {
    local root rel file

    record_path "$REPO"

    for rel in "${SOURCE_ROOTS[@]}"; do
        root="$REPO/$rel"
        [ -e "$root" ] || continue

        find "$root" \
            \( \
                -path "$REPO/brain/data" -o -path "$REPO/brain/data/*" -o \
                -path "$REPO/brain/logs" -o -path "$REPO/brain/logs/*" -o \
                -path "$REPO/frontend/dist" -o -path "$REPO/frontend/dist/*" -o \
                -path "$REPO/frontend/node_modules" -o -path "$REPO/frontend/node_modules/*" -o \
                -name "__pycache__" -o \
                -name "node_modules" -o \
                -name ".mypy_cache" -o \
                -name ".pytest_cache" -o \
                -name ".ruff_cache" \
            \) -prune -o \
            \( -type f -o -type d \) -print
    done | while IFS= read -r file; do
        record_path "$file"
    done

    for rel in "${TOP_LEVEL_FILES[@]}"; do
        record_path "$REPO/$rel"
    done
}

manifest_count() {
    [ -f "$MANIFEST" ] || {
        echo 0
        return
    }
    wc -l < "$MANIFEST" | tr -d ' '
}

is_locked() {
    [ -f "$MANIFEST" ] && [ -f "$STATE_FILE" ] && grep -qx "locked" "$STATE_FILE"
}

write_manifest() {
    local tmp="$LOCK_DIR/manifest.$$.tmp"
    mkdir -p "$LOCK_DIR"
    collect_paths | awk '!seen[$0]++' > "$tmp"
    if [ ! -s "$tmp" ]; then
        rm -f "$tmp"
        echo "[run-lock] ERROR: no lockable paths found under $REPO" >&2
        exit 1
    fi
    mv "$tmp" "$MANIFEST"
}

lock_path() {
    local kind="$1"
    local path="$2"

    [ -e "$path" ] || return 0
    if [ "$kind" = "f" ]; then
        chmod u-w,go-rwx "$path"
        if use_chflags; then
            "$CHFLAGS_BIN" uchg "$path" 2>/dev/null || {
                echo "[run-lock] warning: could not set immutable flag on $path" >&2
            }
        fi
    elif [ "$kind" = "d" ]; then
        chmod u-w,go-rwx "$path"
    fi
}

unlock_flags() {
    local kind="$1"
    local path="$2"

    [ "$kind" = "f" ] || return 0
    [ -e "$path" ] || return 0
    if use_chflags; then
        "$CHFLAGS_BIN" nouchg "$path" 2>/dev/null || true
    fi
}

restore_mode() {
    local mode="$1"
    local path="$2"

    [ -e "$path" ] || return 0
    chmod "$mode" "$path" 2>/dev/null || {
        echo "[run-lock] warning: could not restore mode $mode on $path" >&2
    }
}

lock_repo() {
    local owner_pid=""
    local lock_complete=0
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --owner-pid)
                owner_pid="${2:-}"
                [ -n "$owner_pid" ] || {
                    echo "[run-lock] ERROR: --owner-pid requires a value" >&2
                    exit 2
                }
                shift 2
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                echo "[run-lock] ERROR: unknown lock option: $1" >&2
                usage >&2
                exit 2
                ;;
        esac
    done

    if is_locked; then
        echo "[run-lock] already locked: $REPO ($(manifest_count) paths)"
        exit 2
    fi

    write_manifest
    if [ -n "$owner_pid" ]; then
        printf '%s\n' "$owner_pid" > "$OWNER_FILE"
    fi

    rollback_partial_lock() {
        if [ "$lock_complete" -eq 0 ]; then
            echo "[run-lock] lock interrupted; restoring original modes" >&2
            unlock_repo >/dev/null 2>&1 || true
        fi
    }
    trap rollback_partial_lock ERR INT TERM

    local kind mode path
    while IFS=$'\t' read -r kind mode path; do
        lock_path "$kind" "$path"
    done < "$MANIFEST"

    printf 'locked\n' > "$STATE_FILE"
    lock_complete=1
    trap - ERR INT TERM
    echo "[run-lock] locked $(manifest_count) paths under $REPO"
}

unlock_repo() {
    if [ ! -f "$MANIFEST" ]; then
        echo "[run-lock] no active lock manifest under $LOCK_DIR"
        return 0
    fi

    local kind mode path
    while IFS=$'\t' read -r kind mode path; do
        unlock_flags "$kind" "$path"
    done < "$MANIFEST"

    while IFS=$'\t' read -r kind mode path; do
        restore_mode "$mode" "$path"
    done < "$MANIFEST"

    local count
    count="$(manifest_count)"
    rm -f "$MANIFEST" "$STATE_FILE" "$OWNER_FILE"
    rmdir "$LOCK_DIR" 2>/dev/null || true
    echo "[run-lock] unlocked $count paths under $REPO"
}

status_repo() {
    if is_locked; then
        local owner=""
        if [ -f "$OWNER_FILE" ]; then
            owner="$(tr -d '\n' < "$OWNER_FILE")"
        fi
        if [ -n "$owner" ]; then
            echo "[run-lock] locked: $REPO ($(manifest_count) paths, owner pid $owner)"
        else
            echo "[run-lock] locked: $REPO ($(manifest_count) paths)"
        fi
    elif [ -f "$MANIFEST" ]; then
        echo "[run-lock] partial/stale manifest present: $MANIFEST ($(manifest_count) paths)"
    else
        echo "[run-lock] unlocked: $REPO"
    fi
}

list_repo() {
    collect_paths | awk '!seen[$0]++'
}

cmd="${1:-status}"
if [ "$#" -gt 0 ]; then
    shift
fi

case "$cmd" in
    lock) lock_repo "$@" ;;
    unlock) unlock_repo ;;
    status) status_repo ;;
    list) list_repo ;;
    -h|--help|help) usage ;;
    *)
        echo "[run-lock] ERROR: unknown command: $cmd" >&2
        usage >&2
        exit 2
        ;;
esac
