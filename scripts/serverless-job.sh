#!/usr/bin/env bash
# Run one migration the way a Nebius Serverless Job would.
# Usage: ./scripts/serverless-job.sh request.json out/
set -euo pipefail
cd "$(dirname "$0")/.."
python -m polyglot.jobs.entrypoint "${1:?request.json}" "${2:?out dir}"
