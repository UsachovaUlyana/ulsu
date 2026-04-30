#!/usr/bin/env bash
set -euo pipefail

# Полная матрица: 4 размера x 3 интенсивности x 2 профиля x repeats
python benchmark.py matrix \
  --brokers "rabbitmq,redis" \
  --msg-sizes "128,1024,10240,102400" \
  --rates "1000,5000,10000" \
  --duration 120 \
  --repeats 3 \
  --producers 2 \
  --consumers 2 \
  --output-dir results
