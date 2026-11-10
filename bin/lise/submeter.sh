#!/usr/bin/env bash
# Submete no Lise o job.slurm de uma pasta ja enviada.
source "$(dirname "${BASH_SOURCE[0]}")/comum.sh"

[[ $# -eq 1 ]] || { echo "uso: submeter.sh runs/semana-NN/PASTA" >&2; exit 2; }
REL="$(pasta_relativa "$1")"
REMOTA="$(remota "$REL")"
JOB="$IC/runs/$REL/job.slurm"
[[ -f "$JOB" ]] || { echo "ERRO: nao ha job.slurm em runs/$REL" >&2; exit 1; }

LOCAL_MD5="$(md5sum "$JOB" | cut -d' ' -f1)"
REMOTO_MD5="$(ssh -n "$LISE_HOST" md5sum "$REMOTA/job.slurm" 2>/dev/null | cut -d' ' -f1 || true)"
if [[ -z "$REMOTO_MD5" ]]; then
    echo "ERRO: nao ha job.slurm em $LISE_HOST:$REMOTA. Envie a pasta antes." >&2
    exit 1
elif [[ "$LOCAL_MD5" != "$REMOTO_MD5" ]]; then
    echo "ERRO: o job.slurm do Lise e diferente do local. Envie a pasta de novo." >&2
    exit 1
fi

PART="$(sbatch_opcao "$JOB" -p --partition)"
NOS="$(sbatch_opcao "$JOB" -N --nodes)"; NOS="${NOS:-1}"
RANKS="$(sbatch_opcao "$JOB" --tasks-per-node --ntasks-per-node)"
THREADS="$(sbatch_opcao "$JOB" -c --cpus-per-task)"; THREADS="${THREADS:-1}"
TEMPO="$(sbatch_opcao "$JOB" -t --time)"
CONTA="$(sbatch_opcao "$JOB" -A --account)"
EMAIL="$(sbatch_opcao "$JOB" --mail-user)"

read -r TAXA CORES ALOC <<< "$(taxa "$PART")" || true
if [[ -z "${TAXA:-}" ]]; then
    echo "AVISO: particao $PART fora da tabela de cobranca; custo nao estimado."
    CUSTO="?"
else
    FRACAO=1
    [[ "$ALOC" == compartilhavel ]] && FRACAO="$(awk -v r="$RANKS" -v c="$THREADS" -v n="$CORES" 'BEGIN{printf "%.4f", r*c/n}')"
    CUSTO="$(awk -v n="$NOS" -v h="$(horas "$TEMPO")" -v t="$TAXA" -v f="$FRACAO" 'BEGIN{printf "%.0f", n*h*t*f}')"
fi

echo
echo "  pasta      runs/$REL"
echo "  no Lise    $REMOTA"
echo "  particao   $PART   ($NOS no(s), alocacao ${ALOC:-?})"
echo "  ranks      $RANKS por no  x  $THREADS thread(s)"
echo "  tempo max  $TEMPO"
echo "  conta      ${CONTA:-padrao (pessoal)}"
echo "  e-mail     ${EMAIL:-nenhum}"
echo "  custo max  $CUSTO core-h   (cobra-se o tempo de fato usado)"
echo
read -r -p "Submeter? [s/N] " RESP
[[ "$RESP" == [sS] ]] || { echo "Nada submetido."; exit 0; }

SAIDA="$(no_lise <<EOF
cd '$REMOTA' && sbatch --parsable job.slurm
EOF
)" || { echo "ERRO no sbatch:" >&2; echo "$SAIDA" >&2; exit 1; }
JOBID="$(printf '%s\n' "$SAIDA" | tail -1 | cut -d';' -f1)"
[[ "$JOBID" =~ ^[0-9]+$ ]] || { echo "ERRO: resposta inesperada do sbatch: $SAIDA" >&2; exit 1; }

printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$(date '+%d/%m/%Y %H:%M')" "$JOBID" "$(nome_run "$REL")" \
    "$PART" "$NOS" "$TEMPO" submetido >> "$REGISTRO"
echo "[lise] job $JOBID submetido. Acompanhe com a task \"Lise: estado dos jobs\"."
