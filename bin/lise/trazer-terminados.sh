#!/usr/bin/env bash
# Traz do Lise todos os jobs registrados que ja terminaram.
source "$(dirname "${BASH_SOURCE[0]}")/comum.sh"

PARALELO="${1:-4}"
STATE="${2:---sem-state}"
[[ "$STATE" == --com-state || "$STATE" == --sem-state ]] || { echo "ERRO: opcao invalida: $STATE" >&2; exit 2; }
[[ "$PARALELO" =~ ^[1-9][0-9]*$ ]] || { echo "ERRO: numero de copias invalido: $PARALELO" >&2; exit 2; }

mapfile -t PENDENTES < <(awk -F'\t' 'NR > 1 && $7 != "trazido" && $7 != "duplicado" { print $2 " " $3 }' "$REGISTRO")
if [[ ${#PENDENTES[@]} -eq 0 ]]; then
    echo "Nada a trazer: todos os jobs registrados ja foram trazidos."
    exit 0
fi

CADEIAS="$(printf '%s\n' "${PENDENTES[@]}" | awk '$2 ~ /-bse$/ {print $2}' | sort -u | tr '\n' ' ')"

IDS="$(printf '%s\n' "${PENDENTES[@]}" | awk '{print $1}' | paste -sd,)"
SAIDA="$(no_lise <<EOF
for p in $CADEIAS; do
    echo "CADEIA \$p \$(tail -1 '$LISE_RUNS'/\$p/cadeia.txt 2>/dev/null | awk '{print \$2}')"
done
ULTIMAS="\$(for p in $CADEIAS; do tail -1 '$LISE_RUNS'/\$p/cadeia.txt 2>/dev/null | awk '{print \$2}'; done | paste -sd,)"
sacct -j $IDS\${ULTIMAS:+,\$ULTIMAS} -X -n -P -o JobID,State,Elapsed
EOF
)"
SITUACOES="$(grep -v '^CADEIA ' <<< "$SAIDA" || true)"
for i in "${!PENDENTES[@]}"; do
    read -r JOB PASTA <<< "${PENDENTES[$i]}"
    [[ "$PASTA" == *-bse ]] || continue
    ULTIMA="$(awk -v p="$PASTA" '$1 == "CADEIA" && $2 == p {print $3}' <<< "$SAIDA")"
    if [[ -n "$ULTIMA" ]]; then
        SIT="$(awk -F'|' -v j="$ULTIMA" '$1 == j {print $2 "|" $3}' <<< "$SITUACOES")"
        SITUACOES="$(awk -F'|' -v j="$JOB" '$1 != j' <<< "$SITUACOES")"$'\n'"$JOB|${SIT:-PENDING|}"
    fi
done

LOGS="$IC/.lise/trazer"
mkdir -p "$LOGS"
FILA=()
echo "[lise] jobs registrados ainda nao trazidos:"
for linha in "${PENDENTES[@]}"; do
    read -r JOB PASTA <<< "$linha"
    SIT="$(awk -F'|' -v j="$JOB" '$1 == j { print $2 " " $3 }' <<< "$SITUACOES")"
    case "$SIT" in
        ""|PENDING*|RUNNING*|CONFIGURING*|COMPLETING*|REQUEUED*)
            printf '  %-10s %-38s %s\n' "$JOB" "$PASTA" "${SIT:-?}  (fica para depois)"
            continue ;;
    esac
    LOCAL="$(python3 -c "import sys; sys.path.insert(0, '$IC/bin'); import leitura
p = leitura.acha_run('$PASTA'); print(p or '')")"
    if [[ -z "$LOCAL" ]]; then
        printf '  %-10s %-38s %s\n' "$JOB" "$PASTA" "$SIT  (pasta local nao encontrada!)"
        continue
    fi
    printf '  %-10s %-38s %s\n' "$JOB" "$PASTA" "$SIT  -> trazer"
    FILA+=("$JOB $LOCAL")
done

if [[ ${#FILA[@]} -eq 0 ]]; then
    echo; echo "Nenhum job terminado para trazer agora."
    exit 0
fi

echo
echo "[lise] trazendo ${#FILA[@]} pasta(s), ate $PARALELO ao mesmo tempo (logs em .lise/trazer/)..."
printf '%s\n' "${FILA[@]}" | xargs -P "$PARALELO" -L 1 bash -c '
    job="$1"; local="$2"
    if "'"$IC"'/bin/lise/trazer.sh" "$local" "'"$STATE"'" >"'"$LOGS"'/$job.log" 2>&1 < /dev/null; then
        echo "  ok    $job  $(basename "$local")"
    else
        echo "  ERRO  $job  $(basename "$local")  (ver .lise/trazer/$job.log)"
    fi' _

echo
echo "[lise] resumo"
for item in "${FILA[@]}"; do
    read -r JOB LOCAL <<< "$item"
    LOG="$LOGS/$JOB.log"
    echo "== $(basename "$LOCAL")   $(grep -m1 '^\[lise\] job' "$LOG" | sed 's/^\[lise\] //')"
    grep -E '^\[lise\] custo real|GAP|DIRETO|INDIRETO|^  [A-Za-z0-9._-]+ +[0-9.]+ eV' "$LOG" | sed 's/^/   /' || true
done
