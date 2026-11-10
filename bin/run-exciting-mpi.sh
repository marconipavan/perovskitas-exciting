#!/usr/bin/env bash
# Roda o exciting com MPI dentro do container.
set -euo pipefail

IC="${IC_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SIF="$IC/exciting-toolchain.sif"
INSTALL_DIR="$IC/build-farm/install-sodium"
EXC="$INSTALL_DIR/bin/exciting_mpismp"

NPROC=4
NTHREADS=""
PHYS_CORES=8

while [[ $# -gt 0 ]]; do
    case "$1" in
        -n|--np)      NPROC="$2";    shift 2 ;;
        -t|--threads) NTHREADS="$2"; shift 2 ;;
        --)           shift; break ;;
        -h|--help)    echo "uso: run-exciting-mpi.sh [-n NPROC] [-t NTHREADS] [-- ARGUMENTOS_DO_MPIRUN]"; exit 0 ;;
        *)            break ;;
    esac
done

if [[ -z "$NTHREADS" ]]; then
    NTHREADS=$(( PHYS_CORES / NPROC ))
    (( NTHREADS < 1 )) && NTHREADS=1
fi

[[ -f input.xml ]] || { echo "ERRO: nao ha input.xml em $(pwd)"; exit 1; }
[[ -x "$EXC" ]]    || { echo "ERRO: binario nao encontrado: $EXC"; exit 1; }

echo "[run-exciting-mpi] $NPROC ranks MPI x $NTHREADS threads OMP  (carga = $((NPROC*NTHREADS)))"
echo "[run-exciting-mpi] dir: $(pwd)"

export APPTAINERENV_LD_LIBRARY_PATH="$INSTALL_DIR/lib:/opt/openblas/lib:/usr/local/lib:/opt/openmpi/lib:${LD_LIBRARY_PATH:-}"

OVERSUB=()
if (( NPROC > PHYS_CORES )); then
    echo "[run-exciting-mpi] AVISO: $NPROC ranks > $PHYS_CORES nucleos fisicos -> --oversubscribe"
    OVERSUB=(--oversubscribe)
fi

exec apptainer exec "$SIF" \
    mpirun -np "$NPROC" "${OVERSUB[@]}" \
        --map-by "socket:PE=$NTHREADS" --bind-to core \
        -x OMP_NUM_THREADS="$NTHREADS" \
        -x OPENBLAS_NUM_THREADS="$NTHREADS" \
        -x OMP_PLACES=cores \
        -x OMP_PROC_BIND=close \
        "$EXC" "$@"
