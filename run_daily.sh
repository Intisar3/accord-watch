#!/usr/bin/env bash
# Headless daily run for macOS / Linux (cron or launchd).
cd "$(dirname "$0")"
mkdir -p logs
claude -p "/daily-run" --permission-mode acceptEdits >> "logs/$(date +%F).log" 2>&1
