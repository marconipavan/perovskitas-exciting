#!/usr/bin/env bash
# Mede a escalabilidade MPI do exciting.
set -euo pipefail

IC="${IC_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RUNNER="$IC/bin/run-exciting-mpi.sh"

NTHREADS=1
LIST="1 2 4 8"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -t|--threads) NTHREADS="$2"; shift 2 ;;
        -l|--list)    LIST="$2";     shift 2 ;;
        -h|--help)    echo "uso: bench-exciting-mpi.sh [-t NTHREADS] [-l LISTA_DE_NPROC]"; exit 0 ;;
        *) echo "opcao desconhecida: $1"; exit 1 ;;
    esac
done

[[ -f input.xml ]] || { echo "ERRO: rode dentro da pasta que contem input.xml"; exit 1; }

BASE="$(pwd)"
OUT="$BASE/scaling.dat"
: > "$OUT"
printf "# nproc nthreads tempo_s speedup eficiencia\n" >> "$OUT"

T1=""
for NP in $LIST; do
    DIR="$BASE/np$NP"
    rm -rf "$DIR"; mkdir -p "$DIR"
    cp "$BASE"/*.xml "$DIR"/ 2>/dev/null || true
    rm -f "$DIR"/geometry.xml "$DIR"/info.xml "$DIR"/eigval.xml "$DIR"/atoms.xml "$DIR"/dos.xml

    echo "=============================================="
    echo ">>> $NP rank(s) MPI x $NTHREADS thread(s) OMP"
    cd "$DIR"

    START=$(date +%s.%N)
    if ! "$RUNNER" -n "$NP" -t "$NTHREADS" > run.log 2>&1; then
        echo "    FALHOU - ver $DIR/run.log"
        cd "$BASE"; continue
    fi
    END=$(date +%s.%N)
    cd "$BASE"

    T=$(echo "$END - $START" | bc)
    [[ -z "$T1" ]] && T1="$T"
    SPEEDUP=$(echo "scale=3; $T1 / $T" | bc)
    EFF=$(echo "scale=3; 100 * $SPEEDUP / $NP" | bc)

    printf "%5d %8d %8.2f %8.3f %8.1f\n" "$NP" "$NTHREADS" "$T" "$SPEEDUP" "$EFF" | tee -a "$OUT"
done

echo
echo "=============================================="
echo "Resultado em: $OUT"
column -t "$OUT"
