#!/usr/bin/env python3
"""Tabela com os resultados de BSE, uma linha por calculo."""
import argparse
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import leitura

IC = Path(__file__).resolve().parent.parent
SAIDA = IC / "registros" / "TABELA-BSE.md"
INICIO = "<!-- gerado por bin/tabela-bse.py - nao editar entre os marcadores -->"
FIM = "<!-- fim do trecho gerado -->"

CHAVES = [("malha k/q", "xs@ngridk"), ("gqmax", "xs@gqmax"),
          ("nempty(scr)", "xs/screening@nempty"), ("nstlbse", "xs/BSE@nstlbse"),
          ("bsetype", "xs/BSE@bsetype")]


RE_VARREDURA = re.compile(r"^[A-Za-z][A-Za-z0-9]*_[\d.]+$")


def e_varredura(pasta):
    return bool(RE_VARREDURA.match(pasta.name)) and (pasta.parent / "input.xml").is_file()


def calculos_bse(base, com_varreduras=False):
    vistas = {}
    for exciton_dir in sorted(base.rglob("EXCITON")):
        pasta = exciton_dir.parent
        if not com_varreduras and e_varredura(pasta):
            continue
        if leitura.arquivo_exciton(pasta) is not None:
            vistas[pasta] = True
    return list(vistas)


def linha(pasta):
    exc = leitura.exciton(pasta)
    i = leitura.brilhante(exc)
    if i is None:
        return None
    _, tau = leitura.taxa_einstein(exc)
    eps = leitura.eps_estatico(pasta)
    a = leitura.absorcao(pasta)
    plano = leitura.plano_input(pasta)

    if a is not None:
        j = int(np.argmax(a[1]))
        pico = f"{a[1][j]:.2e} @ {a[0][j]:.1f}"
    else:
        pico = "-"
    t = tau[i] * 1e9
    rel = Path("..") / pasta.relative_to(IC)
    params = " · ".join(f"`{r}`={leitura.bonito(plano[c])}"
                        for r, c in CHAVES if c in plano) or "-"
    return [
        leitura.titulo(pasta) or "?",
        leitura.fase(pasta) or "-",
        f"[`{pasta.name}`]({rel.as_posix()})",
        f"{eps:.3f}" if eps is not None else "-",
        f"**{exc['energia'][i]:.3f}**",
        f"**{exc['ligacao'][i]:.3f}**",
        f"{exc['osc'][i]:.3e}",
        f"{t:.2f}" if np.isfinite(t) else "∞",
        pico,
        params,
    ]


CABECALHO = ["material", "fase", "pasta", "ε∞", "E₁ (eV)", "E_b (eV)",
             "\\|Osc\\|", "τ (ns)", "α pico (cm⁻¹ @ eV)", "parâmetros"]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--material", default="", help="filtra pelo nome do material")
    ap.add_argument("--varreduras", action="store_true",
                    help="inclui as subpastas de convergencia (nempty_25, malhaqk_333...)")
    ap.add_argument("--stdout", action="store_true", help="imprime em vez de gravar")
    ap.add_argument("-o", "--out", default=str(SAIDA), help=f"default: {SAIDA}")
    args = ap.parse_args()

    linhas = []
    for pasta in calculos_bse(IC / "runs", args.varreduras):
        l = linha(pasta)
        if l is None:
            continue
        if args.material and args.material.lower() not in l[0].lower():
            continue
        linhas.append(l)
    linhas.sort(key=lambda l: (l[0], l[1]))

    from datetime import datetime
    corpo = [INICIO, "",
             f"*{len(linhas)} cálculo(s) · gerado em {datetime.now():%d/%m/%Y %H:%M} "
             f"por `bin/tabela-bse.py`.*", "",
             "| " + " | ".join(CABECALHO) + " |",
             "|" + "---|" * len(CABECALHO)]
    corpo += ["| " + " | ".join(l) + " |" for l in linhas]
    corpo += ["",
              "**E_b negativa -> éxciton ligado.** E₁ e |Osc| são da primeira excitação",
              "**brilhante** (as escuras acima do limiar são puladas). ε∞ é Re ε_M na",
              "menor frequência do próprio espectro BSE, não o `DIELTENS.OUT` (que é RPA).",
              "",
              "ATENCAO **τ é uma ordem de grandeza**, não um valor de paper: é o coeficiente A",
              "de Einstein de um emissor isolado. Falta a média térmica sobre o cone de luz",
              "(Spataru 2005, Palummo 2015). Serve para comparar fases entre si.",
              "", FIM]
    gerado = "\n".join(corpo)

    if args.stdout:
        print(gerado)
        return

    destino = Path(args.out)
    if destino.is_file():
        texto = destino.read_text()
        if INICIO in texto and FIM in texto:
            antes = texto.split(INICIO)[0]
            depois = texto.split(FIM, 1)[1]
            novo = antes + gerado + depois
        else:
            novo = texto.rstrip() + "\n\n" + gerado + "\n"
    else:
        novo = ("# Tabela de resultados do BSE\n\n"
                "O entregável do eixo excitônico: por fase, a função dielétrica, a energia\n"
                "de ligação do éxciton, a força de oscilador e as grandezas derivadas.\n"
                "A [TABELA-GAPS.md](TABELA-GAPS.md) cobre o eixo do gap; esta cobre o resto.\n\n"
                "Escreva livremente **fora** dos marcadores - só o trecho entre eles é\n"
                "regerado. As etapas estão catalogadas em [ETAPAS.md](ETAPAS.md).\n\n"
                + gerado + "\n")
    destino.write_text(novo)
    print(f"{len(linhas)} cálculos de BSE -> {destino}")


if __name__ == "__main__":
    main()
