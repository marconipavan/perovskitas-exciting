#!/usr/bin/env bash
# Traz do Lise os resultados de uma pasta de runs.
source "$(dirname "${BASH_SOURCE[0]}")/comum.sh"

[[ $# -ge 1 && $# -le 2 ]] || { echo "uso: trazer.sh runs/semana-NN/PASTA [--com-state]" >&2; exit 2; }
COM_STATE=0
case "${2:-}" in
    --com-state) COM_STATE=1 ;;
    ""|--sem-state) ;;
    *) echo "uso: trazer.sh runs/semana-NN/PASTA [--com-state]" >&2; exit 2 ;;
esac
REL="$(pasta_relativa "$1")"
REMOTA="$(remota "$REL")"
LOCAL="$IC/runs/$REL"

JOBID="$(awk -F'\t' -v p="$(nome_run "$REL")" 'NR > 1 && $3 == p { id = $2 } END { print id }' "$REGISTRO")"

if [[ -z "$JOBID" ]]; then
    echo "AVISO: nenhum job registrado para runs/$REL."
    if [[ -f "$LOCAL/INFO.OUT" ]]; then
        echo "       E esta pasta ja tem um INFO.OUT: pode ser um resultado LOCAL, que seria"
        echo "       sobrescrito pelo do Lise."
    fi
    read -r -p "Trazer mesmo assim? [s/N] " RESP
    [[ "$RESP" == [sS] ]] || { echo "Nada trazido."; exit 0; }
else
    INFO="$(no_lise <<EOF
ids="\$(awk '{print \$2}' '$REMOTA'/cadeia.txt 2>/dev/null | paste -sd,)"
sacct -j "\${ids:-$JOBID}" -X -n -P -o JobID,State,Elapsed,NNodes,Partition
EOF
)"
    ETAPAS="$(grep -c . <<< "$INFO" || true)"
    IFS='|' read -r _ SITUACAO GASTO NOS PART <<< "$(tail -1 <<< "$INFO")"
    if (( ETAPAS > 1 )); then
        echo "[lise] cadeia de $ETAPAS etapas (cadeia.txt):"
        while IFS='|' read -r J S E N P; do printf '         %-10s %-12s %s  %s no(s)\n' "$J" "$S" "$E" "$N"; done <<< "$INFO"
    fi
    echo "[lise] job $JOBID: ${SITUACAO:-?}, ${GASTO:-?}"
    case "$SITUACAO" in
        RUNNING*|PENDING*|CONFIGURING*|COMPLETING*)
            echo "AVISO: o job ainda nao terminou; o que vier agora e um retrato parcial."
            read -r -p "Trazer mesmo assim? [s/N] " RESP
            [[ "$RESP" == [sS] ]] || { echo "Nada trazido."; exit 0; }
            ;;
    esac
fi

EXCLUI=(--exclude='EVEC*' --exclude=input.xml --exclude=job.slurm)
EXCLUI+=(--exclude='APWCMT*' --exclude='APWDLM*' --exclude='LOCMT*' --exclude='LODLM*'
         --exclude='PMAT*' --exclude='EMAT*' --exclude='SCCLI*' --exclude='EXCLI*'
         --exclude='SCREEN/' --exclude='.*.OUT.??????')
(( COM_STATE )) || EXCLUI+=(--exclude=STATE.OUT)
INPUTS=()
for f in "$LOCAL/input.xml" "$LOCAL"/*/input.xml; do [[ -f "$f" ]] && INPUTS+=("$f"); done
if [[ ${#INPUTS[@]} -gt 0 ]]; then
    while IFS= read -r sp; do EXCLUI+=(--exclude="$sp"); done \
        < <(grep -ho 'speciesfile="[^"]*"' "${INPUTS[@]}" | sed 's/^speciesfile="//; s/"$//' | sort -u)
fi

echo "[lise] trazendo $LISE_HOST:$REMOTA  ->  runs/$REL"
if (( COM_STATE )); then
    echo "       (com o STATE.OUT)"
else
    echo "       (sem o STATE.OUT: fica no Lise; --com-state para trazer)"
fi
mkdir -p "$LOCAL"
rsync -av "${EXCLUI[@]}" "$LISE_HOST:$REMOTA/" "$LOCAL/"

if [[ -n "$JOBID" ]] && [[ "${SITUACAO:-}" =~ ^(RUNNING|PENDING|CONFIGURING|COMPLETING) ]]; then
    echo "[lise] job ainda na fila: o registro continua sem a marca de trazido"
elif [[ -n "$JOBID" ]]; then
    (
        flock 9
        awk -F'\t' -v OFS='\t' -v id="$JOBID" 'NR > 1 && $2 == id { $7 = "trazido" } { print }' \
            "$REGISTRO" > "$REGISTRO.tmp.$$" && mv "$REGISTRO.tmp.$$" "$REGISTRO"
    ) 9> "$REGISTRO.lock"
    if (( ETAPAS > 1 )); then
        TOTAL=0
        while IFS='|' read -r J S E N P; do
            read -r TAXA CORES ALOC <<< "$(taxa "$P")" || true
            [[ -n "${TAXA:-}" && -n "$E" ]] || continue
            TOTAL="$(awk -v s="$TOTAL" -v n="$N" -v h="$(horas "$E")" -v t="$TAXA" 'BEGIN{printf "%.1f", s + n*h*t}')"
        done <<< "$INFO"
        echo "[lise] custo real: $TOTAL core-h (as $ETAPAS etapas)"
    else
        read -r TAXA CORES ALOC <<< "$(taxa "${PART:-}")" || true
        if [[ -n "${TAXA:-}" && -n "${GASTO:-}" && "${ALOC:-}" == exclusiva ]]; then
            CUSTO="$(awk -v n="${NOS:-1}" -v h="$(horas "$GASTO")" -v t="$TAXA" 'BEGIN{printf "%.1f", n*h*t}')"
            echo "[lise] custo real: ${NOS:-1} no(s) x $GASTO x $TAXA = $CUSTO core-h"
        fi
    fi
fi

echo
echo "[lise] pos-processamento local"
python3 "$IC/bin/figuras.py" --src "$LOCAL" --silencioso || echo "AVISO: figuras.py falhou"
python3 "$IC/bin/indice-runs.py" > /dev/null || echo "AVISO: indice-runs.py falhou"
if [[ -f "$LOCAL/INFO.OUT" ]]; then
    python3 "$IC/bin/resultado.py" --src "$LOCAL" || true
else
    for d in "$LOCAL"/*/; do
        [[ -f "$d/INFO.OUT" ]] || continue
        printf '  %-24s ' "$(basename "$d")"
        python3 "$IC/bin/resultado.py" --src "$d" 2>/dev/null | awk '/GAP/{printf "%s %s  ", $3, $4} /DIRETO|INDIRETO/{print $1}' || echo "?"
    done
fi
