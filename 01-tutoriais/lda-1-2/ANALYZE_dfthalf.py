"""Le os gaps da varredura de raio de corte do DFT-1/2."""
import os
import sys
import glob
from lxml import etree
import matplotlib.pyplot as plt

HARTREE_EV = 27.211396132


def ler_cut(input_path, especie="N.xml"):
    tree = etree.parse(input_path)
    cut = tree.xpath(f'/input/structure/species[@speciesfile="{especie}"]/dfthalfparam/@cut')
    if not cut:
        cut = tree.xpath('/input/structure/species/dfthalfparam/@cut')
    return float(cut[-1])


def ler_gap(info_path):
    gap_ha = None
    with open(info_path, "r") as f:
        for linha in f:
            if "Estimated fundamental gap" in linha:
                gap_ha = float(linha.split(":")[1])
    if gap_ha is None:
        raise ValueError(f"Nenhum gap encontrado em {info_path}")
    return gap_ha*HARTREE_EV


if __name__ == '__main__':
    base = sys.argv[1] if len(sys.argv) > 1 else "."

    dados = []
    for rundir in sorted(glob.glob(os.path.join(base, "run*"))):
        input_path = os.path.join(rundir, "input.xml")
        info_path = os.path.join(rundir, "INFO.OUT")
        if not (os.path.exists(input_path) and os.path.exists(info_path)):
            print(f"  (pulando {rundir}: falta input.xml ou INFO.OUT)")
            continue
        r_cut = ler_cut(input_path)
        gap = ler_gap(info_path)
        dados.append((r_cut, gap))

    dados.sort()

    if not dados:
        sys.exit("Nenhuma run válida encontrada!")

    raios = [d[0] for d in dados]
    gaps = [d[1] for d in dados]

    saida = os.path.join(base, "bandgap-vs-rcut.dat")
    with open(saida, "w") as f:
        f.write("# r_cut[Bohr]        gap[eV]\n")
        for r, g in dados:
            f.write(f"{r:12.6f}   {g:12.6f}\n")

    print("\n r_cut[Bohr]    gap[eV]")
    print(" " + "-" * 24)
    for r, g in dados:
        print(f" {r:8.3f}    {g:8.4f}")

    g_max = max(gaps)
    r_otimo = raios[gaps.index(g_max)]
    print(f"\n>>> Gap máximo = {g_max:.4f} eV  em  r_cut = {r_otimo:.3f} Bohr")
    print(f">>> Dados salvos em {saida}")

    plt.figure(figsize=(7, 5))
    plt.plot(raios, gaps, "o-", color="steelblue", label="LDA-1/2")
    plt.plot(r_otimo, g_max, "r*", markersize=16,
             label=f"máx: {g_max:.3f} eV @ {r_otimo:.2f} Bohr")
    plt.xlabel(r"$r_{cut}$ [Bohr]")
    plt.ylabel("Bandgap [eV]")
    plt.title("GaN - LDA-1/2: bandgap vs. raio de corte")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    png = os.path.join(base, "bandgap-vs-rcut.png")
    plt.savefig(png, dpi=150)
    print(f">>> Gráfico salvo em {png}")
    plt.show()
