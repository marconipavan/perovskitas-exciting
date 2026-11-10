#!/usr/bin/env python3
"""Compara os espectros de uma varredura de convergencia."""
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib
import numpy as np

import leitura

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("prefixo", nargs="*", default=None,
                    help="prefixo das subpastas (ex.: nempty, nstlbse_25), padrao com "
                         "curinga entre aspas (ex.: 'nstlbse_*514'), ou varias pastas "
                         "nomeadas uma a uma (ex.: bsetype_singlet beyond_TDA). "
                         "Se omitido, detecta sozinho.")
parser.add_argument("-d", "--dir", default=".", help="pasta com as subpastas (default: .)")
parser.add_argument("-f", "--file", default="singlet-TDA", help="arquivo dentro de cada subpasta")
parser.add_argument("--col", type=int, default=3, help="coluna do eixo y, base 1 (default: 3 = Im)")
parser.add_argument("-x", "--xlim", type=float, nargs=2, default=[0.0, 27.0], metavar=("MIN", "MAX"))
parser.add_argument("-y", "--ylim", type=float, nargs=2, default=None, metavar=("MIN", "MAX"))
parser.add_argument("-t", "--title", default="Macroscopic dielectric function")
parser.add_argument("-lx", "--xlabel", default="Energy [eV]")
parser.add_argument("-ly", "--ylabel", default=None, help="default: depende de --col")
parser.add_argument("-o", "--out", default=None, help="default: <prefixo>-comparison.png")
parser.add_argument("--diff", action="store_true",
                    help="painel extra com a diferenca para a rodada de referencia")
parser.add_argument("--janela-pico", type=float, default=1.0, metavar="eV",
                    help="largura da busca do pico em torno do pico da referencia "
                         "(default: 1.0 eV) - garante que se compara o mesmo pico")
parser.add_argument("--registro", action="store_true",
                    help="ja copia a figura para figuras/ da semana atual do registro")
parser.add_argument("--show", action="store_true", help="abre a janela interativa")
args = parser.parse_args()

if not args.show:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt

base = Path(args.dir).resolve()


def tem_curinga(padrao):
    return any(c in padrao for c in "*?[")


def numero(nome, prefixo):
    if tem_curinga(prefixo):
        return tuple(int(d) for d in re.findall(r"\d+", nome)) or (0,)
    achado = re.search(rf"{re.escape(prefixo)}_?(\d+)", nome)
    return (int(achado.group(1)),) if achado else (0,)


def varreduras_em(pasta):
    contagem = {}
    for p in pasta.iterdir():
        if not p.is_dir():
            continue
        achado = re.fullmatch(r"(.+?)_(\d+)", p.name)
        if achado:
            contagem.setdefault(achado.group(1), []).append(p)
    return {k: v for k, v in contagem.items() if len(v) > 1}


def detecta_prefixo(pasta):
    candidatos = varreduras_em(pasta)
    if not candidatos:
        sys.exit(f"ERRO: nenhuma varredura PREFIXO_* encontrada em {pasta}")
    if len(candidatos) > 1:
        sys.exit("ERRO: ha mais de uma varredura nesta pasta - diga qual:\n" +
                 "".join(f"    plot-convergencia.py {k}\n" for k in sorted(candidatos)))
    return next(iter(candidatos))


def resolve_base(pasta, prefixo):
    tem = ((lambda d: any(espectro(p) is not None
                      for p in d.glob(prefixo if tem_curinga(prefixo) else f"{prefixo}*")))
           if prefixo else (lambda d: bool(varreduras_em(d))))
    if tem(pasta):
        return pasta
    if pasta.parent != pasta and tem(pasta.parent):
        print(f"[plot] {pasta.name}/ nao tem a varredura; usando a pasta-mae "
              f"{pasta.parent.name}/")
        return pasta.parent
    return pasta


def espectro(run, avisar=False):
    return leitura.espectro(run, args.file, avisar)


def rotulos(pastas, prefixo):
    planos = {p: leitura.plano_input(p) for p in pastas}
    if all(planos.values()):
        todas = set().union(*(set(v) for v in planos.values()))
        variam = sorted(k for k in todas if len({planos[p].get(k) for p in pastas}) > 1)
        if variam:
            valores = {p: {planos[p].get(k) for k in variam} for p in pastas}
            if all(len(v) == 1 for v in valores.values()):
                nome = "/".join(k.rsplit("@", 1)[1] for k in variam)
                return {p: f"{nome} = {leitura.bonito(next(iter(valores[p])))}"
                        for p in pastas}
            nome = variam[0].rsplit("@", 1)[1]
            return {p: f"{nome} = {planos[p].get(variam[0], '?')}" for p in pastas}
    if tem_curinga(prefixo):
        return {p: p.name for p in pastas}
    return {p: f"{prefixo} = {numero(p.name, prefixo)[0]}" for p in pastas}


