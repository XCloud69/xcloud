```bash
uv venv --python 3.11

uv pip install -e .
```

// to run
// uv run python src/main.py
/** */

Each time, run this from the project directory:
cd /home/mennabashir/Desktop/projects/xcloud/xcloud

uv run python src/main.py

That starts the server on http://localhost:8000 (it stays in the foreground; press Ctrl+C to stop). This is the command from your README.

If you want it to keep running in the background instead:
cd /home/mennabashir/Desktop/projects/xcloud/xcloud

setsid uv run python src/main.py > /tmp/xcloud.log 2>&1 < /dev/null &

Stop the background one with: pkill -f "src/main.py"

**/
