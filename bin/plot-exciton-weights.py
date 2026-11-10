#!/usr/bin/env python3
"""Plota as bandas com os pesos excitonicos."""
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib
import numpy as np

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("arquivo", nargs="*", default=None,
                    help="arquivos KPATH_*_LAMBDA*.OUT explicitos (default: acha "
                         "sozinho pelos numeros de --lambda)")
parser.add_argument("-d", "--dir", default=".",
                    help="pasta do calculo ou a propria KPATHEXC (default: .)")
parser.add_argument("-l", "--lambda", dest="lambdas", type=int, nargs="+", default=[1],
                    metavar="N", help="numeros dos excitons a plotar (default: 1)")
parser.add_argument("-y", "--ylim", type=float, nargs=2, default=[-10.0, 15.0],
                    metavar=("MIN", "MAX"), help="janela de energia em eV (default: -10 15)")
parser.add_argument("-s", "--scale", type=float, default=1.0,
                    help="tamanho dos circulos de peso (default: 1.0)")
parser.add_argument("-t", "--title", default=None, help="default: titulo do input.xml")
parser.add_argument("-o", "--out", default=None,
                    help="default: exciton-weights-lambdaN.png na pasta do calculo")
parser.add_argument("--registro", action="store_true",
                    help="ja copia a figura para figuras/ da semana atual do registro")
parser.add_argument("--show", action="store_true", help="abre a janela interativa")
args = parser.parse_args()

if not args.show:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt


def resolve_pastas(pasta):
    p = Path(pasta).resolve()
    if p.name == "KPATHEXC":
        return p.parent, p
    return p, p / "KPATHEXC"


run, kpathexc = resolve_pastas(args.dir)

if args.arquivo:
    arquivos = [Path(a) if Path(a).is_absolute() else Path(a).resolve()
                for a in args.arquivo]
    faltando = [a for a in arquivos if not a.is_file()]
    if faltando:
        sys.exit("nao achei: " + ", ".join(str(a) for a in faltando))
    run, kpathexc = resolve_pastas(arquivos[0].parent)
else:
    if not kpathexc.is_dir():
        sys.exit(f"nao achei {kpathexc}.\nRode o exciting com <doonly task=\"writekpathweights\"/> "
                 "no <plan> do <xs>.")
    arquivos = []
    for n in args.lambdas:
        achados = sorted(kpathexc.glob(f"KPATH_*_LAMBDA{n:06d}.OUT"))
        if not achados:
            disponiveis = sorted(int(m.group(1)) for f in kpathexc.glob("KPATH_*_LAMBDA*.OUT")
                                 for m in [re.search(r"LAMBDA(\d+)\.OUT$", f.name)] if m)
            sys.exit(f"nao ha KPATH_*_LAMBDA{n:06d}.OUT em {kpathexc}.\n"
                     f"excitons disponiveis: {disponiveis or 'nenhum'}")
        if len(achados) > 1:
            print(f"aviso: mais de um KPATH para lambda={n}, usando {achados[0].name}")
        arquivos.append(achados[0])


def le_kpath(caminho):
    blocos, atual = [], []
    for linha in caminho.read_text().splitlines():
        s = linha.strip()
        if s.startswith("#"):
            continue
        if not s:
            if atual:
                blocos.append(atual)
                atual = []
            continue
        atual.append([float(x) for x in s.split()])
    if atual:
        blocos.append(atual)
    if not blocos:
        sys.exit(f"{caminho.name} nao tem dados")
    tamanhos = {len(b) for b in blocos}
    if len(tamanhos) > 1:
        sys.exit(f"{caminho.name}: bandas com numeros de pontos diferentes {sorted(tamanhos)}")
    dados = np.array(blocos)
    return dados[:, :, 0], dados[:, :, 1], dados[:, :, 2]


def le_bandlines(pasta):
    caminho = pasta / "BANDLINES.OUT"
    if not caminho.is_file():
        return None
    xs = [float(l.split()[0]) for l in caminho.read_text().splitlines() if l.strip()]
    vertices = []
    for x in xs:
        if not vertices or abs(x - vertices[-1]) > 1e-8:
            vertices.append(x)
    return vertices


GREGAS = {"GAMMA": r"$\Gamma$", "DELTA": r"$\Delta$", "SIGMA": r"$\Sigma$",
          "LAMBDA": r"$\Lambda$", "PI": r"$\Pi$"}


def le_rotulos(pasta):
    caminho = pasta / "input.xml"
    if not caminho.is_file():
        return None
    raiz = ET.parse(caminho).getroot()
    caminho_k = raiz.find("./properties/bandstructure/plot1d/path")
    if caminho_k is None:
        return None
    rotulos = []
    for ponto in caminho_k.findall("point"):
        r = (ponto.get("label") or "").strip()
        rotulos.append(GREGAS.get(r.upper(), r))
    return rotulos or None


