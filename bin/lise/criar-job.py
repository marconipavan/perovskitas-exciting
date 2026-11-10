#!/usr/bin/env python3
"""Escreve o job.slurm de uma pasta de runs para o Lise."""
import argparse
import re
import shlex
import sys
from datetime import datetime
from pathlib import Path

IC = Path(__file__).resolve().parent.parent.parent
CONF = IC / "bin" / "lise" / "lise.conf"

PARTICOES = {
    "cpu-clx": (96, 96, "exclusiva"),
    "cpu-clx:test": (96, 96, "exclusiva"),
    "cpu-clx:ssd": (96, 96, "exclusiva"),
    "cpu-clx:large": (144, 96, "compartilhavel"),
    "cpu-clx:huge": (192, 96, "compartilhavel"),
    "cpu-genoa": (192, 192, "exclusiva"),
    "cpu-genoa:test": (192, 192, "exclusiva"),
}
LIMITE_TESTE_H = 1.0


def le_conf():
    conf = {}
    for linha in CONF.read_text().splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        conf[chave.strip()] = " ".join(shlex.split(valor)) if valor.strip() else ""
    return conf


def horas(t):
    dias = 0
    if "-" in t:
        d, t = t.split("-", 1)
        dias = int(d)
    p = [float(x) for x in t.split(":")]
    if len(p) == 3:
        h = p[0] + p[1] / 60 + p[2] / 3600
    elif len(p) == 2:
        h = p[0] / 60 + p[1] / 3600
    else:
        h = p[0] / 60
    return dias * 24 + h


