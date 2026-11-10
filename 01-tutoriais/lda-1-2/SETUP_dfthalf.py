"""Prepara as pastas da varredura de raio de corte do DFT-1/2."""
import os
import sys
from lxml import etree

if __name__ == '__main__':
    if len(sys.argv) <= 1:
        raise Exception("Esqueceu de passar o nome da pasta!!")
    pasta = sys.argv[1]

    inputxml = "input.xml"
    if not os.path.exists(inputxml):
        raise Exception(f"Esqueceu do input.xml!")

    print("Preciso que você me informe...")
    cut_min = float(input("R cut min: "))
    cut_max = float(input("R cut max: "))
    steps = 0
    while steps <= 0:
        steps = int(input("Steps: "))

    delta = (cut_max - cut_min)/(steps - 1) if steps > 1 else 0
    raios = [cut_min + i*delta for i in range(steps)]

    os.makedirs(pasta, exist_ok=True)
    tree = etree.parse(inputxml)
    especie = "N.xml"
    alvo = tree.xpath(f'/input/structure/species[@speciesfile="{especie}"]/dfthalfparam')
    if not alvo:
        alvo = tree.xpath('/input/structure/species/dfthalfparam')
    dfthalf = alvo[-1]

    for i, r in enumerate(raios):
        dfthalf.set("cut", f"{r:.10f}")
        saida = os.path.join(pasta, f"input-{i+1:02d}.xml")
        with open(saida, "wb") as f:
            f.write(etree.tostring(tree, pretty_print=True))

        strain = os.path.join(pasta, f"strain-{i+1:02d}")
        with open(strain, "w") as f:
            f.write(f"{r:20.8f}\n")

    open(os.path.join(pasta, "dft-0.5"), "w").close()
    with open(inputxml, "r") as src, open(os.path.join(pasta, "source.xml"), "w") as dst:
        dst.write(src.read())

    print(f"\nGerados {steps} inputs em '{pasta}/' (r_cut de {cut_min} a {cut_max}).")
