#!/usr/bin/env bash
# Envia uma pasta de runs para o Lise.
source "$(dirname "${BASH_SOURCE[0]}")/comum.sh"

[[ $# -eq 1 ]] || { echo "uso: enviar.sh runs/semana-NN/PASTA" >&2; exit 2; }
PASTA="$1"
REL="$(pasta_relativa "$PASTA")"
REMOTA="$(remota "$REL")"
cd "$IC/runs/$REL"

IGUAIS="$(find "$IC/runs" -mindepth 1 -maxdepth 2 -type d -name "$(nome_run "$REL")" | wc -l)"
[[ "$IGUAIS" -le 1 ]] || { echo "ERRO: ha $IGUAIS pastas chamadas $(nome_run "$REL") em runs/." >&2
                           echo "      No Lise o nome identifica a pasta; renomeie uma delas." >&2; exit 1; }

[[ -f job.slurm ]] || { echo "ERRO: nao ha job.slurm em runs/$REL." >&2
                        echo "      Gere com a task \"Lise: criar job.slurm\"." >&2; exit 1; }

ARQUIVOS=(job.slurm)

inclui_calculo() {
    local sub="$1" pre="" sp spath f
    [[ "$sub" == "." ]] || pre="$sub/"
    [[ -f "${pre}input.xml" ]] || { echo "ERRO: nao ha input.xml em runs/$REL/$sub" >&2; exit 1; }
    ARQUIVOS+=("${pre}input.xml")
    for f in "${pre}"input_[0-9]*.xml "${pre}"job_[0-9]*.slurm; do
        [[ -f "$f" ]] && ARQUIVOS+=("$f")
    done

    spath="$(grep -om1 'speciespath="[^"]*"' "${pre}input.xml" | sed 's/^speciespath="//; s/"$//' || true)"
    case "$spath" in
        ""|"."|"./") ;;
        *)
            echo "ERRO: runs/$REL/$sub: speciespath=\"$spath\" aponta para fora da pasta." >&2
            echo "      O envio so sabe levar especies que estejam na propria pasta (speciespath=\"./\")." >&2
            exit 1
            ;;
    esac
    while IFS= read -r sp; do
        [[ -f "${pre}$sp" ]] || { echo "ERRO: especie $sp citada em runs/$REL/${pre}input.xml e ausente" >&2; exit 1; }
        ARQUIVOS+=("${pre}$sp")
    done < <(grep -o 'speciesfile="[^"]*"' "${pre}input.xml" | sed 's/^speciesfile="//; s/"$//' | sort -u)

    local modo
    modo="$(grep -oE 'do[[:space:]]*=[[:space:]]*"(skip|fromfile)"' "${pre}input.xml" | head -1 | grep -oE 'skip|fromfile' || true)"
    if [[ -n "$modo" ]]; then
        for f in STATE.OUT EFERMI.OUT OCCSV.OUT EVALCORE.OUT LINENGY.OUT; do
            if [[ -f "${pre}$f" ]]; then
                ARQUIVOS+=("${pre}$f")
            elif [[ "$f" == STATE.OUT ]]; then
                echo "ERRO: runs/$REL/$sub tem do=\"$modo\", mas nao ha STATE.OUT." >&2
                exit 1
            fi
        done
        echo "[lise] $sub: do=\"$modo\", os arquivos de restart vao junto"
    fi
}

if [[ -f input.xml ]]; then
    inclui_calculo .
else
    SUBS=()
    for d in */; do [[ -f "${d}input.xml" ]] && SUBS+=("${d%/}"); done
    [[ ${#SUBS[@]} -gt 0 ]] || { echo "ERRO: nao ha input.xml em runs/$REL nem nas subpastas" >&2; exit 1; }
    echo "[lise] lote: ${#SUBS[@]} subpastas"
    for s in "${SUBS[@]}"; do inclui_calculo "$s"; done
fi

echo "[lise] enviando runs/$REL  ->  $LISE_HOST:$REMOTA"
ssh "$LISE_HOST" mkdir -p "$REMOTA"
rsync -avR "${ARQUIVOS[@]}" "$LISE_HOST:$REMOTA/"
echo "[lise] enviados ${#ARQUIVOS[@]} arquivos"
