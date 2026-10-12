#!/bin/sh
set -eu

mkdir -p /app/uploads
chown appuser:appuser /app/uploads

exec gosu appuser "$@"
