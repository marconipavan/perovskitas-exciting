#!/usr/bin/env python3
"""Confere se o input.xml de cada fase tem a mesma estrutura do POSCAR de origem."""
import argparse
import itertools
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

IC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IC / "bin"))
import leitura

BOHR_A = 0.529177210903
FASES = ["pm3m", "p4mbm", "i4mcm", "gamma", "r3m", "r3c", "delta"]

TOL_REDE = 1e-5
TOL_FRAC = 1e-6


def le_poscar(caminho):
    linhas = Path(caminho).read_text().splitlines()
    escala = float(linhas[1].split()[0])
    rede = np.array([[float(x) for x in linhas[i].split()[:3]] for i in (2, 3, 4)])
    if escala < 0:
        escala = (-escala / abs(np.linalg.det(rede))) ** (1 / 3)
    rede *= escala
    especies = linhas[5].split()
    quantos = [int(x) for x in linhas[6].split()]
    i = 7
    if linhas[i].strip().lower().startswith("s"):
        i += 1
    direta = linhas[i].strip().lower()[0] in "d"
    i += 1
    pos = {}
    for esp, n in zip(especies, quantos):
        bloco = np.array([[float(x) for x in linhas[i + k].split()[:3]] for k in range(n)])
        if not direta:
            bloco = (bloco * escala) @ np.linalg.inv(rede)
        pos[esp] = bloco
        i += n
    return rede, pos


def le_input(pasta):
    raiz = ET.parse(Path(pasta) / "input.xml").getroot()
    cristal = raiz.find("structure/crystal")
    escala = float(cristal.get("scale", "1.0"))
    rede = np.array([[float(x) for x in b.text.split()]
                     for b in cristal.findall("basevect")]) * escala * BOHR_A
    pos, rmt = {}, {}
    caminho_esp = raiz.find("structure").get("speciespath", "./")
    for esp in raiz.findall("structure/species"):
        arq = esp.get("speciesfile")
        nome = arq.replace(".xml", "")
        pos[nome] = np.array([[float(x) for x in a.get("coord").split()]
                              for a in esp.findall("atom")])
        if esp.get("rmt"):
            rmt[nome] = float(esp.get("rmt"))
        else:
            arq_esp = (Path(pasta) / caminho_esp / arq)
            mt = ET.parse(arq_esp).getroot().find(".//muffinTin")
            rmt[nome] = float(mt.get("radius"))
    return rede, pos, rmt


def menor_distancia(rede_bohr, fa, fb, mesma):
    desl = np.array(list(itertools.product((-1, 0, 1), repeat=3)))
    menor = np.inf
    for i, a in enumerate(fa):
        for j, b in enumerate(fb):
            for d in desl:
                if mesma and i == j and not d.any():
                    continue
                menor = min(menor, np.linalg.norm((b + d - a) @ rede_bohr))
    return menor


def confere(fase, nivel):
    pasta = leitura.acha_run(f"CsSnBr3-{fase}-{nivel}")
    poscar = IC / "estruturas" / "CsSnBr3" / f"POSCAR.{fase}"
    if pasta is None or not (pasta / "input.xml").is_file() or not poscar.is_file():
        print(f"\n## {fase}: sem input.xml ou sem POSCAR - pulada")
        return True

    rv, pv = le_poscar(poscar)
    re_, pe, rmt = le_input(pasta)
    ok = True
    print(f"\n## {fase}  ({pasta.name}  <-  {poscar.name})")

    drede = np.abs(rv - re_).max()
    vol_v, vol_e = abs(np.linalg.det(rv)), abs(np.linalg.det(re_))
    comp = np.linalg.norm(re_, axis=1)
    marca = "OK" if drede < TOL_REDE else "DIFERENTE"
    ok &= drede < TOL_REDE
    nfu = int(np.gcd.reduce([len(v) for v in pe.values()]))
    print(f"  rede      |a| |b| |c| = {comp[0]:.5f} {comp[1]:.5f} {comp[2]:.5f} A   "
          f"volume {vol_e:.4f} A³ = {vol_e / nfu:.2f} A³/fórmula ({nfu} fórmulas)")
    print(f"            max |Δ| vetores POSCAR × input = {drede:.2e} A   "
          f"Δvolume = {vol_e - vol_v:+.2e} A³   -> {marca}")

    for esp in pv:
        if esp not in pe:
            print(f"  posições   {esp}: está no POSCAR e NÃO no input.xml  -> DIFERENTE")
            ok = False
            continue
        if pv[esp].shape != pe[esp].shape:
            print(f"  posições   {esp}: {len(pv[esp])} átomos no POSCAR × "
                  f"{len(pe[esp])} no input  -> DIFERENTE")
            ok = False
            continue
        d = pv[esp] - pe[esp]
        d -= np.round(d)
        dmax = np.abs(d).max()
        ok &= dmax < TOL_FRAC
        print(f"  posições   {esp:2s} ({len(pe[esp]):2d})  max |Δfrac| = {dmax:.2e}"
              f"  -> {'OK' if dmax < TOL_FRAC else 'DIFERENTE'}")

    rede_bohr = re_ / BOHR_A
    nomes = list(pe)
    print("  muffin-tin  par      menor dist.   rmt+rmt   folga (bohr)")
    for a, b in itertools.combinations_with_replacement(nomes, 2):
        dist = menor_distancia(rede_bohr, pe[a], pe[b], a == b)
        soma = rmt[a] + rmt[b]
        folga = dist - soma
        aviso = "  <- SOBREPÕE" if folga < 0 else ("  <- apertado" if folga < 0.3 else "")
        ok &= folga >= 0
        print(f"              {a}-{b:2s}   {dist:8.4f}     {soma:6.3f}    {folga:+7.3f}{aviso}")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fases", nargs="*", default=FASES)
    ap.add_argument("--nivel", default="pbe", help="sufixo da pasta: pbe, pbe12, ...")
    args = ap.parse_args()
    resultados = {f: confere(f, args.nivel) for f in args.fases}
    print("\n## resumo")
    for f, ok in resultados.items():
        print(f"  {f:6s} {'OK' if ok else 'PROBLEMA'}")
    return 0 if all(resultados.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
