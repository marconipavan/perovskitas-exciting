#!/usr/bin/env python3
"""Gera o input.xml de uma perovskita ABX3 na fase R-3m a partir da cubica."""
import argparse
import itertools
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

BOHR_A = 0.529177210903
TOL_POS = 1e-6

B_NA_ORIGEM = {"B": [(0, 0, 0)], "A": [(.5, .5, .5)], "X": [(.5, 0, 0), (0, .5, 0), (0, 0, .5)]}
A_NA_ORIGEM = {"A": [(0, 0, 0)], "B": [(.5, .5, .5)], "X": [(0, .5, .5), (.5, 0, .5), (.5, .5, 0)]}


def mesmo_conjunto(p, q):
    if len(p) != len(q):
        return False
    resto = [np.array(x) for x in q]
    for a in p:
        for i, b in enumerate(resto):
            d = (np.array(a) - b + 0.5) % 1.0 - 0.5
            if np.abs(d).max() < TOL_POS:
                resto.pop(i)
                break
        else:
            return False
    return True


def le_base(caminho, nomes):
    arvore = ET.parse(caminho)
    raiz = arvore.getroot()
    cristal = raiz.find("structure/crystal")
    escala = float(cristal.get("scale", "1"))
    B = np.array([[float(x) for x in v.text.split()] for v in cristal.findall("basevect")])
    L = escala * B * BOHR_A
    n = np.linalg.norm(L, axis=1)
    cosang = [L[i] @ L[j] / n[i] / n[j] for i, j in ((1, 2), (0, 2), (0, 1))]
    if np.ptp(n) > 1e-8 * n[0] or max(abs(c) for c in cosang) > 1e-8:
        sys.exit(f"ERRO: a base nao e cubica: |a_i| = {n}, cos = {cosang}")

    pos = {}
    for esp in raiz.findall("structure/species"):
        nome = esp.get("speciesfile").replace(".xml", "")
        pos[nome] = [tuple(float(x) for x in a.get("coord").split()) for a in esp.findall("atom")]
    papel = {nomes["A"]: "A", nomes["B"]: "B", nomes["X"]: "X"}
    if set(pos) != set(papel):
        sys.exit(f"ERRO: especies {sorted(pos)} na base; esperadas {sorted(papel)}")
    por_papel = {papel[k]: v for k, v in pos.items()}
    if all(mesmo_conjunto(por_papel[k], B_NA_ORIGEM[k]) for k in "ABX"):
        origem = "B"
    elif all(mesmo_conjunto(por_papel[k], A_NA_ORIGEM[k]) for k in "ABX"):
        origem = "A"
    else:
        sys.exit(f"ERRO: posicoes da base nao sao as da perovskita cubica ideal: {pos}")
    return arvore, n[0], origem


def vetores(cos_alfa):
    r = math.sqrt(2 * (1 - cos_alfa) / 3)
    h = math.sqrt((1 + 2 * cos_alfa) / 3)
    return np.array([[r * math.cos(math.radians(f)), r * math.sin(math.radians(f)), h]
                     for f in (0, 120, 240)])


def gera(arvore, a_r, cos_alfa, transladar, titulo, nome_b="Sn", delta_b=0.0):
    raiz = arvore.getroot()
    cristal = raiz.find("structure/crystal")
    cristal.set("scale", repr(float(a_r) / BOHR_A))
    u = vetores(cos_alfa)
    for v, ui in zip(cristal.findall("basevect"), u):
        v.text = "  ".join(f"{x:16.12f}" for x in ui)
    eps = delta_b / (a_r * np.linalg.norm(u.sum(axis=0)))
    for esp in raiz.findall("structure/species"):
        desloca = delta_b and esp.get("speciesfile").replace(".xml", "") == nome_b
        for a in esp.findall("atom"):
            p = np.array([float(x) for x in a.get("coord").split()])
            if transladar:
                p = (p + 0.5) % 1.0
            if desloca:
                p = (p + eps) % 1.0
            a.set("coord", "  ".join(f"{x:14.10f}" for x in p))
    if delta_b:
        print(f"{nome_b} deslocado de {delta_b:.4f} A ao longo do eixo de ordem 3: e = {eps:.8f} em (e,e,e)")
    t = raiz.find("title")
    if t is not None and titulo:
        t.text = titulo
    ET.indent(arvore, space="   ")
    return arvore


