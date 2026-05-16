#!/bin/bash
#
# Tadpole Studio Setup and Management Script
# Manages backend and frontend services as background processes
#

set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
LOGS_DIR="${SCRIPT_DIR}/logs"
PIDS_DIR="${SCRIPT_DIR}/pids"

# ── Load environment variables ───────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: .env file not found at ${ENV_FILE}"
    exit 1
fi
set -a
source "$ENV_FILE"
set +a

# ── Configuration with env var defaults ──────────────────────────────────
BACKEND_PORT="${TADPOLE_PORT:-8500}"
BACKEND_HOST="${TADPOLE_HOST:-0.0.0.0}"
FRONTEND_PORT="${TADPOLE_FRONTEND_PORT:-8700}"
VENV_PATH="${SCRIPT_DIR}/backend/.venv"
BACKEND_DIR="${SCRIPT_DIR}/backend"
FRONTEND_DIR="${SCRIPT_DIR}/frontend"

# ── Process IDs ──────────────────────────────────────────────────────────
BACKEND_PID_FILE="${PIDS_DIR}/backend.pid"
FRONTEND_PID_FILE="${PIDS_DIR}/frontend.pid"

# ── Log files ────────────────────────────────────────────────────────────
BACKEND_LOG="${LOGS_DIR}/backend.log"
FRONTEND_LOG="${LOGS_DIR}/frontend.log"

# ── Helper functions ─────────────────────────────────────────────────────

usage() {
    echo "Usage: $0 {start|stop|status|restart|logs [backend|frontend]}"
    echo ""
    echo "Commands:"
    echo "  start       Start both backend and frontend services"
    echo "  stop        Stop both backend and frontend services"
    echo "  status      Check if services are running"
    echo "  restart     Restart both backend and frontend services"
    echo "  logs        Show live logs (tail -f) for both services"
    echo "  logs backend    Show live logs for backend only"
    echo "  logs frontend   Show live logs for frontend only"
    exit 1
}

ensure_dirs() {
    mkdir -p "$LOGS_DIR" "$PIDS_DIR"
}

