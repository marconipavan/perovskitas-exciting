#!/usr/bin/env bash
# Ambiente para seguir os tutoriais Jupyter do exciting.

IC="${IC_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
export EXCITINGROOT="$IC/exciting"
export PATH="$EXCITINGROOT/bin:$EXCITINGROOT/tools/tutorial_scripts:$PATH"
export TIMEFORMAT="   Elapsed time = %0lR"
ulimit -s unlimited 2>/dev/null || true

_venv="$EXCITINGROOT/tools/excitingjupyter/venv/excitingvenv/bin/activate"
if [ -f "$_venv" ]; then
    source "$_venv"
    echo "[exciting-tutorials-env] EXCITINGROOT=$EXCITINGROOT"
    echo "[exciting-tutorials-env] venv ativo: $(python -c 'import sys; print(sys.prefix)')"
else
    echo "[exciting-tutorials-env] AVISO: venv nao encontrado em $_venv"
    echo "[exciting-tutorials-env] Rode primeiro: cd \$EXCITINGROOT/tools/excitingjupyter && source create_env.sh"
fi
unset _venv
