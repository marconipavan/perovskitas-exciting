#!/usr/bin/env bash
# Mostra a fila e o estado dos jobs registrados no Lise.
source "$(dirname "${BASH_SOURCE[0]}")/comum.sh"

PENDENTES="$(awk -F'\t' -v r="$LISE_RUNS" 'NR > 1 && $7 != "trazido" { print $2, r "/" $3 }' "$REGISTRO")"

no_lise <<EOF
echo "== fila (squeue --me)"
squeue --me -o "%.10i %.28j %.14P %.3t %.10M %.10l %R"
echo
echo "== jobs registrados ainda nao trazidos"
if [ -z "$PENDENTES" ]; then
    echo "(nenhum)"
fi
while read -r id pasta; do
    [ -n "\$id" ] || continue
    info=\$(sacct -j "\$id" -X -n -P -o State,Elapsed 2>/dev/null | head -1)
    situacao=\${info%%|*}; gasto=\${info##*|}
    scf="-"
    if [ -f "\$pasta/INFO.OUT" ]; then
        scf="\$(grep -c 'SCF iteration number' "\$pasta/INFO.OUT") iteracoes SCF"
        grep -q 'Convergence targets achieved' "\$pasta/INFO.OUT" && scf="\$scf, convergido"
    elif ls "\$pasta"/*/input.xml >/dev/null 2>&1; then
        tot=\$(ls "\$pasta"/*/input.xml | wc -l)
        ok=\$(grep -l 'Convergence targets achieved' "\$pasta"/*/INFO.OUT 2>/dev/null | wc -l)
        scf="lote: \$ok de \$tot subpastas convergidas"
    fi
    printf '%-10s %-12s %-10s %-30s %s\n' "\$id" "\${situacao:-?}" "\${gasto:-?}" "\${pasta##*/runs/}" "\$scf"
done <<'LISTA'
$PENDENTES
LISTA
EOF