argumentos = [pedaco for a in (args.prefixo or []) for pedaco in a.split()
              if pedaco not in ("-", ".", "")]

base = resolve_base(base, argumentos[0] if len(argumentos) == 1 else "")
if not argumentos:
    argumentos = [detecta_prefixo(base)]

pastas = []
for arg in argumentos:
    padrao = arg if tem_curinga(arg) else f"{arg}*"
    achadas = sorted((p for p in base.glob(padrao) if espectro(p) is not None),
                     key=lambda p: numero(p.name, arg))
    if not achadas:
        sys.exit(f"ERRO: nenhuma pasta {padrao} com {args.file} ou EPSILON/ em {base}")
    pastas += [p for p in achadas if p not in pastas]

varredura = len(argumentos) == 1
etiqueta = argumentos[0] if varredura else " + ".join(argumentos)
nomes = rotulos(pastas, argumentos[0]) if varredura else {p: p.name for p in pastas}

ylabel = args.ylabel
if ylabel is None:
    ylabel = r"Im $\varepsilon_M$" if args.col == 3 else r"Re $\varepsilon_M$"

plt.rcParams.update({"font.size": 13, "axes.linewidth": 1.2,
                     "xtick.direction": "in", "ytick.direction": "in"})

if args.diff:
    fig, (ax, axd) = plt.subplots(2, 1, figsize=(8, 7.5), sharex=True,
                                  gridspec_kw={"height_ratios": [3, 1]})
else:
    fig, ax = plt.subplots(figsize=(8, 5.5))
    axd = None

colors = plt.cm.viridis(np.linspace(0.15, 0.85, len(pastas)))
styles = ["-", "--", ":", "-."]
widths = np.linspace(3.0, 1.2, len(pastas))

curvas = {}
print(f"{'varredura de' if varredura else 'comparacao entre'} '{etiqueta}' em {base}:")
for i, (run, color) in enumerate(zip(pastas, colors)):
    arq = espectro(run, avisar=True)
    dados = np.loadtxt(arq, comments="#")
    x, y = dados[:, 0], dados[:, args.col - 1]
    curvas[run] = (x, y)
    print(f"  {run.name:<16} {arq.relative_to(base)}")
    ax.plot(x, y, ls=styles[i % len(styles)], lw=widths[i], color=color, label=nomes[run])

ax.set_ylabel(ylabel)
ax.set_title(args.title)
ax.set_xlim(*args.xlim)
if args.ylim:
    ax.set_ylim(*args.ylim)
ax.grid(True, ls=":", lw=0.7, alpha=0.7)
ax.legend(frameon=False)

ref = pastas[-1]
xr, yr = curvas[ref]
mascara = (xr >= args.xlim[0]) & (xr <= args.xlim[1])

if axd is not None:
    for i, run in enumerate(pastas):
        x, y = curvas[run]
        if run is ref or x.shape != xr.shape:
            continue
        axd.plot(x, y - yr, ls=styles[i % len(styles)], lw=widths[i], color=colors[i],
                 label=f"{nomes[run].split(' = ')[-1]} − {nomes[ref].split(' = ')[-1]}")
    axd.axhline(0, color="0.6", lw=0.8)
    axd.set_ylabel(r"$\Delta$")
    axd.grid(True, ls=":", lw=0.7, alpha=0.7)
    axd.legend(frameon=False, fontsize=10, ncol=2, loc="upper right")
    axd.set_xlabel(args.xlabel)
else:
    ax.set_xlabel(args.xlabel)

fig.tight_layout()
sufixo = "-comparison-diff.png" if args.diff else "-comparison.png"
nome_base = re.sub(r"[*?]", "x", "-vs-".join(argumentos) if not varredura else argumentos[0])
nome_base = re.sub(r"[\[\]]", "", nome_base).strip("_-") or "comparacao"
saida = Path(args.out) if args.out else base / f"{nome_base}{sufixo}"
if not saida.is_absolute():
    saida = base / saida
fig.savefig(saida, dpi=200)
print(f"\ngrafico salvo em: {saida}")

t_ref = leitura.tempo(ref)
pico_ref = xr[mascara][np.argmax(yr[mascara])]


def pico_rastreado(x, y):
    return leitura.pico_na_janela(x, y, mascara, pico_ref, args.janela_pico)


altura_ref = pico_rastreado(xr, yr)[1]

def valor(rotulo):
    return rotulo.split(" = ")[-1]


