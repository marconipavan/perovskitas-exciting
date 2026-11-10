#!/usr/bin/env python3
"""Comprimentos medios de ligacao Cs-X e M-X de uma fase."""
import argparse
import itertools
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

BOHR_A = 0.52917721092

N_VIZINHOS = {"metal": 6, "cs": 12}


def le_estrutura(caminho):
    raiz = ET.parse(caminho).getroot()
    cristal = raiz.find("structure/crystal")
    if cristal is None:
        raise ValueError(f"{caminho}: nao tem <structure><crystal>")
    escala = float(cristal.get("scale", "1.0"))
    rede = np.array([[float(x) for x in b.text.split()]
                     for b in cristal.findall("basevect")]) * escala

    posicoes = {}
    for especie in raiz.findall("structure/species"):
        nome = especie.get("speciesfile", "").replace(".xml", "")
        posicoes[nome] = np.array([[float(x) for x in a.get("coord").split()]
                                   for a in especie.findall("atom")])
    return rede, posicoes


def vizinhos(rede, centros, alvos, n):
    deslocamentos = np.array(list(itertools.product((-1, 0, 1), repeat=3)))
    por_centro = []
    for centro in centros:
        distancias = [np.linalg.norm((alvo + d - centro) @ rede)
                      for alvo in alvos for d in deslocamentos]
        por_centro.append(np.sort(np.array(distancias))[:n])
    return np.array(por_centro)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="um ou mais input.xml")
    ap.add_argument("--metal", default="Sn", help="metal divalente (default: Sn)")
    ap.add_argument("--anion", default="Br", help="halogenio (default: Br)")
    ap.add_argument("--cs", default="Cs", help="metal monovalente (default: Cs)")
    args = ap.parse_args()

    print(f"{'fase':28s} {'Cs-X':>6s} {'M-X':>6s} {'min':>6s} {'max':>6s} {'dd':>6s}"
          "   (angstrom)")
    houve_erro = False
    for caminho in args.inputs:
        try:
            rede, pos = le_estrutura(caminho)
            faltando = [e for e in (args.cs, args.metal, args.anion) if e not in pos]
            if faltando:
                raise ValueError(f"especies ausentes: {', '.join(faltando)}")
            cs = vizinhos(rede, pos[args.cs], pos[args.anion],
                          N_VIZINHOS["cs"]) * BOHR_A
            mx = vizinhos(rede, pos[args.metal], pos[args.anion],
                          N_VIZINHOS["metal"]) * BOHR_A
        except (ET.ParseError, ValueError, OSError) as erro:
            print(f"{Path(caminho).parent.name:28s} ERRO: {erro}", file=sys.stderr)
            houve_erro = True
            continue

        print(f"{Path(caminho).parent.name:28s} "
              f"{cs.mean():6.2f} {mx.mean():6.2f} "
              f"{mx.min():6.2f} {mx.max():6.2f} {mx.max() - mx.min():6.2f}")

    return 1 if houve_erro else 0


if __name__ == "__main__":
    sys.exit(main())
