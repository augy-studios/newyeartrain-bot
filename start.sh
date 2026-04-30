#!/usr/bin/env bash
# Launch bot in a named tmux session.
# Usage: ./start.sh [start|stop|restart|logs|attach]

SESSION="nyt-bot"
BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${BOT_DIR}/.venv/bin/python"

start() {
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "Session '$SESSION' already running."
        echo "  Attach: tmux attach -t $SESSION"
    else
        tmux new-session -d -s "$SESSION" -c "$BOT_DIR" \
            "source .venv/bin/activate && python bot.py; echo 'Process exited — press Enter'; read"
        echo "Started in tmux session '$SESSION'."
        echo "  Attach:  tmux attach -t $SESSION"
        echo "  Detach:  Ctrl+B then D"
    fi
}

stop() {
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        tmux kill-session -t "$SESSION"
        echo "Session '$SESSION' stopped."
    else
        echo "No session named '$SESSION' found."
    fi
}

case "${1:-start}" in
    start)   start ;;
    stop)    stop ;;
    restart) stop; sleep 1; start ;;
    logs)    tail -f "$BOT_DIR/bot.log" ;;
    attach)  tmux attach -t "$SESSION" ;;
    *)
        echo "Usage: $0 {start|stop|restart|logs|attach}"
        exit 1
        ;;
esac