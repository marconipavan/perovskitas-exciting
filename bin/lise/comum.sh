# Funcoes comuns aos scripts de bin/lise.

set -euo pipefail

IC="${IC_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

if [[ -f "$IC/.lise/trava.sh" ]]; then
    source "$IC/.lise/trava.sh"
fi

CONF="$IC/bin/lise/lise.conf"
[[ -f "$CONF" ]] || { echo "ERRO: falta $CONF" >&2; exit 1; }
source "$CONF"

REGISTRO="$IC/.lise/jobs.tsv"
mkdir -p "$(dirname "$REGISTRO")"
[[ -f "$REGISTRO" ]] || printf 'data\tjob\tpasta\tparticao\tnos\ttempo\tsituacao\n' > "$REGISTRO"

pasta_relativa() {
    local src runs
    src="$(cd "$1" 2>/dev/null && pwd)" || { echo "ERRO: pasta nao existe: $1" >&2; return 1; }
    runs="$(cd "$IC/runs" && pwd)"
    case "$src/" in
        "$runs"/*/) printf '%s\n' "${src#"$runs"/}" ;;
        *) echo "ERRO: a pasta tem de estar dentro de runs/: $src" >&2; return 1 ;;
    esac
}

nome_run() { basename "$1"; }
remota() { printf '%s/%s\n' "$LISE_RUNS" "$(nome_run "$1")"; }

no_lise() { ssh "$LISE_HOST" 'bash -l -s'; }

taxa() {
    case "$1" in
        cpu-clx|cpu-clx:test|cpu-clx:ssd) echo "96 96 exclusiva" ;;
        cpu-clx:large)                    echo "144 96 compartilhavel" ;;
        cpu-clx:huge)                     echo "192 96 compartilhavel" ;;
        cpu-genoa|cpu-genoa:test)         echo "192 192 exclusiva" ;;
        *)                                echo "" ;;
    esac
}

horas() {
    awk -v t="$1" 'BEGIN{
        d = 0; if (index(t, "-")) { split(t, a, "-"); d = a[1]; t = a[2] }
        n = split(t, p, ":")
        if (n == 3)      h = p[1] + p[2]/60 + p[3]/3600
        else if (n == 2) h = p[1]/60 + p[2]/3600
        else             h = p[1]/60
        printf "%.4f", d*24 + h }'
}

sbatch_opcao() {
    local arquivo="$1"; shift
    local f
    for f in "$@"; do
        awk -v f="$f" '
            /^#SBATCH/ {
                for (i = 2; i <= NF; i++) {
                    if ($i == f && i < NF) { print $(i+1); exit }
                    if (index($i, f "=") == 1) { print substr($i, length(f) + 2); exit }
                }
            }' "$arquivo" | head -1 | grep . && return 0
    done
    return 0
}
