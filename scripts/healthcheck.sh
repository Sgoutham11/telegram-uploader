#!/bin/sh
set -eu
test -f /data/state/health.json
python -c 'import json,os,shutil,time; p="/data/state/health.json"; d=json.load(open(p)); assert time.time()-os.path.getmtime(p)<40; assert d["telegram_connected"] and d["workers_alive"] and d["queue_manager_alive"]; assert os.access("/data/state",os.W_OK); assert shutil.which("rclone")'

