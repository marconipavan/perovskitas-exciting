#!/usr/bin/env bash
# Roda o exciting dentro do container.
set -euo pipefail

IC="${IC_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SIF="$IC/exciting-toolchain.sif"
INSTALL_DIR="$IC/build-farm/install-sodium"
EXC="$INSTALL_DIR/bin/exciting_mpismp"

export APPTAINERENV_LD_LIBRARY_PATH="$INSTALL_DIR/lib:/opt/openblas/lib:/usr/local/lib:/opt/openmpi/lib:${LD_LIBRARY_PATH:-}"

export APPTAINERENV_OMP_NUM_THREADS="${APPTAINERENV_OMP_NUM_THREADS:-${OMP_NUM_THREADS:-1}}"
export APPTAINERENV_OPENBLAS_NUM_THREADS="${APPTAINERENV_OPENBLAS_NUM_THREADS:-${OMP_NUM_THREADS:-1}}"

exec apptainer exec "$SIF" "$EXC" "$@"