partido = [n.split(" = ", 1) for n in nomes.values()]
if all(len(p) == 2 for p in partido) and len({p[0] for p in partido}) == 1:
    parametro = partido[0][0]
else:
    parametro = etiqueta

print(f"\ncomparacao na faixa {args.xlim[0]:g}-{args.xlim[1]:g} eV "
      f"(referencia: {nomes[ref]}):\n")
trocou_algum = False
linhas = []
for run in pastas:
    x, y = curvas[run]
    t = leitura.tempo(run)
    pico, altura, trocou = pico_rastreado(x, y)
    trocou_algum |= trocou

    linha = {
        "rotulo": valor(nomes[run]),
        "tempo": f"{t:.2f}" if t is not None else "-",
        "custo": f"{t / t_ref:.2f}×" if (t and t_ref) else "-",
        "pico": f"{pico:.3f}" + ("*" if trocou else ""),
        "altura": f"{altura:.2f}",
    }
    if run is ref:
        linha.update({"dpico": "(ref)", "daltura": "(ref)", "dif": "-", "pct": "-"})
    else:
        linha["dpico"] = f"{(pico - pico_ref) * 1000:.1f}"
        linha["daltura"] = f"{100 * (altura - altura_ref) / altura_ref:.1f}%"
        if x.shape != xr.shape or not np.allclose(x, xr):
            linha.update({"dif": "malha diferente", "pct": "-"})
        else:
            dif = np.abs(y[mascara] - yr[mascara]).max()
            linha["dif"] = f"{dif:.4f}"
            linha["pct"] = f"{100 * dif / np.abs(yr[mascara]).max():.2f}%"
    linhas.append(linha)

COLUNAS = [("rotulo", parametro, max(14, len(parametro))),
           ("tempo", "tempo (s)", 10), ("custo", "custo", 7),
           ("pico", "pico (eV)", 11), ("dpico", "d pico (meV)", 13),
           ("altura", "altura", 8), ("daltura", "d altura", 9),
           ("dif", "max |dif|", 15), ("pct", "% do pico", 10)]

cab = " ".join(f"{titulo:<{w}}" if chave == "rotulo" else f"{titulo:>{w}}"
               for chave, titulo, w in COLUNAS)
print(cab)
print("-" * len(cab))
for linha in linhas:
    print(" ".join(f"{linha[chave]:<{w}}" if chave == "rotulo" else f"{linha[chave]:>{w}}"
                   for chave, _, w in COLUNAS))

print(f"\n'custo' = tempo relativo a referencia")
print(f"'pico'  = maximo dentro de ±{args.janela_pico:g} eV do pico da referencia "
      f"({pico_ref:.3f} eV), para comparar sempre o mesmo pico")
if trocou_algum:
    print("   *    = nesta rodada o maximo global do espectro esta FORA dessa janela, "
          "ou seja,\n          o pico dominante e outro - o espectro ainda nao tem a forma correta")


def titulo_do_input(run):
    caminho = run / "input.xml"
    if caminho.is_file():
        t = ET.parse(caminho).getroot().findtext("title")
        if t and t.strip():
            return t.strip()
    return None


sistema = titulo_do_input(pastas[0])
legenda = (f"{ylabel} - {parametro} de {valor(nomes[pastas[0]])} a {valor(nomes[ref])}")
if sistema:
    legenda = f"{ylabel} do {sistema} - {parametro} de " \
              f"{valor(nomes[pastas[0]])} a {valor(nomes[ref])}"

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

titulos_md = {chave: titulo.replace("|", "\\|") for chave, titulo, _ in COLUNAS}
larguras = {chave: max(len(titulos_md[chave]), max(len(l[chave]) for l in linhas))
            for chave, _, _ in COLUNAS}
md_cab = "| " + " | ".join(f"{titulos_md[chave]:<{larguras[chave]}}"
                           for chave, _, _ in COLUNAS) + " |"
md = [linha_img, f"*{legenda}*", "", md_cab,
      "|" + "|".join("-" * (larguras[chave] + 2) for chave, _, _ in COLUNAS) + "|"]
md += ["| " + " | ".join(f"{l[chave]:<{larguras[chave]}}"
                         for chave, _, _ in COLUNAS) + " |" for l in linhas]

print("\n" + "─" * 30 + " para colar no REGISTRO.md " + "─" * 30)
print("\n".join(md))
print("─" * 87)
if not args.registro:
    print("A figura ainda esta em runs/. Para copia-la para a semana (e usar o caminho "
          "acima),\nrode de novo com --registro, ou:")
    print(f"  registros/_scripts/add-figura.sh -f '{saida}' -l '{legenda}'")

if args.show:
    plt.show()
