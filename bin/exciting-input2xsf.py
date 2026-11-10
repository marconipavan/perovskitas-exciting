#!/usr/bin/env python3
"""Converte um input.xml do exciting para XSF (XCrySDen)."""
import sys
import xml.etree.ElementTree as ET

BOHR2ANG = 0.52917721067


def main():
    inp = sys.argv[1] if len(sys.argv) > 1 else "input.xml"
    out = sys.argv[2] if len(sys.argv) > 2 else "structure.xsf"

    root = ET.parse(inp).getroot()
    structure = root.find("structure")
    crystal = structure.find("crystal")

    scale = float(crystal.get("scale", "1.0"))
    avecs = []
    for bv in crystal.findall("basevect"):
        comps = [float(x) for x in bv.text.split()]
        avecs.append([scale * c for c in comps])

    atoms = []
    for sp in structure.findall("species"):
        symbol = sp.get("speciesfile", "X.xml").split("/")[-1].rsplit(".", 1)[0]
        for at in sp.findall("atom"):
            f = [float(x) for x in at.get("coord").split()]
            cart = [
                f[0] * avecs[0][i] + f[1] * avecs[1][i] + f[2] * avecs[2][i]
                for i in range(3)
            ]
            atoms.append((symbol, *cart))

    with open(out, "w") as fh:
        fh.write("CRYSTAL\nPRIMVEC\n")
        for v in avecs:
            fh.write("  {:18.10f}{:18.10f}{:18.10f}\n".format(*[c * BOHR2ANG for c in v]))
        fh.write("PRIMCOORD\n  {}  1\n".format(len(atoms)))
        for sym, x, y, z in atoms:
            fh.write("  {:<3s}{:18.10f}{:18.10f}{:18.10f}\n".format(
                sym, x * BOHR2ANG, y * BOHR2ANG, z * BOHR2ANG))

    print("OK -> {} ({} atomos, scale={} Bohr)".format(out, len(atoms), scale))


if __name__ == "__main__":
    main()
