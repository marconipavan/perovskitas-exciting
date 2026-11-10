#!/usr/bin/env bash
# Apaga arquivos grandes e recalculaveis de uma pasta de calculo.
set -euo pipefail

PASTA=""
APAGAR=0
TUDO=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apagar)  APAGAR=1; shift ;;
        --tudo)    TUDO=1;   shift ;;
        -h|--help) echo "uso: limpar-runs.sh PASTA [--apagar] [--tudo]"; exit 0 ;;
        -*)        echo "argumento desconhecido: $1" >&2; exit 2 ;;
        *)         PASTA="$1"; shift ;;
    esac
done

[[ -n "$PASTA" ]] || { echo "ERRO: informe a pasta. Veja --help." >&2; exit 1; }
[[ -d "$PASTA" ]] || { echo "ERRO: pasta nao existe: $PASTA" >&2; exit 1; }

PADROES=(EVECFV*.OUT EVECSV*.OUT EVALFV*.OUT APWCMT*.OUT LOCMT*.OUT PMAT*.OUT)
PASTAS_INT=(EMATRAD EPS0 SCREEN GQPOINTS)

PADROES_RESTART=(STATE.OUT EXCLI_*.OUT SCCLI_*.OUT)

encontra() {
    local -a expr=()
    for p in "${PADROES[@]}"; do expr+=(-name "$p" -o); done
    (( TUDO )) && for p in "${PADROES_RESTART[@]}"; do expr+=(-name "$p" -o); done
    unset 'expr[${#expr[@]}-1]'
    find "$PASTA" -type f \( "${expr[@]}" \) -print0
    for d in "${PASTAS_INT[@]}"; do
        find "$PASTA" -type d -name "$d" -print0
    done
}

TOTAL=0
N=0
while IFS= read -r -d '' alvo; do
    tam=$(du -sb "$alvo" | cut -f1)
    TOTAL=$(( TOTAL + tam ))
    N=$(( N + 1 ))
    printf '  %8.1f MB  %s\n' "$(python3 -c "print($tam/1e6)")" "${alvo#$PASTA/}"
    (( APAGAR )) && rm -rf "$alvo"
done < <(encontra)

echo
if (( N == 0 )); then
    echo "[limpar] nada a apagar em $PASTA"
    exit 0
fi
printf '[limpar] %d itens, %.1f MB\n' "$N" "$(python3 -c "print($TOTAL/1e6)")"
(( TUDO )) && echo "[limpar] modo --tudo: restart (STATE.OUT/EXCLI/SCCLI) incluido"

if (( APAGAR )); then
    echo "[limpar] APAGADOS."
else
    echo "[limpar] nada foi apagado (dry-run). Para apagar de verdade: --apagar"
fi
