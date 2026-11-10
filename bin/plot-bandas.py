#!/usr/bin/env python3
"""Plota a estrutura de bandas e a densidade de estados."""
import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import leitura

HARTREE_EV = leitura.HARTREE_EV
MARGEM_EV = 6.0


def le_bandas(pasta):
    arq = Path(pasta) / "BAND.OUT"
    if not arq.is_file():
        return []
    bandas, x, y = [], [], []
    for linha in arq.read_text(errors="replace").splitlines():
        if not linha.strip():
            if x:
                bandas.append((np.array(x), np.array(y)))
                x, y = [], []
            continue
        try:
            a, b = linha.split()[:2]
            x.append(float(a)); y.append(float(b))
        except ValueError:
            continue
    if x:
        bandas.append((np.array(x), np.array(y)))
    return [corta_nos_saltos(bx, by) for bx, by in bandas]


def corta_nos_saltos(x, y):
    if len(x) < 2:
        return x, y
    saltos = np.flatnonzero(np.diff(x) <= 0)
    if not len(saltos):
        return x, y
    x = np.insert(x.astype(float), saltos + 1, np.nan)
    y = np.insert(y.astype(float), saltos + 1, np.nan)
    return x, y


def le_verticais(pasta):
    arq = Path(pasta) / "BANDLINES.OUT"
    if not arq.is_file():
        return []
    xs, bloco = [], None
    for linha in arq.read_text(errors="replace").splitlines():
        p = linha.split()
        if len(p) >= 2:
            try:
                if bloco is None:
                    bloco = float(p[0])
            except ValueError:
                pass
        elif bloco is not None:
            xs.append(bloco); bloco = None
    if bloco is not None:
        xs.append(bloco)
    return xs


def le_rotulos(pasta):
    arq = Path(pasta) / "input.xml"
    if not arq.is_file():
        return []
    try:
        raiz = ET.parse(arq).getroot()
    except ET.ParseError:
        return []
    pontos = raiz.findall("properties/bandstructure/plot1d/path/point")
    bonito = {"GAMMA": "Γ", "Gamma": "Γ"}
    return [bonito.get(p.get("label", ""), p.get("label", "")) for p in pontos]


def marcas_do_eixo(pasta):
    vert, rot = le_verticais(pasta), le_rotulos(pasta)
    if not vert or len(vert) != len(rot):
        return vert, [""] * len(vert)
    marcas, nomes = [], []
    for x, nome in zip(vert, rot):
        if marcas and abs(x - marcas[-1]) < 1e-9:
            if nomes[-1] != nome:
                nomes[-1] += f"|{nome}"
        else:
            marcas.append(x); nomes.append(nome)
    return marcas, nomes


def le_dos(pasta):
    arq = Path(pasta) / "TDOS.OUT"
    if not arq.is_file():
        return None
    try:
        d = np.loadtxt(arq)
    except (OSError, ValueError):
        return None
    if d.ndim != 2 or d.shape[1] < 2:
        return None
    return d[:, 0] * HARTREE_EV, d[:, 1]


