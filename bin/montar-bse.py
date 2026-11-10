#!/usr/bin/env python3
"""Monta o BSE de uma fase em 4 etapas encadeadas."""
import argparse
import re
import shlex
import shutil
import sys
from datetime import datetime
from pathlib import Path

IC = Path(__file__).resolve().parent.parent
CONF = IC / "bin" / "lise" / "lise.conf"
ESPECIES = ("Cs", "Sn", "Br")

GS = {"pm3m": "runs/semana-08/CsSnBr3-pm3m-grupo-teste/3-pbe12-soc"}
for _f in ("p4mbm", "i4mcm", "gamma", "r3c", "delta", "r3m"):
    GS[_f] = f"runs/semana-08/CsSnBr3-{_f}-pbe12-soc/pbe12-soc"

KPONTOS = {"delta": "11 5 3", "gamma": "6 6 4", "i4mcm": "6 6 4", "p4mbm": "7 7 9",
           "pm3m": "10 10 10", "r3c": "7 7 7", "r3m": "7 7 6"}
NSTLBSE = {"delta": "289 360 1 24", "gamma": "289 360 1 22", "i4mcm": "289 360 1 22",
           "p4mbm": "145 180 1 16", "pm3m": "73 90 1 14", "r3c": "145 180 1 14", "r3m": "217 270 1 16"}
PARALELO = {"delta": "1,48,4 8,16,12 8,16,12 8,16,12", "gamma": "3,48,4 3,48,4 3,48,4 3,48,4",
            "i4mcm": "3,48,4 1,30,6 3,48,4 3,48,4", "p4mbm": "1,192,1 3,192,1 3,96,2 3,96,2",
            "pm3m": "1,48,4 1,56,3 2,48,4 3,48,4", "r3c": "1,48,4 1,35,5 2,48,4 3,48,4",
            "r3m": "1,48,4 1,35,5 2,48,4 3,48,4"}
PLANOS = {"01": '<doonly task="xsgeneigvec"/> <doonly task="writepmatxs"/> <doonly task="scrgeneigvec"/> <doonly task="scrwritepmat"/>',
          "02": '<doonly task="screen"/>',
          "03": '<doonly task="scrcoulint"/> <doonly task="exccoulint"/>',
          "04": '<doonly task="bse"/>'}

XS = """  <xs
    xstype="BSE"
    ngridk="{k}"
    ngridq="{k}"
    vkloff="0.01 0.002 0.011"
    nempty="120"
    scissor="0.0000d0"
    gqmax="2.0"
    broad="0.008"
    tevout="true" >
    <energywindow
      intv="0.0 1.0"
      points="1500" />
    <screening
      screentype="full"
      nempty="50" />
    <BSE
      bsetype="singlet"
      distribute="true"
      bsesolver="elpa2StageSolver"
      nstlbse="{nst}" />
    <plan>
      {plano}
    </plan>
    <qpointset>
      <qpoint>0.0 0.0 0.0</qpoint>
    </qpointset>
  </xs>
"""


def le_conf():
    conf = {}
    for linha in CONF.read_text().splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            conf[k.strip()] = " ".join(shlex.split(v)) if v.strip() else ""
    return conf


def job(conf, fase, etapa, nos, ranks, threads, cadeia, tempo=None, primeira=False):
    particao, padrao = ("cpu-genoa:test", "01:00:00") if etapa == "01" else ("cpu-genoa", "12:00:00")
    tempo = tempo or padrao
    h, m, s = map(int, tempo.split(":"))
    custo = round(int(nos) * (h + m / 60 + s / 3600) * 192)
    linhas = [
        "#!/bin/bash",
        f"# Gerado por bin/montar-bse.py em {datetime.now():%d/%m/%Y %H:%M}. BSE da {fase}, etapa {etapa}: "
        + PLANOS[etapa].replace('<doonly task="', "").replace('"/>', ""),
        f"# {nos} no(s) x {ranks} ranks x {threads} threads. Custo maximo: {nos} x {tempo} x 192 = {custo} core-h.",
        "#",
        f"#SBATCH -p {particao}",
        f"#SBATCH -N {nos}",
        f"#SBATCH --tasks-per-node {ranks}",
        f"#SBATCH -c {threads}",
        f"#SBATCH -t {tempo}",
        f"#SBATCH -J CsSnBr3-{fase}-bse-{etapa}",
        "#SBATCH -o lise-%j.out",
        "#SBATCH --hint=nomultithread",
        f"#SBATCH -A {conf['LISE_CONTA']}",
        f"#SBATCH --mail-type={conf.get('LISE_EMAIL_TIPO') or 'END,FAIL'}",
        f"#SBATCH --mail-user={conf['LISE_EMAIL']}",
        "",
        "ulimit -s unlimited",
        f"module load {conf['LISE_MODULOS_GRUPO']}",
        "export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK",
        "export OMP_PLACES=cores OMP_PROC_BIND=close",
        "export OMP_STACKSIZE=1g SLURM_CPU_BIND=none",
        "export GFORTRAN_UNBUFFERED_ALL=1",
        "cd \"$SLURM_SUBMIT_DIR\"",
        "",
    ]
    if cadeia:
        linhas += [
            "limpo() { env $(compgen -e | grep -E '^(SLURM|SBATCH)_' | grep -v '^SLURM_CONF$' | sed 's/^/-u /') \"$@\"; }",
            "anterior=$SLURM_JOB_ID",
            f'echo "{etapa} $SLURM_JOB_ID" > cadeia.txt',
            f"for e in {' '.join(cadeia)}; do",
            "    anterior=$(limpo sbatch --parsable --kill-on-invalid-dep=yes --dependency=afterok:$anterior job_$e.slurm)",
            '    echo "$e $anterior" >> cadeia.txt',
            "done",
            'echo "cadeia:"; cat cadeia.txt',
            "",
        ]
    elif primeira:
        linhas += [f'echo "{etapa} $SLURM_JOB_ID" > cadeia.txt', ""]
    linhas += [
        f'echo "=== etapa {etapa}   no: $(hostname)   inicio: $(date \'+%d/%m/%Y %T\')"',
        f"cp input_{etapa}.xml input.xml",
        "mpirun --bind-to core --map-by ppr:$SLURM_NTASKS_PER_NODE:node:pe=$OMP_NUM_THREADS "
        f"{conf['LISE_EXCITING_GRUPO']} > exciting_{etapa}.log 2>&1",
        "rc=$?",
        'echo "codigo de saida: $rc   fim: $(date \'+%d/%m/%Y %T\')"',
        f"cp INFOXS.OUT INFOXS_{etapa}.OUT",
        "exit $rc",
        "",
    ]
    return "\n".join(linhas)


