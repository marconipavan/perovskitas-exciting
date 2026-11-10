#!/usr/bin/env python3
"""Calcula alpha, eps_inf e tempos de vida a partir de um calculo BSE."""
import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import leitura

IC = Path(__file__).resolve().parent.parent


def confere(pasta, exc):
    c = leitura.curva(pasta, col=leitura.COL_IM)
    if c is None or exc is None:
        print("  [!] falta EPSILON ou EXCITON - nao da para conferir.")
        return
    x, im = c
    rec = leitura.reconstroi_epsilon(exc, x)
    if rec is None:
        print("  [!] o cabecalho do EPSILON nao traz o alargamento; sem conferencia.")
        return
    escala = max(float(np.max(im)), 1e-30)
    erro = float(np.max(np.abs(rec.imag - im))) / escala
    print(f"  conferencia EXCITON x EPSILON : erro relativo maximo {erro:.4%}")
    if erro < 0.01:
        print("  [ok] os dois arquivos sao consistentes.")
    else:
        print("  [!] DIVERGEM. Provaveis causas: os arquivos vieram de rodadas")
        print("      diferentes, ou <storeexcitons> guardou menos solucoes do que o")
        print("      espectro usa. Confira antes de usar os numeros.")


def tabela(pasta, exc, quantos):
    d2 = leitura.dipolo2(exc)
    A, tau = leitura.taxa_einstein(exc)
    limiar = float(np.max(exc["osc"])) * 1e-3
    idx = [i for i in range(len(exc["nr"])) if exc["osc"][i] > limiar][:quantos]
    if not idx:
        print("  nenhum exciton com forca de oscilador acima do limiar.")
        return
    print(f"  {'#':>6} {'E (eV)':>10} {'E_b (eV)':>10} {'|Osc|':>12} "
          f"{'|d|^2 (u.a.)':>13} {'tau (ns)':>12}")
    print(f"  {'-'*6} {'-'*10} {'-'*10} {'-'*12} {'-'*13} {'-'*12}")
    for i in idx:
        t = tau[i] * 1e9 if np.isfinite(tau[i]) else float("inf")
        print(f"  {exc['nr'][i]:>6} {exc['energia'][i]:>10.4f} "
              f"{exc['ligacao'][i]:>10.4f} {exc['osc'][i]:>12.4e} "
              f"{d2[i]:>13.4f} {t:>12.3f}")
    escuros = idx[0]
    if escuros:
        print(f"  ({escuros} estado(s) abaixo do primeiro brilhante - escuros)")


def figura(pasta, args):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    c_im = leitura.curva(pasta, col=leitura.COL_IM)
    a = leitura.absorcao(pasta)
    if c_im is None or a is None:
        print("  [!] sem espectro; figura nao gerada.")
        return None
    x, im = c_im
    _, alpha = a
    titulo = leitura.titulo(pasta) or pasta.name

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 7), sharex=True)
    ax1.plot(x, im, color="steelblue")
    ax1.set_ylabel(r"Im $\varepsilon_M$")
    ax1.grid(True, alpha=0.3)
    eps = leitura.eps_estatico(pasta)
    if eps is not None:
        ax1.axhline(0, lw=0.5, color="0.7")
        ax1.set_title(f"{titulo}   -   " + rf"$\varepsilon_\infty$ = {eps:.3f}")
    else:
        ax1.set_title(titulo)

    ax2.plot(x, alpha, color="indianred")
    ax2.set_ylabel(r"$\alpha$ [cm$^{-1}$]")
    ax2.set_xlabel("energia [eV]")
    ax2.grid(True, alpha=0.3)
    if args.xlim:
        ax2.set_xlim(*args.xlim)
    fig.tight_layout()

    png = pasta / f"otica-{pasta.name}.png"
    fig.savefig(png, dpi=150)
    plt.close(fig)
    print(f"  figura: {png}")
    legenda = f"Im ε_M e coeficiente de absorção α - {titulo}"
    if args.registro:
        leitura.manda_para_registro(png, legenda)
    print()
    print("─" * 30 + " para colar no REGISTRO.md " + "─" * 30)
    print(f"![{legenda}](figuras/{png.name})")
    print(f"*{legenda}*")
    print("─" * 87)
    return png


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-s", "--src", default=".", help="pasta do calculo (default: atual)")
    ap.add_argument("-n", "--quantos", type=int, default=5,
                    help="quantos excitons brilhantes listar (default: 5)")
    ap.add_argument("-x", "--xlim", nargs=2, type=float, metavar=("MIN", "MAX"))
    ap.add_argument("--figura", action="store_true", help="gera a figura Im eps + alpha")
    ap.add_argument("--registro", action="store_true",
                    help="copia a figura para figuras/ da semana corrente")
    ap.add_argument("--conferir", action="store_true",
                    help="confere o EXCITON contra o EPSILON")
    args = ap.parse_args()

    pasta = Path(args.src).resolve()
    if not pasta.is_dir():
        sys.exit(f"ERRO: pasta nao existe: {pasta}")

    exc = leitura.exciton(pasta)
    if exc is None:
        sys.exit(f"ERRO: nao ha EXCITON/ em {pasta}\n"
                 f"      Esta pasta nao tem um calculo BSE terminado. As grandezas\n"
                 f"      opticas derivadas precisam das autoenergias e das forcas de\n"
                 f"      oscilador, que so saem da tarefa 'bse'.")

    print()
    print(f"  {pasta}")
    print(f"  {leitura.titulo(pasta) or '?'}   ·   {leitura.tipo_de_calculo(pasta)}")
    eps = leitura.eps_estatico(pasta)
    if eps is not None:
        print(f"  eps_inf (do BSE) : {eps:.4f}")
    dt = leitura.dieltens(pasta)
    if dt:
        print(f"  DIELTENS (RPA)   : {dt[0]:.4f}  {dt[1]:.4f}  {dt[2]:.4f}")
    a = leitura.absorcao(pasta)
    if a is not None:
        j = int(np.argmax(a[1]))
        print(f"  pico de alpha    : {a[1][j]:.3e} cm^-1 em {a[0][j]:.2f} eV")
    print()

    if args.conferir:
        confere(pasta, exc)
        print()

    tabela(pasta, exc, args.quantos)
    print()
    print("  tau: coeficiente A de Einstein de um emissor isolado. Serve de ordem de")
    print("  grandeza e de comparacao RELATIVA entre fases. Para o valor absoluto,")
    print("  falta a media termica sobre o cone de luz (Spataru 2005, Palummo 2015)")
    print("  - confirmar a formula antes de levar ao paper.")

    if args.figura:
        print()
        figura(pasta, args)
    print()


if __name__ == "__main__":
    main()