def plota(pasta, args):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pasta = Path(pasta)
    bandas = le_bandas(pasta)
    dos = le_dos(pasta)
    if not bandas and dos is None:
        return None, "nem BAND.OUT nem TDOS.OUT nesta pasta"

    info = leitura.info(pasta) or {}
    if not info.get("gap_ev") and pasta.name.endswith("-bandas"):
        pai = pasta.parent / pasta.name[:-len("-bandas")]
        if pai.is_dir():
            info = leitura.info(pai) or info
    titulo = leitura.titulo(pasta) or pasta.name
    nivel = leitura.nivel_de_teoria(pasta)

    so_dos = args.so_dos or not bandas
    com_dos = dos is not None and not args.so_bandas
    if so_dos:
        fig, axd = plt.subplots(figsize=(6, 5))
        axb = None
    elif com_dos:
        fig, (axb, axd) = plt.subplots(
            1, 2, figsize=(10, 5.5), sharey=True,
            gridspec_kw={"width_ratios": [3, 1], "wspace": 0.05})
    else:
        fig, axb = plt.subplots(figsize=(7.5, 5.5))
        axd = None

    if axb is not None:
        for x, y in bandas:
            axb.plot(x, y * HARTREE_EV, lw=1.0, color="steelblue")
        for v in sorted(set(round(v, 9) for v in le_verticais(pasta))):
            axb.axvline(v, color="0.6", lw=0.7)
        axb.axhline(0, color="0.4", lw=0.8, ls="--")

        marcas, rotulos = marcas_do_eixo(pasta)
        axb.set_xticks(marcas)
        axb.set_xticklabels(rotulos)
        finitos = bandas[0][0][np.isfinite(bandas[0][0])]
        axb.set_xlim(finitos[0], finitos[-1])
        axb.set_ylabel("E − E$_F$  [eV]")
        axb.grid(axis="y", alpha=0.2)

        todos = np.concatenate([y for _, y in bandas])
        todos = todos[np.isfinite(todos)]
        ocupados, vazios = todos[todos <= 0], todos[todos > 0]
        if len(ocupados) and len(vazios):
            vbm = ocupados.max() * HARTREE_EV
            cbm = vazios.min() * HARTREE_EV
            janela_padrao = (vbm - MARGEM_EV, cbm + MARGEM_EV)
            gap_bandas = cbm - vbm
            gap_info = info.get("gap_ev")
            concordam = gap_info is not None and abs(gap_bandas - gap_info) < 0.01
            if gap_bandas > 1e-3 and concordam:
                direto = "direto" if info.get("direto") else "indireto"
                axb.axhspan(vbm, cbm, color="orange", alpha=0.10)
                axb.text(0.985, (vbm + cbm) / 2,
                         f"gap {gap_info:.3f} eV\n({direto})",
                         transform=axb.get_yaxis_transform(), ha="right", va="center",
                         fontsize=8, color="darkorange")
            elif gap_bandas > 1e-3 and gap_info is not None:
                print(f"  AVISO: o gap das bandas ({gap_bandas:.4f} eV) nao bate com o "
                      f"do INFO.OUT ({gap_info:.4f} eV); faixa nao desenhada")

    if axd is not None and dos is not None:
        e, d = dos
        axd.plot(d, e, lw=1.0, color="indianred")
        axd.fill_betweenx(e, 0, d, color="indianred", alpha=0.18)
        axd.axhline(0, color="0.4", lw=0.8, ls="--")
        axd.set_xlabel("DOS [estados/Ha/cela]")
        axd.set_xlim(left=0)
        axd.grid(alpha=0.2)
        if axb is None:
            axd.set_ylabel("E − E$_F$  [eV]")

    alvo = axb if axb is not None else axd
    if args.elim:
        alvo.set_ylim(*args.elim)
    elif janela_padrao and not args.tudo:
        alvo.set_ylim(*janela_padrao)

    if axd is not None and dos is not None:
        e, d = dos
        lo, hi = alvo.get_ylim()
        dentro = d[(e >= lo) & (e <= hi)]
        if len(dentro) and dentro.max() > 0:
            axd.set_xlim(0, dentro.max() * 1.08)
    (axb or axd).set_title(f"{titulo} - {nivel}", loc="left", fontsize=11)
    fig.tight_layout()

    nome = "dos" if so_dos else ("bandas-dos" if com_dos else "bandas")
    png = pasta / f"{nome}-{pasta.name}.png"
    fig.savefig(png, dpi=150)
    plt.close(fig)
    return png, None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-s", "--src", default=".", help="pasta do calculo")
    ap.add_argument("-e", "--elim", nargs=2, type=float, metavar=("MIN", "MAX"),
                    help="janela de energia em eV, relativa a E_F")
    ap.add_argument("--tudo", action="store_true",
                    help="nao recorta o eixo de energia (mostra ate os estados de caroco)")
    ap.add_argument("--so-bandas", action="store_true")
    ap.add_argument("--so-dos", action="store_true")
    ap.add_argument("--registro", action="store_true",
                    help="copia a figura para figuras/ da semana")
    args = ap.parse_args()

    pasta = Path(args.src).resolve()
    if not pasta.is_dir():
        sys.exit(f"ERRO: pasta nao existe: {pasta}")
    png, erro = plota(pasta, args)
    if erro:
        sys.exit(f"ERRO: {erro}")
    print(f"  figura: {png}")

    titulo = leitura.titulo(pasta) or pasta.name
    legenda = (f"Densidade de estados - {titulo}" if "dos-" in png.name
               else f"Estrutura de bandas - {titulo}")
    if args.registro:
        leitura.manda_para_registro(png, legenda)
    print()
    print("─" * 30 + " para colar no REGISTRO.md " + "─" * 30)
    print(f"![{legenda}](figuras/{png.name})")
    print(f"*{legenda}*")
    print("─" * 87)


if __name__ == "__main__":
    main()
