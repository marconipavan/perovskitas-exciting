#!/usr/bin/env bash
# Roda o exciting a partir das tasks do VS Code.
set -euo pipefail

IC="${IC_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SRC="$PWD"
OUT=""
MODE="smp"
NPROC=2
NTHREADS=1
COPY_STATE=auto
CRONOMETRO=auto
REUSAR=0
EXTRA=()

RESTART_FILES=(STATE.OUT EFERMI.OUT OCCSV.OUT EVALCORE.OUT LINENGY.OUT)

while [[ $# -gt 0 ]]; do
    case "$1" in
        --src)        SRC="$2";      shift 2 ;;
        --out)        OUT="$2";      shift 2 ;;
        --mpi)        MODE="mpi";    shift   ;;
        -n|--np)      NPROC="$2";    shift 2 ;;
        -t|--threads) NTHREADS="$2"; shift 2 ;;
        --copy)       EXTRA+=("$2"); shift 2 ;;
        --no-state)   COPY_STATE=no; shift   ;;
        --reusar)     REUSAR=1;      shift   ;;
        --cronometro)     CRONOMETRO=sim; shift ;;
        --sem-cronometro) CRONOMETRO=nao; shift ;;
        -h|--help)    echo "uso: run-exciting-task.sh --src DIR [--out NOME] [--mpi] [-n NPROC] [-t NTHREADS]"; exit 0 ;;
        *)            echo "argumento desconhecido: $1" >&2; exit 2 ;;
    esac
done

[[ -d "$SRC" ]]           || { echo "ERRO: pasta nao existe: $SRC" >&2; exit 1; }
[[ -f "$SRC/input.xml" ]] || { echo "ERRO: nao ha input.xml em $SRC" >&2; exit 1; }

OUT="${OUT#./}"
OUT="${OUT%/}"

