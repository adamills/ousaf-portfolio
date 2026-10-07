#!/data/data/com.termux/files/usr/bin/sh
# Auto-starts Postgres + the landing page server whenever the phone boots.
# Termux:Boot runs this automatically from ~/.termux/boot/
#
# Flask runs inside a detached tmux session named "ousaf-server" so you can
# reattach anytime to see live logs or debug issues:
#   tmux attach -t ousaf-server
# Detach again without killing it: press Ctrl+B, then D

termux-wake-lock

PROJECT_DIR="/data/data/com.termux/files/home/projects/ousaf-landing"
PGDATA="$PREFIX/var/lib/postgresql"

# Start Postgres if it isn't already running
pg_ctl -D "$PGDATA" -l "$PGDATA/log" start

# Give Postgres a moment to finish starting before Flask tries to connect
sleep 3

# Kill any stale tmux session with the same name so restarts don't collide
tmux kill-session -t ousaf-server 2>/dev/null

tmux new-session -d -s ousaf-server "cd $PROJECT_DIR && python3 app.py"