def energia_do_exciton(pasta, arquivo_kpath, n):
    m = re.match(r"KPATH_(.+)_QMT\d+_LAMBDA\d+\.OUT$", arquivo_kpath.name)
    if not m:
        return None
    candidatos = sorted((pasta / "EXCITON").glob(f"EXCITON_{m.group(1)}_OC11.OUT"))
    if not candidatos:
        candidatos = sorted((pasta / "EXCITON").glob(f"EXCITON_{m.group(1)}_OC*.OUT"))
    if not candidatos:
        return None
    for linha in candidatos[0].read_text().splitlines():
        campos = linha.split()
        if len(campos) >= 2 and not linha.lstrip().startswith("#") and campos[0] == str(n):
            return float(campos[1])
    return None


def titulo_do_input(pasta):
    caminho = pasta / "input.xml"
    if caminho.is_file():
        t = ET.parse(caminho).getroot().findtext("title")
        if t and t.strip():
            return t.strip()
    return None


vertices = le_bandlines(run)
rotulos = le_rotulos(run)
sistema = args.title or titulo_do_input(run) or run.name

n_paineis = len(arquivos)
fig, axes = plt.subplots(1, n_paineis, figsize=(6.0 * n_paineis, 7.0),
                         sharey=True, squeeze=False)
axes = axes[0]

lambdas = []
for eixo, arquivo in zip(axes, arquivos):
    m = re.search(r"LAMBDA(\d+)\.OUT$", arquivo.name)
    n = int(m.group(1)) if m else 0
    lambdas.append(n)
    k, energia, peso = le_kpath(arquivo)

    for banda in range(k.shape[0]):
        eixo.plot(k[banda], energia[banda], color="tab:blue", lw=1.6, zorder=10)
    tamanho = (200.0 * args.scale * peso) ** 2
    eixo.scatter(k.ravel(), energia.ravel(), s=tamanho.ravel(), lw=1.6,
                 edgecolor="tab:red", facecolor="none", zorder=11)

    xmin, xmax = float(k.min()), float(k.max())
    eixo.set_xlim(xmin, xmax)
    eixo.set_ylim(*args.ylim)
    eixo.axhline(0.0, color="0.35", lw=1.2, ls="-", zorder=9)
    if vertices:
        for x in vertices[1:-1]:
            eixo.axvline(x, color="0.6", lw=0.9, zorder=8)
        if rotulos and len(rotulos) == len(vertices):
            eixo.set_xticks(vertices)
            eixo.set_xticklabels(rotulos)
        else:
            eixo.set_xticks(vertices)
            eixo.set_xticklabels([""] * len(vertices))
    eixo.grid(True, axis="y", ls=":", lw=0.7, alpha=0.6)

    energia_exc = energia_do_exciton(run, arquivo, n)
    sub = f"exciton $\\lambda$ = {n}"
    if energia_exc is not None:
        sub += f"   ($E$ = {energia_exc:.3f} eV)"
    eixo.set_title(sub, fontsize=12)
    peso_max = float(peso.max())
    eixo.text(0.015, 0.015, f"peso max = {peso_max:.4f}", transform=eixo.transAxes,
              va="bottom", ha="left", fontsize=9, color="0.35",
              bbox=dict(facecolor="white", edgecolor="none", alpha=0.75, pad=2))

axes[0].set_ylabel("Energia [eV]")
axes[-1].annotate("$E_F$", xy=(1.0, 0.0), xycoords=("axes fraction", "data"),
                  xytext=(4, 0), textcoords="offset points", va="center", fontsize=11)
fig.suptitle(f"Pesos excitonicos - {sistema}", fontsize=14)
fig.tight_layout()

if args.out:
    saida = Path(args.out)
    if not saida.is_absolute():
        saida = run / saida
else:
    nome = "exciton-weights-lambda" + "-".join(str(n) for n in lambdas) + ".png"
    saida = run / nome
fig.savefig(saida, dpi=200)
print(f"grafico salvo em: {saida}")

alvo = f"exciton {lambdas[0]}" if len(lambdas) == 1 else \
       "excitons " + ", ".join(str(n) for n in lambdas)
legenda = f"Pesos excitonicos do {sistema} sobre a estrutura de bandas - {alvo}"

add_figura = Path(__file__).resolve().parent.parent / "registros" / "_scripts" / "add-figura.sh"
linha_img = f"![{legenda}]({saida.name})"
if args.registro and add_figura.is_file():
    import subprocess
    r = subprocess.run([str(add_figura), "-f", str(saida), "-l", legenda],
                       capture_output=True, text=True)
    sys.stderr.write(r.stderr)
    if r.returncode == 0 and r.stdout.strip():
        linha_img = r.stdout.strip().splitlines()[0]
    else:
        sys.exit(r.returncode or 1)
elif add_figura.is_file():
    linha_img = f"![{legenda}](figuras/{saida.name})"

print("\n" + "─" * 30 + " para colar no REGISTRO.md " + "─" * 30)
print(linha_img)
print(f"*{legenda}*")
print("─" * 87)
if not args.registro:
    print("A figura ainda esta em runs/. Para copia-la para a semana (e usar o caminho "
          "acima),\nrode de novo com --registro, ou:")
    print(f"  registros/_scripts/add-figura.sh -f '{saida}' -l '{legenda}'")

if args.show:
    plt.show()