def pontos_k(pasta):
    arq = pasta / "KPOINTS.OUT"
    if arq.is_file():
        primeira = arq.read_text().split("\n", 1)[0].split()
        if primeira and primeira[0].isdigit():
            return int(primeira[0])
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, help="pasta dentro de runs/")
    ap.add_argument("--ranks", default="auto", help="ranks MPI; 'auto' = pontos k ou no inteiro")
    ap.add_argument("--threads", default="auto",
                    help="threads OpenMP por rank; 'auto' = floor(cores / ranks)")
    ap.add_argument("--pontos-k", type=int, default=None,
                    help="pontos k irredutiveis, quando a pasta ainda nao rodou")
    ap.add_argument("--tempo", default="padrao", help="HH:MM:SS; 'padrao' = LISE_TEMPO")
    ap.add_argument("--particao", default="padrao", help="'padrao' = LISE_PARTICAO")
    ap.add_argument("--conta", choices=["projeto", "pessoal"], default="projeto",
                    help="projeto = LISE_CONTA (padrao); pessoal = LISE_CONTA_PESSOAL")
    ap.add_argument("--exciting", choices=["modulo", "grupo"], default="modulo",
                    help="modulo = o do Lise (LISE_MODULOS, CLX); grupo = o build do grupo "
                         "(LISE_EXCITING_GRUPO, Genoa, aceita DFT-1/2 + SOC + svlo)")
    ap.add_argument("--forcar", action="store_true", help="sobrescreve job.slurm existente")
    args = ap.parse_args()

    conf = le_conf()
    pasta = Path(args.src).resolve()
    runs = (IC / "runs").resolve()
    subpastas = (sorted(p.name for p in pasta.iterdir() if (p / "input.xml").is_file())
                 if pasta.is_dir() else [])
    lote = not (pasta / "input.xml").is_file()
    if lote and not subpastas:
        sys.exit(f"ERRO: nao ha input.xml em {pasta} nem nas subpastas dela")
    if runs not in pasta.parents:
        sys.exit(f"ERRO: a pasta tem de estar dentro de runs/: {pasta}")

    destino = pasta / "job.slurm"
    if destino.exists() and not args.forcar:
        sys.exit(f"ERRO: {destino.relative_to(IC)} ja existe (e versionado).\n"
                 "      Para gerar de novo, use --forcar (na task: apague o arquivo antes).")

    grupo = args.exciting == "grupo"
    if grupo and not conf.get("LISE_EXCITING_GRUPO"):
        sys.exit("ERRO: --exciting grupo, mas LISE_EXCITING_GRUPO esta vazio no lise.conf")
    padrao = "cpu-genoa" if grupo else conf["LISE_PARTICAO"]
    particao = padrao if args.particao == "padrao" else args.particao
    if grupo and not particao.startswith("cpu-genoa"):
        sys.exit(f"ERRO: o exciting do grupo foi compilado para a Genoa; particao pedida: {particao}")
    tempo = conf["LISE_TEMPO"] if args.tempo == "padrao" else args.tempo
    if particao not in PARTICOES:
        sys.exit(f"ERRO: particao desconhecida: {particao} (opcoes: {', '.join(PARTICOES)})")
    if not re.fullmatch(r"(\d+-)?\d+(:\d{1,2}){0,2}", tempo):
        sys.exit(f"ERRO: tempo invalido: {tempo} (formato HH:MM:SS)")
    taxa, cores_no, alocacao = PARTICOES[particao]
    if particao.endswith(":test") and horas(tempo) > LIMITE_TESTE_H:
        sys.exit(f"ERRO: {particao} aceita no maximo 1 h; pedido: {tempo}")

    if lote:
        nks = [k for k in (pontos_k(pasta / s) for s in subpastas) if k]
        nk = max(nks) if nks else None
    else:
        nk = pontos_k(pasta)
    fonte_nk = "KPOINTS.OUT"
    if nk is None and args.pontos_k:
        nk, fonte_nk = args.pontos_k, "--pontos-k"
    threads_fixas = None if args.threads == "auto" else int(args.threads)
    if threads_fixas is not None and not 1 <= threads_fixas <= cores_no:
        sys.exit(f"ERRO: threads tem de estar entre 1 e {cores_no}")
    max_ranks = cores_no // (threads_fixas or 1)
    if args.ranks == "auto":
        ranks = min(nk, max_ranks) if nk else max_ranks
        origem = (f"{nk} pontos k ({fonte_nk})" if nk else
                  "no inteiro: a pasta ainda nao rodou, os pontos k sao desconhecidos")
    else:
        ranks = int(args.ranks)
        origem = "escolhido na hora"
    if ranks < 1:
        sys.exit("ERRO: ranks tem de ser >= 1")
    threads = threads_fixas or max(1, cores_no // ranks)
    if ranks < 1 or ranks * threads > cores_no:
        sys.exit(f"ERRO: {ranks} ranks x {threads} threads passa dos {cores_no} cores do no")
    if nk and ranks > nk:
        print(f"AVISO: {ranks} ranks para {nk} pontos k: {ranks - nk} ficarao ociosos.")

    fracao = 1.0 if alocacao == "exclusiva" else ranks * threads / cores_no
    custo_max = 1 * horas(tempo) * taxa * fracao
    nome = re.sub(r"[^A-Za-z0-9._-]", "_", pasta.name)[:40]
    modulos = conf["LISE_MODULOS_GRUPO" if grupo else "LISE_MODULOS"].split()

    linhas = [
        "#!/bin/bash",
        f"# Gerado por bin/lise/criar-job.py em {datetime.now():%d/%m/%Y %H:%M}.",
        f"# Ranks: {origem}. Threads: "
        + ("escolhidas na hora." if threads_fixas else f"floor({cores_no} / {ranks}) = {threads}.")
        + " Pinning: ranks espalhados pelo no.",
        f"# Custo maximo: 1 no x {tempo} x {taxa} core-h/no-hora"
        + (f" x {fracao:.2f}" if fracao < 1 else "") + f" = {custo_max:.0f} core-h.",
        "#",
        f"#SBATCH -p {particao}",
        "#SBATCH -N 1",
        f"#SBATCH --tasks-per-node {ranks}",
        f"#SBATCH -c {threads}",
        f"#SBATCH -t {tempo}",
        f"#SBATCH -J {nome}",
        "#SBATCH -o lise-%j.out",
    ]
    if grupo:
        linhas.append("#SBATCH --hint=nomultithread")
    conta = conf.get("LISE_CONTA" if args.conta == "projeto" else "LISE_CONTA_PESSOAL")
    if args.conta == "pessoal" and not conta:
        sys.exit("ERRO: --conta pessoal, mas LISE_CONTA_PESSOAL esta vazio no lise.conf")
    if conta:
        linhas.append(f"#SBATCH -A {conta}")
    if conf.get("LISE_EMAIL"):
        linhas += [f"#SBATCH --mail-type={conf.get('LISE_EMAIL_TIPO') or 'END,FAIL'}",
                   f"#SBATCH --mail-user={conf['LISE_EMAIL']}"]
    raiz = f"{conf['LISE_RUNS']}/{pasta.name}"
    rodar = [
        (f"mpirun --bind-to core --map-by ppr:$SLURM_NTASKS_PER_NODE:node:pe=$OMP_NUM_THREADS "
         f"{conf['LISE_EXCITING_GRUPO']} > exciting.log 2>&1") if grupo else
        f"mpirun -np $SLURM_NTASKS {conf['LISE_BINARIO']} > exciting.log 2>&1",
        'echo "codigo de saida: $?   fim: $(date \'+%d/%m/%Y %T\')"',
        "grep -m1 'version hash id' INFO.OUT",
        "gap=$(grep 'Estimated fundamental gap' INFO.OUT | tail -1 | awk '{print $NF}')",
        '[ -n "$gap" ] && awk -v g="$gap" \'BEGIN{printf "gap: %.4f eV  (%s Ha)\\n", g*27.211386245988, g}\''
        ' || echo "gap: nao encontrado no INFO.OUT"',
    ]
    linhas += [
        "",
        *[f"module load {m}" for m in modulos],
        "export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK",
        "export OMP_PLACES=cores OMP_PROC_BIND=close",
        *(["ulimit -s unlimited",
           "export OMP_STACKSIZE=1g SLURM_CPU_BIND=none"]
          if grupo else
          ["export I_MPI_PIN_DOMAIN=auto I_MPI_PIN_ORDER=scatter",
           "export I_MPI_DEBUG=4"]),
        "",
        'echo "no: $(hostname)   ranks: $SLURM_NTASKS   threads por rank: $OMP_NUM_THREADS"',
    ]
    if lote:
        linhas += [
            f"for sub in {' '.join(subpastas)}; do",
            f'    cd "{raiz}/$sub" || {{ echo "=== $sub: pasta nao encontrada"; continue; }}',
            "    echo",
            '    echo "=== $sub   inicio: $(date \'+%d/%m/%Y %T\')"',
            *["    " + l for l in rodar],
            "done",
            "",
        ]
    else:
        linhas += [
            f"cd {raiz}",
            'echo "inicio: $(date \'+%d/%m/%Y %T\')"',
            *rodar,
            "",
        ]
    destino.write_text("\n".join(linhas))

    print(f"escrito: {destino.relative_to(IC)}")
    if lote:
        print(f"  LOTE: {len(subpastas)} subpastas, em sequencia: {' '.join(subpastas)}")
    print(f"  {particao} · 1 no · {ranks} ranks x {threads} threads = {ranks * threads} "
          f"de {cores_no} cores · {tempo}")
    print(f"  ranks: {origem}")
    print(f"  conta: {conta or 'a padrao do Slurm'} ({args.conta})")
    print(f"  exciting: {'do grupo (' + conf['LISE_EXCITING_GRUPO'] + ')' if grupo else 'modulo do Lise'}")
    print(f"  custo maximo: {custo_max:.0f} core-h")


if __name__ == "__main__":
    main()
