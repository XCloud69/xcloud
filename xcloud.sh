#!/bin/bash

# Define the session name
SESSION="xcloud"

# Start a new tmux session in the background
tmux new-session -d -s $SESSION

# --- Setup Window 1 ---
tmux send-keys -t $SESSION:0 "cd ~/Desktop/python/Xcloud/src" C-m
tmux send-keys -t $SESSION:0 "source ../.venv/bin/activate" C-m
tmux send-keys -t $SESSION:0 "nvim" C-m

# --- Setup Window 2 ---
# Create a new window (index 1)
tmux new-window -t $SESSION
tmux send-keys -t $SESSION:1 "cd ~/Desktop/python/Xcloud/" C-m
tmux send-keys -t $SESSION:1 "source .venv/bin/activate" C-m
tmux send-keys -t $SESSION:1 "export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$VIRTUAL_ENV/lib/python3.13/site-packages/nvidia/cublas/lib:$VIRTUAL_ENV/lib/python3.13/site-packages/nvidia/cudnn/lib" C-m
tmux send-keys -t $SESSION:1 "python src/main.py" C-m


# --- Setup Window 3 ---
# Create a new window (index 2)
tmux new-window -t $SESSION
tmux send-keys -t $SESSION:2 "btop" C-m

# Select the first window so it's active upon attachment
tmux select-window -t $SESSION:0

# Attach to the session
tmux attach-session -t $SESSION
