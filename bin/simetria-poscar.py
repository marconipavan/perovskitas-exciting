#!/usr/bin/env python3
"""Mostra o grupo espacial de cada POSCAR."""
import sys
from pathlib import Path

import numpy as np

try:
    import spglib
except ImportError:
    sys.exit(__doc__.split("Uso:")[0].strip() + "\n\nERRO: spglib nao instalado.")

IC = Path(__file__).resolve().parent.parent
FASES = ["pm3m", "p4mbm", "i4mcm", "gamma", "r3m", "r3c", "delta"]
TOLERANCIAS = (1e-5, 1e-3, 1e-2, 0.05, 0.1, 0.2, 0.3, 0.5)


def le_poscar(caminho):
    linhas = Path(caminho).read_text().splitlines()
    escala = float(linhas[1].split()[0])
    rede = np.array([[float(x) for x in linhas[i].split()[:3]] for i in (2, 3, 4)]) * escala
    quantos = [int(x) for x in linhas[6].split()]
    i = 8 if not linhas[7].strip().lower().startswith("s") else 9
    pos, num = [], []
    for z, n in enumerate(quantos):
        for _ in range(n):
            pos.append([float(x) for x in linhas[i].split()[:3]])
            num.append(z + 1)
            i += 1
    return rede, np.array(pos), num


def main():
    fases = sys.argv[1:] or FASES
    for fase in fases:
        cel = le_poscar(IC / "estruturas" / "CsSnBr3" / f"POSCAR.{fase}")
        grupos = [spglib.get_spacegroup(cel, symprec=t) for t in TOLERANCIAS]
        estavel = len(set(grupos)) == 1
        print(f"{fase:6s} {grupos[0]:16s} "
              + ("(igual em todas as tolerâncias, 1e-5 a 0,5 Å)" if estavel
                 else " -> ".join(f"{t:g}: {g}" for t, g in zip(TOLERANCIAS, grupos))))


if __name__ == "__main__":
    main()