def montar(fase, semana="08", desde="01", ate="04", paralelo=None, tempos=None, k=None, sufixo=""):
    gs = IC / GS[fase]
    if not (gs / "INFO.OUT").exists():
        sys.exit(f"ERRO: o ground state {GS[fase]} ainda nao rodou (sem INFO.OUT)")
    lote = IC / "runs" / f"semana-{semana}" / (f"CsSnBr3-{fase}-bse" + (f"-{sufixo}" if sufixo else ""))
    if desde != "01":
        if not (lote / "STATE.OUT").exists():
            sys.exit(f"ERRO: nao ha STATE.OUT em {lote.relative_to(IC)}. Traga a pasta com --com-state antes.")
    elif not (gs / "STATE.OUT").exists():
        sys.exit(f"ERRO: nao ha STATE.OUT em {GS[fase]}. Traga a pasta do ground state com --com-state.")
    elif (gs / "STATE.OUT").stat().st_mtime < (gs / "INFO.OUT").stat().st_mtime - 300:
        sys.exit(f"ERRO: o STATE.OUT de {GS[fase]} e mais velho que o INFO.OUT: e o de partida, nao o convergido.\n"
                 "      Traga a pasta do ground state com o STATE.OUT (trazer.sh ... --com-state).")
    base = (gs / "input.xml").read_text()
    base = re.sub(r'do="[^"]*"', 'do="skip"', base)
    base = re.sub(r"<title>.*?</title>", f"<title>CsSnBr3 {fase} BSE sobre PBE-1/2+SOC (svlo) - exciting do grupo</title>", base)
    lote.mkdir(parents=True, exist_ok=True)
    conf = le_conf()
    pars = dict(zip(PLANOS, PARALELO[fase].split())) | (paralelo or {})
    etapas = [e for e in PLANOS if desde <= e <= ate]
    for etapa in etapas:
        par = pars[etapa]
        xs = XS.format(k=k or KPONTOS[fase], nst=NSTLBSE[fase], plano=PLANOS[etapa])
        t = base.replace("</groundstate>\n", "</groundstate>\n" + xs, 1)
        (lote / f"input_{etapa}.xml").write_text(t)
        if etapa == etapas[0]:
            (lote / "input.xml").write_text(t)
        nos, ranks, threads = par.split(",")
        nome = "job.slurm" if etapa == etapas[0] else f"job_{etapa}.slurm"
        cadeia = etapas[1:] if etapa == etapas[0] else []
        (lote / nome).write_text(job(conf, fase, etapa, nos, ranks, threads, cadeia, (tempos or {}).get(etapa), etapa == etapas[0]))
    for s in ESPECIES:
        shutil.copy(gs / f"{s}.xml", lote / f"{s}.xml")
    if desde == "01":
        for f in ("STATE.OUT", "EFERMI.OUT"):
            shutil.copy(gs / f, lote / f)
    print(f"montado: {lote.relative_to(IC)}  (ground state {GS[fase]}, etapas {' '.join(etapas)})")
    print(f"  k {k or KPONTOS[fase]}, nstlbse {NSTLBSE[fase]}, paralelizacao {' '.join(pars[e] for e in etapas)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fases", nargs="+", choices=sorted(GS))
    ap.add_argument("--semana", default="08", help="pasta runs/semana-NN do lote (padrao: 08)")
    ap.add_argument("--desde", default="01", choices=sorted(PLANOS), help="primeira etapa (padrao: 01)")
    ap.add_argument("--ate", default="04", choices=sorted(PLANOS), help="ultima etapa (padrao: 04)")
    ap.add_argument("--paralelo", nargs="*", default=[], metavar="ETAPA=NOS,RANKS,THREADS",
                    help="troca a paralelizacao de uma etapa, ex.: 03=4,48,4")
    ap.add_argument("--k", help='malha k e q do BSE, ex.: "7 7 8" (padrao: a do script de referencia)')
    ap.add_argument("--sufixo", default="", help="sufixo do nome da pasta, ex.: k778 -> CsSnBr3-<fase>-bse-k778")
    ap.add_argument("--tempo", nargs="*", default=[], metavar="ETAPA=HH:MM:SS",
                    help="troca o tempo pedido de uma etapa, ex.: 04=24:00:00")
    a = ap.parse_args()
    if a.desde > a.ate:
        ap.error("--desde depois de --ate")
    paralelo = dict(x.split("=") for x in a.paralelo)
    tempos = dict(x.split("=") for x in a.tempo)
    for f in a.fases:
        montar(f, a.semana, a.desde, a.ate, paralelo, tempos, a.k, a.sufixo)


if __name__ == "__main__":
    main()
