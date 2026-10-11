#!/usr/bin/env bash
# Run the whole pipeline in order. Stops at the first failure.
set -euo pipefail
cd "$(dirname "$0")"

echo "=== 1/9 load_data ==="       && python load_data.py
echo "=== 2/9 clean ==="           && python clean.py
echo "=== 3/9 seasonality ==="     && python seasonality.py
echo "=== 4/9 lifecycle ==="       && python lifecycle.py
echo "=== 5/9 lebaran_effect ==="  && python lebaran_effect.py
echo "=== 6/9 lag_analysis (exploratory) ===" && python lag_analysis.py
echo "=== 7/9 forecast ==="        && python forecast.py
echo "=== 8/9 trend_radar ==="     && python trend_radar.py
echo "=== 9/9 check_json_v2 ==="   && python check_json_v2.py
echo "=== ALL OK ==="