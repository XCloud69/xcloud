#!/bin/bash

SESSION="xcloud_env"

tmux has-session -t $SESSION 2>/dev/null

if [ $? != 0 ]; then
    tmux new-session -d -s $SESSION

    tmux send-keys -t $SESSION:1 "cd ~/Desktop/python/Xcloud/src" C-m
    tmux send-keys -t $SESSION:1 "source ../.venv/bin/activate" C-m
    tmux send-keys -t $SESSION:1 "nvim" C-m
    
    tmux new-window -t $SESSION
    tmux send-keys -t $SESSION:2 "cd ~/Desktop/python/Xcloud/" C-m
    tmux send-keys -t $SESSION:2 "source .venv/bin/activate" C-m
    tmux send-keys -t $SESSION:2 "export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$VIRTUAL_ENV/lib/python3.13/site-packages/nvidia/cublas/lib:$VIRTUAL_ENV/lib/python3.13/site-packages/nvidia/cudnn/lib" C-m
    tmux send-keys -t $SESSION:2 "python src/main.py" C-m
    
    
    tmux new-window -t $SESSION
    tmux send-keys -t $SESSION:3 "cd ~/Desktop/python/Xcloud/" C-m
    tmux send-keys -t $SESSION:3 "lazygit" C-m
    
    tmux select-window -t $SESSION:1
fi

tmux attach-session -t $SESSION
