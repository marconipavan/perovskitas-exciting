#!/usr/bin/env bash
# Apaga no Lise os arquivos SCCLI e EXCLI de um BSE terminado e ja trazido.
source "$(dirname "${BASH_SOURCE[0]}")/comum.sh"

[[ $# -ge 1 && $# -le 2 ]] || { echo "uso: limpar.sh runs/semana-NN/PASTA [--lista]" >&2; exit 2; }
LISTA=0
case "${2:-}" in
    --lista) LISTA=1 ;;
    "") ;;
    *) echo "uso: limpar.sh runs/semana-NN/PASTA [--lista]" >&2; exit 2 ;;
esac
REL="$(pasta_relativa "$1")"
NOME="$(nome_run "$REL")"
REMOTA="$(remota "$REL")"
LOCAL="$IC/runs/$REL"
[[ "$NOME" =~ ^[A-Za-z0-9._-]+$ && -n "$LISE_RUNS" ]] || { echo "ERRO: nome de pasta invalido: $NOME" >&2; exit 1; }

for tipo in EPSILON EXCITON; do
    for oc in OC11 OC22 OC33; do
        arq="$(ls "$LOCAL/$tipo/${tipo}_"*"_$oc.OUT" 2>/dev/null | head -1 || true)"
        if [[ -z "$arq" ]] || ! grep -qv '^#' "$arq"; then
            echo "RECUSADO: falta aqui $tipo $oc de runs/$REL. Traga a pasta antes de limpar." >&2
            exit 1
        fi
    done
done
if ! grep -qs "stopped gracefully" "$LOCAL/INFOXS_04.OUT"; then
    echo "RECUSADO: a etapa 04 de runs/$REL nao terminou bem (INFOXS_04.OUT)." >&2
    exit 1
fi

ACHA="find '$REMOTA' -maxdepth 1 -type f \\( -name 'SCCLI_QMT*.OUT' -o -name 'EXCLI_*QMT*.OUT' \\)"
SAIDA="$(no_lise <<FIM
if squeue --me -h -o '%j' | grep -q '^$NOME'; then echo FILA; exit 0; fi
$ACHA -exec ls -lh {} +
FIM
)"
SAIDA="$(printf '%s\n' "$SAIDA" | grep -E '^(FILA$|-)' || true)"
if [[ "$SAIDA" == FILA ]]; then
    echo "RECUSADO: ha um job de $NOME na fila ou rodando no Lise." >&2
    exit 1
fi
if [[ -z "$SAIDA" ]]; then
    echo "[lise] nada a apagar em $REMOTA"
    exit 0
fi
echo "Vai apagar em $LISE_HOST:$REMOTA:"
printf '%s\n' "$SAIDA" | awk '{print "  " $5 "  " $NF}'
(( LISTA )) && exit 0

echo
read -r -p "Apagar? [s/N] " RESP
[[ "$RESP" == [sS] ]] || { echo "Nada apagado."; exit 0; }

no_lise <<FIM
if squeue --me -h -o '%j' | grep -q '^$NOME'; then echo "RECUSADO: job de $NOME na fila." >&2; exit 1; fi
$ACHA -delete
FIM
echo "[lise] apagados. O show-quota pode levar um tempo para atualizar."
