#!/bin/bash
# Keep the resumable v2 generator running until every document is done (or 20 restarts).
cd "$(dirname "$0")/.."
set -a; . /Users/majjir/muse-shield/.env; set +a
for i in $(seq 1 20); do
  echo "=== run $i $(date +%H:%M:%S)" >> runs/synth/v2/generate.log
  SYNTH_API_CONCURRENCY=24 PYTHONPATH=$PWD /Users/majjir/muse-shield/.venv/bin/python -m muse_shield.synth scale \
    --sectors ma_legal,healthcare,ecommerce,admin --train-docs 400 --test-docs 75 --workers 24 --out $PWD/runs/synth/v2 >> runs/synth/v2/generate.log 2>&1
  done_n=$(wc -l < runs/synth/v2/done.jsonl)
  echo "=== run $i exited $? with $done_n done" >> runs/synth/v2/generate.log
  [ "$done_n" -ge 1900 ] && break
  sleep 30
done
echo "=== generator loop finished $(date +%H:%M:%S)" >> runs/synth/v2/generate.log
