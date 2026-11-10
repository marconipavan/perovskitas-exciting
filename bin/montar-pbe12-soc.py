#!/usr/bin/env python3
"""Monta os calculos PBE-1/2 e PBE-1/2+SOC de uma fase."""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

IC = Path(__file__).resolve().parent.parent
ESPECIES_SOC = IC / "runs" / "semana-08" / "CsSnBr3-pm3m-grupo-teste" / "3-pbe12-soc"
ESPECIES = ("Cs", "Sn", "Br")

FASES = {"p4mbm": ("runs/semana-06/CsSnBr3-p4mbm-pbe12-final", "runs/semana-04/CsSnBr3-p4mbm-pbe12", 50, "02:00:00"),
         "r3c": ("runs/semana-06/CsSnBr3-r3c-pbe12-final", "runs/semana-04/CsSnBr3-r3c-pbe12", 126, "03:00:00"),
         "i4mcm": ("runs/semana-06/CsSnBr3-i4mcm-pbe12-final", "runs/semana-05/CsSnBr3-i4mcm-pbe12", 30, "03:30:00"),
         "delta": ("runs/semana-06/CsSnBr3-delta-pbe12-final", "runs/semana-05/CsSnBr3-delta-pbe12", 36, "04:30:00"),
         "gamma": ("runs/semana-06/CsSnBr3-gamma-pbe12-final", "runs/semana-05/CsSnBr3-gamma-pbe12", 48, "04:30:00"),
         "r3m": ("runs/semana-04/CsSnBr3-r3m-pbe12", "runs/semana-04/CsSnBr3-r3m-pbe", 28, "03:00:00")}


def sintaxe_dft05(t):
    def troca(m):
        cut, ampl, exp, meio, num, ion = m.groups()
        return f'<dfthalfparam>{meio}<shell number="{num}" ionization="{ion}" cut="{cut}" ampl="{ampl}" exponent="{exp}"/>'
    t, n = re.subn(r'<dfthalfparam cut="([^"]+)" ampl="([^"]+)" exponent="([^"]+)">(\s*)'
                   r'<shell number="([^"]+)" ionization="([^"]+)"\s*/>', troca, t)
    if n == 0:
        sys.exit("ERRO: <dfthalfparam> no formato esperado nao encontrado")
    return t


def montar(fase, rcut=None):
    src_rel, state_rel, nk, tempo = FASES[fase]
    base = (IC / src_rel / "input.xml").read_text()
    if rcut:
        base = re.sub(r'(<dfthalfparam cut=")[^"]+"', rf'\g<1>{rcut}"', base)
    elif fase == "r3m":
        sys.exit("ERRO: a r3m precisa de --rcut (o otimo da varredura runs/semana-08/CsSnBr3-r3m-rcut)")
    cut = re.search(r'<dfthalfparam cut="([^"]+)"', base).group(1)
    base = re.sub(r"\s*<properties>.*?</properties>", "", base, flags=re.S)
    base = re.sub(r'do="[a-z]+"', 'do="fromfile"', base, count=1)
    base = sintaxe_dft05(base)
    lote = IC / "runs" / "semana-08" / f"CsSnBr3-{fase}-pbe12-soc"
    for sub, soc in (("pbe12", False), ("pbe12-soc", True)):
        nivel = "PBE-1/2+SOC (svlo)" if soc else "PBE-1/2"
        t = re.sub(r"<title>.*?</title>",
                   f"<title>CsSnBr3 {fase} {nivel}, r_cut {cut}, especies de referencia do SOC - exciting do grupo</title>", base)
        if soc:
            t = t.replace('do="fromfile"', 'do="fromfile"\n      useDensityMatrix="false"', 1)
            t = t.replace("</groundstate>", '   <spin spinorb="true" svlo="true"/>\n   </groundstate>', 1)
        d = lote / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / "input.xml").write_text(t)
        for s in ESPECIES:
            shutil.copy(ESPECIES_SOC / f"{s}.xml", d / f"{s}.xml")
        shutil.copy(IC / state_rel / "STATE.OUT", d / "STATE.OUT")
    r = subprocess.run([sys.executable, str(IC / "bin" / "lise" / "criar-job.py"), "--src", str(lote),
                        "--pontos-k", str(nk), "--tempo", tempo, "--exciting", "grupo", "--forcar"],
                       capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())
    print(f"montado: {lote.relative_to(IC)}  (r_cut {cut}, STATE.OUT de {state_rel})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fases", nargs="+", choices=sorted(FASES))
    ap.add_argument("--rcut", help="r_cut no lugar do da producao (obrigatorio na r3m)")
    a = ap.parse_args()
    for f in a.fases:
        montar(f, a.rcut)


if __name__ == "__main__":
    main()
