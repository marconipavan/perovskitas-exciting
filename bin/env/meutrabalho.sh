#!/usr/bin/env bash
# Ambiente para rodar o exciting local fora dos tutoriais.

IC="${IC_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export EXCITINGROOT="$IC/exciting"
export PATH="$EXCITINGROOT/bin:$PATH"
ulimit -s unlimited 2>/dev/null || true

echo "[exciting-meutrabalho-env] EXCITINGROOT=$EXCITINGROOT"