def valida(caminho, a_r, cos_alfa, symprec, nomes_axb=("Cs", "Sn", "Br")):
    raiz = ET.parse(caminho).getroot()
    cristal = raiz.find("structure/crystal")
    L = float(cristal.get("scale")) * np.array(
        [[float(x) for x in v.text.split()] for v in cristal.findall("basevect")]) * BOHR_A
    print(f"\n  validacao de {caminho}")
    for i in range(3):
        print(f"    |a_{i+1}| = {np.linalg.norm(L[i]):.10f} A    (a_R = {a_r:.10f})")
    for i, j in ((0, 1), (0, 2), (1, 2)):
        print(f"    a_{i+1}.a_{j+1} = {L[i] @ L[j]:+.10f} A^2  (a_R^2 cos alfa = {a_r**2 * cos_alfa:+.10f})")
    print(f"    eixo de ordem 3 ao longo de z: a_1+a_2+a_3 = {np.round(L.sum(axis=0), 10)}")
    pos, num, nomes = [], [], []
    for z, esp in enumerate(raiz.findall("structure/species")):
        nomes.append(esp.get("speciesfile").replace(".xml", ""))
        for a in esp.findall("atom"):
            pos.append([float(x) for x in a.get("coord").split()])
            num.append(z + 1)
    P, N = np.array(pos), np.array(num)
    desl = np.array(list(itertools.product((-1, 0, 1), repeat=3)))
    def vizinhos(a, b, k):
        ia, ib = nomes.index(a) + 1, nomes.index(b) + 1
        return np.sort([np.linalg.norm((q + s - p) @ L) for p in P[N == ia] for q in P[N == ib] for s in desl])[:k]
    if len(set(nomes) & set(nomes_axb)) == 3:
        A, B, X = nomes_axb
        bx, ax = vizinhos(B, X, 6), vizinhos(A, X, 12)
        print(f"    {B}-{X} (6 vizinhos): {np.round(bx, 4)} A   medio {bx.mean():.4f}   delta-d {bx.max() - bx.min():.4f}")
        print(f"    {A}-{X} (12 vizinhos): medio {ax.mean():.4f} A")
    try:
        import spglib
    except ImportError:
        print("    (spglib ausente: grupo espacial nao conferido - ver bin/simetria-poscar.py)")
        return
    ds = spglib.get_symmetry_dataset((L, np.array(pos), num), symprec=symprec)
    print(f"    spglib (symprec {symprec:g} A): {ds.international} ({ds.number}), "
          f"{len(ds.rotations)} operacoes de simetria")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="input.xml da fase cubica Pm-3m")
    ap.add_argument("--saida", required=True, help="input.xml a escrever")
    ap.add_argument("--aH", type=float, help="a hexagonal (A)")
    ap.add_argument("--cH", type=float, help="c hexagonal (A)")
    ap.add_argument("--aR", type=float, help="aresta romboedrica (A)")
    ap.add_argument("--alfa", type=float, help="angulo romboedrico (graus)")
    ap.add_argument("--teste-cubico", action="store_true",
                    help="alfa = 90 e a_R = parametro da base: tem de dar Pm-3m (221)")
    ap.add_argument("--transladar", action="store_true",
                    help="base com A na origem: desloca tudo por (1/2,1/2,1/2)")
    ap.add_argument("--manter-origem", action="store_true",
                    help="base com A na origem: mantem (X fica em 3e, tambem sem parametro livre)")
    ap.add_argument("--A", default="Cs"); ap.add_argument("--B", default="Sn"); ap.add_argument("--X", default="Br")
    ap.add_argument("--titulo", default="")
    ap.add_argument("--deslocar-B", type=float, default=0.0, metavar="DELTA",
                    help="desloca o metal B de DELTA angstrom ao longo do eixo de ordem 3 "
                         "(fase ferroeletrica R3m, 160)")
    ap.add_argument("--symprec", type=float, default=1e-5)
    args = ap.parse_args()

    arvore, a_cub, origem = le_base(args.base, {"A": args.A, "B": args.B, "X": args.X})
    print(f"base: cubica, a = {a_cub:.10f} A, origem no {'metal ' + args.B if origem == 'B' else 'cation ' + args.A}")
    if args.transladar and args.manter_origem:
        sys.exit("ERRO: --transladar e --manter-origem sao excludentes")
    if origem == "A" and not (args.transladar or args.manter_origem):
        sys.exit(f"PARADO: a base tem {args.A} na origem. O ajuste descrito (B em 1a, A em 1b,\n"
                 f"X em 3d) pede uma translacao de (1/2,1/2,1/2). Os dois ajustes sao o mesmo\n"
                 f"cristal. Rode de novo com --transladar ou com --manter-origem.")
    if origem == "B" and args.transladar:
        sys.exit("ERRO: a base ja tem o metal na origem; --transladar a tiraria de la.")

    if args.teste_cubico:
        a_r, cos_alfa = a_cub, 0.0
    elif args.aH and args.cH:
        a_r = math.sqrt(3 * args.aH**2 + args.cH**2) / 3
        cos_alfa = (2 * args.cH**2 - 3 * args.aH**2) / (2 * args.cH**2 + 6 * args.aH**2)
    elif args.aR and args.alfa:
        a_r, cos_alfa = args.aR, math.cos(math.radians(args.alfa))
    else:
        sys.exit("ERRO: de --aH e --cH, ou --aR e --alfa, ou --teste-cubico")
    alfa = math.degrees(math.acos(cos_alfa))
    print(f"a_R = {a_r:.10f} A = {a_r / BOHR_A:.10f} bohr   alfa = {alfa:.6f} graus   cos alfa = {cos_alfa:+.3e}")

    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    gera(arvore, a_r, cos_alfa, args.transladar, args.titulo,
         nome_b=args.B, delta_b=args.deslocar_B).write(saida, encoding="unicode")
    with open(saida, "a") as f:
        f.write("\n")
    print(f"escrito: {saida}")
    valida(saida, a_r, cos_alfa, args.symprec, nomes_axb=(args.A, args.B, args.X))


if __name__ == "__main__":
    main()