is_running() {
    local pid_file="$1"
    if [[ -f "$pid_file" ]]; then
        local pid
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

write_pid() {
    local pid_file="$1"
    local pid="$2"
    echo "$pid" > "$pid_file"
}

stop_service() {
    local name="$1"
    local pid_file="$2"
    local log_file="$3"

    if is_running "$pid_file"; then
        local pid
        pid=$(cat "$pid_file")
        echo "Stopping ${name} (PID: ${pid})..."
        kill "$pid" 2>/dev/null || true

        # Wait up to 10 seconds for graceful shutdown
        local count=0
        while kill -0 "$pid" 2>/dev/null && [[ $count -lt 20 ]]; do
            sleep 0.5
            count=$((count + 1))
        done

        # Force kill if still running
        if kill -0 "$pid" 2>/dev/null; then
            echo "Force killing ${name} (PID: ${pid})..."
            kill -9 "$pid" 2>/dev/null || true
        fi
        echo "${name} stopped."
    else
        echo "${name} is not running."
    fi

    # Clean up PID file
    rm -f "$pid_file"
}

check_python_env() {
    if [[ ! -d "$VENV_PATH" ]]; then
        echo "ERROR: Virtual environment not found at ${VENV_PATH}"
        echo "Please create it with: cd ${BACKEND_DIR} && uv venv"
        exit 1
    fi
    if [[ ! -f "${VENV_PATH}/bin/python" ]]; then
        echo "ERROR: Python executable not found in virtual environment"
        exit 1
    fi
}

# ── Commands ─────────────────────────────────────────────────────────────

cmd_start() {
    ensure_dirs

    # Check prerequisites
    if [[ ! -d "$VENV_PATH" ]]; then
        echo "ERROR: Virtual environment not found at ${VENV_PATH}"
        echo "Please create it with: cd ${BACKEND_DIR} && uv venv && uv sync"
        exit 1
    fi
    if ! command -v uv &>/dev/null; then
        echo "ERROR: 'uv' not found. Install: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
    if ! command -v pnpm &>/dev/null; then
        echo "ERROR: 'pnpm' not found. Install: https://pnpm.io/installation"
        exit 1
    fi

    echo "Starting Tadpole Studio..."
    echo ""

    # Start backend
    if is_running "$BACKEND_PID_FILE"; then
        echo "Backend is already running (PID: $(cat "$BACKEND_PID_FILE"))."
    else
        echo "Starting backend on ${BACKEND_HOST}:${BACKEND_PORT}..."
        cd "$BACKEND_DIR"
        # Load .env file into environment
        set -a
        source "$ENV_FILE"
        set +a
        export PYTHONUNBUFFERED=1
        uv run --no-sync tadpole-studio \
            > "$BACKEND_LOG" 2>&1 &
        local backend_pid=$!
        write_pid "$BACKEND_PID_FILE" "$backend_pid"
        echo "Backend started (PID: ${backend_pid})."
    fi

    # Start frontend
    if is_running "$FRONTEND_PID_FILE"; then
        echo "Frontend is already running (PID: $(cat "$FRONTEND_PID_FILE"))."
    else
        echo "Starting frontend on port ${FRONTEND_PORT}..."
        cd "$FRONTEND_DIR"
        # Set environment variables for frontend
        export PORT="$FRONTEND_PORT"
        export NEXT_PUBLIC_TADPOLE_API_PORT="$BACKEND_PORT"
        export NEXT_TELEMETRY_DISABLED=1
        pnpm dev \
            > "$FRONTEND_LOG" 2>&1 &
        local frontend_pid=$!
        write_pid "$FRONTEND_PID_FILE" "$frontend_pid"
        echo "Frontend started (PID: ${frontend_pid})."
    fi

    echo ""
    echo "Services starting..."
    echo "  Backend:  http://${BACKEND_HOST}:${BACKEND_PORT}"
    echo "  Frontend: http://localhost:${FRONTEND_PORT}"
    echo ""
    echo "Use '$0 status' to check if services are running."
    echo "Use '$0 logs' to view live logs."
}

cmd_stop() {
    ensure_dirs

    echo "Stopping Tadpole Studio..."
    echo ""

    stop_service "Backend" "$BACKEND_PID_FILE" "$BACKEND_LOG"
    stop_service "Frontend" "$FRONTEND_PID_FILE" "$FRONTEND_LOG"

    echo ""
    echo "All services stopped."
}

cmd_status() {
    ensure_dirs

    echo "Tadpole Studio Status:"
    echo "======================"
    echo ""

    # Check backend
    if is_running "$BACKEND_PID_FILE"; then
        local backend_pid
        backend_pid=$(cat "$BACKEND_PID_FILE")
        echo "Backend:   RUNNING (PID: ${backend_pid}) - http://${BACKEND_HOST}:${BACKEND_PORT}"
    else
        echo "Backend:   STOPPED"
    fi

    # Check frontend
    if is_running "$FRONTEND_PID_FILE"; then
        local frontend_pid
        frontend_pid=$(cat "$FRONTEND_PID_FILE")
        echo "Frontend:  RUNNING (PID: ${frontend_pid}) - http://localhost:${FRONTEND_PORT}"
    else
        echo "Frontend:  STOPPED"
    fi

    echo ""

    # Also check if processes are actually listening on the expected ports
    if command -v ss &>/dev/null; then
        echo "Port status:"
        echo "  Backend port ${BACKEND_PORT}:  $(ss -tlnp 2>/dev/null | grep -q ":${BACKEND_PORT} " && echo 'LISTENING' || echo 'NOT LISTENING')"
        echo "  Frontend port ${FRONTEND_PORT}: $(ss -tlnp 2>/dev/null | grep -q ":${FRONTEND_PORT} " && echo 'LISTENING' || echo 'NOT LISTENING')"
    elif command -v netstat &>/dev/null; then
        echo "Port status:"
        echo "  Backend port ${BACKEND_PORT}:  $(netstat -tlnp 2>/dev/null | grep -q ":${BACKEND_PORT} " && echo 'LISTENING' || echo 'NOT LISTENING')"
        echo "  Frontend port ${FRONTEND_PORT}: $(netstat -tlnp 2>/dev/null | grep -q ":${FRONTEND_PORT} " && echo 'LISTENING' || echo 'NOT LISTENING')"
    fi
}

cmd_restart() {
    echo "Restarting Tadpole Studio..."
    echo ""
    cmd_stop
    # Small delay to ensure ports are released
    sleep 2
    cmd_start
}

cmd_logs() {
    ensure_dirs

    local service="${1:-all}"

    case "$service" in
        backend)
            if [[ -f "$BACKEND_LOG" ]]; then
                tail -f "$BACKEND_LOG"
            else
                echo "No backend log file found at ${BACKEND_LOG}"
            fi
            ;;
        frontend)
            if [[ -f "$FRONTEND_LOG" ]]; then
                tail -f "$FRONTEND_LOG"
            else
                echo "No frontend log file found at ${FRONTEND_LOG}"
            fi
            ;;
        all)
            if [[ -f "$BACKEND_LOG" ]] || [[ -f "$FRONTEND_LOG" ]]; then
                echo "Following logs (Ctrl+C to stop)..."
                echo ""
                if [[ -f "$BACKEND_LOG" ]]; then
                    echo "=== Backend Logs ==="
                    tail -f "$BACKEND_LOG"
                fi
                echo ""
                if [[ -f "$FRONTEND_LOG" ]]; then
                    echo "=== Frontend Logs ==="
                    tail -f "$FRONTEND_LOG"
                fi
            else
                echo "No log files found in ${LOGS_DIR}"
                echo "Start services first with '$0 start'"
            fi
            ;;
        *)
            echo "ERROR: Unknown service '${service}'"
            echo "Valid options: backend, frontend, all"
            exit 1
            ;;
    esac
}

# ── Main ─────────────────────────────────────────────────────────────────

case "${1:-}" in
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    status)
        cmd_status
        ;;
    restart)
        cmd_restart
        ;;
    logs)
        cmd_logs "${2:-all}"
        ;;
    *)
        usage
        ;;
esac
