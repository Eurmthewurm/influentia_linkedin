#!/usr/bin/env python3
"""
Subprocess helper: posts a single Reddit comment.
Uses get_reddit_client() (prefers saved-session API, no Playwright needed).
Job details are read from .reddit_pending_job.json.
"""
import sys, os, json

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)
os.chdir(script_dir)

# Force-load credentials from .env, overriding any stale parent-process env vars
_env_path = os.path.join(script_dir, '.env')
if os.path.exists(_env_path):
    with open(_env_path) as _ef:
        for _line in _ef:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _, _v = _line.partition('=')
                os.environ[_k.strip()] = _v.strip()

job_file = os.path.join(script_dir, ".reddit_pending_job.json")
with open(job_file) as f:
    job = json.load(f)

entry_id     = job["entry_id"]
post_fullname = job["post_fullname"]
text         = job["text"]

from reddit_client import get_reddit_client
from state_manager import load_state, save_state
from reddit_signal import mark_reddit_comment

client = get_reddit_client()

try:
    comment_fullname = client.post_comment(post_fullname, text)
    print(comment_fullname)

    state = load_state()
    # Store the real fullname before marking as posted
    for c in state.get("reddit_pending_comments", []):
        if c["id"] == entry_id:
            c["comment_fullname"] = comment_fullname
            break
    mark_reddit_comment(state, entry_id, "posted", text)
    save_state(state)
finally:
    try:
        os.remove(job_file)
    except Exception:
        pass
    client.close()
