#!/usr/bin/env bash
# Cria a pasta da semana seguinte a partir do modelo.
set -euo pipefail

REGISTROS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$REGISTROS/_template/REGISTRO.md"
INDICE="$REGISTROS/README.md"

DATA="$(date +%F)"
NUMERO=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -d|--data)   DATA="$2";   shift 2 ;;
        -n|--numero) NUMERO="$2"; shift 2 ;;
        -h|--help)   echo "uso: nova-semana.sh [--data AAAA-MM-DD] [--numero N]"; exit 0 ;;
        *)           echo "argumento desconhecido: $1" >&2; exit 2 ;;
    esac
done

[[ -f "$TEMPLATE" ]] || { echo "ERRO: template nao encontrado: $TEMPLATE" >&2; exit 1; }
date -d "$DATA" >/dev/null 2>&1 || { echo "ERRO: data invalida: $DATA" >&2; exit 1; }

if [[ -z "$NUMERO" ]]; then
    ULTIMA=0
    for d in "$REGISTROS"/semana-*/; do
        [[ -d "$d" ]] || continue
        n="$(basename "$d")"; n="${n#semana-}"; n="${n#0}"
        [[ "$n" =~ ^[0-9]+$ ]] && (( n > ULTIMA )) && ULTIMA="$n"
    done
    NUMERO=$(( ULTIMA + 1 ))
fi
NUMERO_FMT="$(printf '%02d' "$NUMERO")"

PASTA="$REGISTROS/semana-$NUMERO_FMT"
if [[ -e "$PASTA" ]]; then
    echo "ERRO: $PASTA ja existe." >&2
    echo "      Use --numero para outro numero, ou apague a pasta." >&2
    exit 1
fi

INI="$(date -d "$DATA -$(( ($(date -d "$DATA" +%u) - 1) )) days" +%F)"
FIM="$(date -d "$INI +6 days" +%F)"

mkdir -p "$PASTA/figuras" "$PASTA/dados"
sed -e "s|{{SEMANA}}|$NUMERO_FMT|g" \
    -e "s|{{DATA_INI}}|$(date -d "$INI" +%d/%m)|g" \
    -e "s|{{DATA_FIM}}|$(date -d "$FIM" +%d/%m)|g" \
    -e "s|{{ANO}}|$(date -d "$INI" +%Y)|g" \
    "$TEMPLATE" > "$PASTA/REGISTRO.md"

cat > "$PASTA/rascunho.txt" <<FIM_RASCUNHO
RASCUNHO - semana $NUMERO_FMT ($(date -d "$INI" +%d/%m) a $(date -d "$FIM" +%d/%m))

--- o que fiz ---

--- duvidas ---

FIM_RASCUNHO

if [[ -f "$INDICE" ]] && grep -q '^| semana |' "$INDICE"; then
    LINHA="| [semana-$NUMERO_FMT](semana-$NUMERO_FMT/REGISTRO.md) | $(date -d "$INI" +%d/%m) a $(date -d "$FIM" +%d/%m) | | pendente |"
    awk -v linha="$LINHA" '
        /^\| semana \|/ { cab = 1 }
        cab && !inserido && /^\|---/ { print; print linha; inserido = 1; next }
        { print }
    ' "$INDICE" > "$INDICE.tmp" && mv "$INDICE.tmp" "$INDICE"
    echo "[registro] indice atualizado: $INDICE"
fi

echo "[registro] semana $NUMERO_FMT criada: $PASTA"
echo "[registro] rascunho.txt criado para anotacoes soltas"
echo "[registro] periodo: $(date -d "$INI" +%d/%m/%Y) a $(date -d "$FIM" +%d/%m/%Y)"
echo "$PASTA/REGISTRO.md"
