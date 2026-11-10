#!/usr/bin/env bash
# Copia uma figura para a pasta da semana e devolve o Markdown.
set -euo pipefail

REGISTROS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIG=""
LEGENDA=""
SEMANA=""
APPEND=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--figura)  FIG="$2";     shift 2 ;;
        -l|--legenda) LEGENDA="$2"; shift 2 ;;
        -s|--semana)  SEMANA="$2";  shift 2 ;;
        -a|--append)  APPEND=1;     shift   ;;
        -h|--help)    echo "uso: add-figura.sh -f FIGURA.png -l LEGENDA"; exit 0 ;;
        *)            echo "argumento desconhecido: $1" >&2; exit 2 ;;
    esac
done

[[ -n "$FIG" ]]  || { echo "ERRO: falta -f CAMINHO-DA-FIGURA" >&2; exit 1; }
[[ -f "$FIG" ]]  || { echo "ERRO: figura nao existe: $FIG" >&2; exit 1; }

if [[ -n "$SEMANA" ]]; then
    PASTA="$REGISTROS/semana-$(printf '%02d' "$SEMANA")"
else
    PASTA="$(find "$REGISTROS" -maxdepth 1 -type d -name 'semana-*' | sort | tail -1)"
fi
[[ -n "$PASTA" && -d "$PASTA" ]] || {
    echo "ERRO: nenhuma pasta de semana encontrada. Rode nova-semana.sh antes." >&2
    exit 1
}

mkdir -p "$PASTA/figuras"
NOME="$(basename "$FIG")"
DESTINO="$PASTA/figuras/$NOME"

if [[ -e "$DESTINO" ]] && ! cmp -s "$FIG" "$DESTINO"; then
    BASE="${NOME%.*}"; EXT="${NOME##*.}"
    i=2
    while [[ -e "$PASTA/figuras/$BASE-$i.$EXT" ]]; do i=$(( i + 1 )); done
    NOME="$BASE-$i.$EXT"
    DESTINO="$PASTA/figuras/$NOME"
fi

cp "$FIG" "$DESTINO"
echo "[registro] figura copiada: ${DESTINO#$REGISTROS/}" >&2

TRECHO="![${LEGENDA}](figuras/${NOME})"
[[ -n "$LEGENDA" ]] && TRECHO="$TRECHO
*${LEGENDA}*"

if (( APPEND )); then
    printf '\n%s\n' "$TRECHO" >> "$PASTA/REGISTRO.md"
    echo "[registro] trecho acrescentado ao fim de ${PASTA#$REGISTROS/}/REGISTRO.md" >&2
else
    echo "$TRECHO"
fi