case "$OUT" in
    ""|"."|"-") WORKDIR="$SRC" ;;
    /*)  echo "ERRO: --out deve ser um nome relativo, nao um caminho absoluto: $OUT" >&2; exit 1 ;;
    *..*) echo "ERRO: --out nao pode conter '..': $OUT" >&2; exit 1 ;;
    *)   WORKDIR="$SRC/$OUT" ;;
esac

NEEDS_STATE=0
if [[ "$COPY_STATE" == "auto" ]] && grep -qE 'do[[:space:]]*=[[:space:]]*"skip"' "$SRC/input.xml"; then
    NEEDS_STATE=1
    if [[ ! -f "$SRC/STATE.OUT" ]]; then
        echo "ERRO: o input tem groundstate do=\"skip\", mas nao ha STATE.OUT em" >&2
        echo "      $SRC" >&2
        echo "      Rode o groundstate primeiro (do=\"fromscratch\") ou use --no-state." >&2
        exit 1
    fi
fi

if [[ "$WORKDIR" != "$SRC" ]]; then
    if [[ -e "$WORKDIR" ]] && [[ -n "$(ls -A "$WORKDIR" 2>/dev/null)" ]]; then
        if (( ! REUSAR )); then
            echo "ERRO: $WORKDIR ja existe e nao esta vazia." >&2
            echo "      Para rodar DE NOVO nela, aproveitando o que ja foi calculado," >&2
            echo "      use --reusar (task \"exciting MPI (reaproveitar pasta calculada)\")." >&2
            echo "      Para comecar do zero: rm -rf '$WORKDIR'" >&2
            exit 1
        fi
        if [[ -f "$WORKDIR/input.xml" ]] && ! cmp -s "$SRC/input.xml" "$WORKDIR/input.xml"; then
            cp "$WORKDIR/input.xml" "$WORKDIR/input.xml.anterior"
            echo "[task] input.xml anterior salvo como input.xml.anterior"
        fi
        echo "[task] reaproveitando $WORKDIR (nada foi apagado)"
    fi

    NOVA=1
    [[ -d "$WORKDIR" ]] && NOVA=0
    mkdir -p "$WORKDIR"
    cp "$SRC/input.xml" "$WORKDIR/input.xml"
    (( NOVA )) && echo "[task] pasta criada: $WORKDIR"

    SPECIESPATH="$(grep -om1 'speciespath="[^"]*"' "$SRC/input.xml" \
                   | sed 's/^speciespath="//; s/"$//' || true)"

    case "$SPECIESPATH" in
        ""|"."|"./")
            n=0
            while IFS= read -r sp; do
                if [[ -f "$SRC/$sp" ]]; then
                    cp "$SRC/$sp" "$WORKDIR/"
                    n=$((n + 1))
                fi
            done < <(grep -o 'speciesfile="[^"]*"' "$SRC/input.xml" \
                     | sed 's/^speciesfile="//; s/"$//' | sort -u)
            (( n > 0 )) && echo "[task] $n arquivo(s) de species copiado(s)"
            ;;
        /*|'$'*)
            ;;
        *)
            sed -i "s|speciespath=\"$SPECIESPATH\"|speciespath=\"../$SPECIESPATH\"|" \
                "$WORKDIR/input.xml"
            echo "[task] speciespath ajustado: $SPECIESPATH -> ../$SPECIESPATH"
            ;;
    esac

    if (( NEEDS_STATE )); then
        copied=()
        for f in "${RESTART_FILES[@]}"; do
            [[ -f "$SRC/$f" ]] && { cp "$SRC/$f" "$WORKDIR/"; copied+=("$f"); }
        done
        echo "[task] do=\"skip\" detectado -> restart copiado: ${copied[*]}"
    fi

    for f in ${EXTRA+"${EXTRA[@]}"}; do
        if [[ -e "$SRC/$f" ]]; then
            cp -r "$SRC/$f" "$WORKDIR/"
            echo "[task] copiado: $f"
        else
            echo "AVISO: --copy '$f' nao existe em $SRC" >&2
        fi
    done
fi

cd "$WORKDIR"

executa() {
    if [[ "$MODE" == "mpi" ]]; then
        "$IC/bin/run-exciting-mpi.sh" -n "$NPROC" -t "$NTHREADS"
    else
        export APPTAINERENV_OMP_NUM_THREADS="$NTHREADS"
        export APPTAINERENV_OPENBLAS_NUM_THREADS="$NTHREADS"
        echo "[task] SMP com OMP_NUM_THREADS=$NTHREADS"
        echo "[task] dir: $WORKDIR"
        "$IC/bin/run-exciting.sh"
    fi
}

[[ "$CRONOMETRO" == "auto" ]] && { [[ -t 1 ]] && CRONOMETRO=sim || CRONOMETRO=nao; }

if [[ "$CRONOMETRO" != "sim" ]]; then
    exec_rc=0
    executa || exec_rc=$?
    exit $exec_rc
fi

hhmmss() { printf '%02d:%02d:%02d' $(( $1 / 3600 )) $(( $1 % 3600 / 60 )) $(( $1 % 60 )); }

progresso() {
    if [[ -f INFOXS.OUT ]]; then
        local etapa
        etapa="$(grep 'Info(' INFOXS.OUT | tail -1)"
        [[ -n "$etapa" ]] && { printf '%s' "${etapa:0:60}"; return; }
    fi
    if [[ -f INFO.OUT ]]; then
        local n=0
        n="$(grep -c '^ Total energy  ' INFO.OUT 2>/dev/null)" || n=0
        (( n > 0 )) && { printf 'SCF: %d iteracoes' "$n"; return; }
    fi
    printf 'iniciando'
}

INICIO=$SECONDS

set -m
executa < /dev/null &
FILHO=$!
set +m

encerra() {
    if ! kill -0 "$FILHO" 2>/dev/null; then
        trap - INT TERM
        return
    fi
    kill -TERM -- -"$FILHO" 2>/dev/null || kill -TERM "$FILHO" 2>/dev/null || true
    sleep 1
    kill -KILL -- -"$FILHO" 2>/dev/null || true
    printf '\r\033[K[task] interrompido apos %s - %s\n' \
        "$(hhmmss $(( SECONDS - INICIO )))" "$WORKDIR"
    exit 130
}
trap encerra INT TERM

while kill -0 "$FILHO" 2>/dev/null; do
    printf '\r\033[K[task] %s · %s' "$(hhmmss $(( SECONDS - INICIO )))" "$(progresso)"
    sleep 1
done

trap - INT TERM
RC=0
wait "$FILHO" || RC=$?
TOTAL=$(( SECONDS - INICIO ))
printf '\r\033[K'
if (( RC == 0 )); then
    echo "[task] terminou em $(hhmmss $TOTAL) ($TOTAL s) - $WORKDIR"
else
    echo "[task] FALHOU depois de $(hhmmss $TOTAL) (codigo $RC) - $WORKDIR"
fi
exit $RC
