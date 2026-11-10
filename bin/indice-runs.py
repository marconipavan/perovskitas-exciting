#!/usr/bin/env python3
"""Gera um indice em Markdown de todos os calculos em runs/."""
import argparse
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import leitura

IC = Path(__file__).resolve().parent.parent
SAIDA = IC / "runs" / "INDICE.md"
DIR_SAIDA = SAIDA.parent

RE_VARREDURA = re.compile(r"^(?P<prefixo>[A-Za-z][A-Za-z0-9]*)_(?P<valor>[\d.]+)$")
RE_VARREDURA_NUM = re.compile(r"^[\d]+(?:[._][\d]+)*$")

SAIDAS_EXCITING = {"EPSILON", "LOSS", "SIGMA", "EXCITON", "EXCITON_EVEC", "BEVEC",
                   "BEVEC_KSUM", "KPATHEXC", "SCREEN", "EMATRAD", "EPS0", "GQPOINTS",
                   "TDOS", "figuras", "dados"}


def calculo(pasta, plano):
    t = leitura.tipo_de_calculo(pasta)
    if t.startswith(("BSE", "fastBSE", "GW", "TDDFT")):
        return t
    nivel = leitura.nivel_de_teoria(pasta)
    if nivel and nivel != "?":
        return nivel
    if plano.get("groundstate@do") == "skip":
        return "(reaproveita GS)"
    return t


def quando(pasta):
    for nome in ("INFOXS.OUT", "INFO.OUT", "input.xml"):
        caminho = pasta / nome
        if caminho.is_file():
            return datetime.fromtimestamp(caminho.stat().st_mtime)
    return None


def convergidos(pasta):
    md = pasta / "convergencia.md"
    if not md.is_file():
        return {}
    out = {}
    for linha in md.read_text(errors="replace").splitlines():
        campos = [c.strip() for c in linha.strip().strip("|").split("|")]
        if len(campos) >= 3 and campos[0] not in ("parametro", "") and "---" not in campos[0]:
            if campos[1] not in ("", "-"):
                out[campos[0]] = campos[1]
        if linha.startswith("## "):
            break
    return out


def calculos(bases):
    achadas = []
    for base in bases:
        if not base.is_dir():
            continue
        for xml in sorted(base.rglob("input.xml")):
            pasta = xml.parent
            if any(p in SAIDAS_EXCITING for p in pasta.relative_to(IC).parts):
                continue
            achadas.append(pasta)
    return achadas


def agrupa(pastas):
    varreduras = defaultdict(lambda: defaultdict(list))
    soltas = []
    conjunto = set(pastas)
    for p in pastas:
        m = RE_VARREDURA.match(p.name)
        mae_e_calculo = p.parent in conjunto or (p.parent / "convergencia.conf").is_file()
        if m and mae_e_calculo:
            varreduras[p.parent][m.group("prefixo")].append(p)
        elif RE_VARREDURA_NUM.match(p.name) and p.parent in conjunto:
            varreduras[p.parent]["varredura"].append(p)
        else:
            soltas.append(p)
    return [(p, varreduras.get(p, {})) for p in soltas]


CHAVES = [
    ("ngridk", ("groundstate@ngridk",)),
    ("rgkmax", ("groundstate@rgkmax",)),
    ("xc", ("groundstate@xctype",)),
    ("ngridk(xs)", ("xs@ngridk",)),
    ("gqmax", ("xs@gqmax",)),
    ("nempty(scr)", ("xs/screening@nempty",)),
    ("bse", ("xs/BSE@nstlbse", "xs/BSE@nstlxas")),
    ("bsetype", ("xs/BSE@bsetype",)),
]


def parametros(plano):
    partes = []
    for rotulo, chaves in CHAVES:
        for chave in chaves:
            if chave in plano:
                partes.append(f"`{rotulo}`={leitura.bonito(plano[chave])}")
                break
    return " · ".join(partes) or "-"


def hms(s):
    if s is None:
        return "-"
    if s < 90:
        return f"{s:.0f} s"
    if s < 5400:
        return f"{s / 60:.0f} min"
    return f"{s / 3600:.1f} h"


def linha(pasta, sweeps):
    plano = leitura.plano_input(pasta)
    try:
        import xml.etree.ElementTree as ET
        raiz = ET.parse(pasta / "input.xml").getroot()
    except Exception:
        raiz = None

    info = leitura.info(pasta) or {}
    data = quando(pasta)
    conv = convergidos(pasta)

    obs = []
    for prefixo, lista in sorted(sweeps.items()):
        alvo = conv.get(prefixo)
        marca = f" -> **{alvo}**" if alvo else ""
        obs.append(f"varredura `{prefixo}` ({len(lista)}){marca}")
    if (pasta / "convergencia.conf").is_file() and not sweeps:
        obs.append("tem `convergencia.conf`")

    if info.get("gap_ev") is not None:
        marca = "" if info["direto"] in (True, None) else "*"
        gap = f"{info['gap_ev']:.3f}{marca}"
    else:
        gap = "-"

    exc = leitura.exciton(pasta)
    if exc is not None and (i := leitura.brilhante(exc)) is not None:
        e_lig = f"**{exc['ligacao'][i]:.3f}**"
    else:
        e_lig = "-"

    rel = pasta.relative_to(IC)
    href = Path(os.path.relpath(pasta, DIR_SAIDA)).as_posix()
    return data, [
        f"[`{rel}`]({href})",
        leitura.titulo(pasta) or "?",
        leitura.fase(pasta) or "-",
        calculo(pasta, plano),
        parametros(plano),
        gap,
        e_lig,
        hms(leitura.tempo(pasta)),
        data.strftime("%d/%m/%y") if data else "-",
        "; ".join(obs) or "-",
    ]


CABECALHO = ["pasta", "material", "fase", "cálculo", "parâmetros",
             "gap (eV)", "E_b (eV)", "tempo", "data", "obs."]


def matriz(pastas):
    NIVEIS = ["PBE", "PBE+SOC", "PBE-1/2", "PBE-1/2+SOC"]
    feito = {}
    for pasta, _ in agrupa(pastas):
        f = leitura.fase(pasta)
        if not f:
            continue
        n = leitura.nivel_de_teoria(pasta)
        onde = leitura.pasta_do_resultado(pasta)
        info = leitura.info(onde) if onde else None
        if info and info.get("gap_ev") is not None:
            atual = feito.get((f, n))
            if atual is None or (info["tempo"] or 0) > (atual[1] or 0):
                feito[(f, n)] = (info["gap_ev"], info["tempo"], info["direto"])

    ordem = [nome for nome, _ in leitura.FASES]
    largura = max(len(n) for n in NIVEIS) + 2
    print()
    print("  Estado da matriz - gap (eV) por fase e nível de teoria")
    print()
    print("  " + "fase".ljust(8) + "".join(n.rjust(largura) for n in NIVEIS))
    print("  " + "-" * (8 + largura * len(NIVEIS)))
    total = prontas = 0
    for f in ordem:
        celulas = []
        for n in NIVEIS:
            total += 1
            v = feito.get((f, n))
            if v is None:
                celulas.append("-".rjust(largura))
            else:
                prontas += 1
                marca = "" if v[2] in (True, None) else "*"
                celulas.append(f"{v[0]:.3f}{marca}".rjust(largura))
        print("  " + f.ljust(8) + "".join(celulas))
    print()
    print(f"  {prontas} de {total} células · `*` = gap indireto")
    print("  Fases sem nenhuma célula não têm cálculo em runs/.")
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tutoriais", action="store_true", help="inclui tutoriais/")
    ap.add_argument("--material", default="", help="filtra pelo nome do material")
    ap.add_argument("--fase", default="", help="filtra pelo polimorfo (pm3m, r3c, delta...)")
    ap.add_argument("--matriz", action="store_true",
                    help="mostra o estado da matriz fase x nivel e sai")
    ap.add_argument("--stdout", action="store_true", help="imprime em vez de gravar")
    ap.add_argument("-o", "--out", default=str(SAIDA), help=f"default: {SAIDA}")
    args = ap.parse_args()
    global DIR_SAIDA
    DIR_SAIDA = Path(args.out).resolve().parent

    bases = [IC / "runs"] + ([IC / "tutoriais"] if args.tutoriais else [])
    pastas = calculos(bases)
    if args.matriz:
        matriz(pastas)
        return
    linhas = []
    for pasta, sweeps in agrupa(pastas):
        data, l = linha(pasta, sweeps)
        if args.material and args.material.lower() not in l[1].lower():
            continue
        if args.fase and args.fase.lower() != l[2].lower():
            continue
        linhas.append((data or datetime.min, l))

    linhas.sort(key=lambda par: par[0], reverse=True)
    linhas = [l for _, l in linhas]

    texto = [f"# Índice dos cálculos - {len(linhas)} pastas", "",
             "Gerado por `bin/indice-runs.py`. Não editar à mão: rode de novo.",
             f"Última atualização: {datetime.now():%d/%m/%Y %H:%M}.", "",
             "Varreduras de convergência (subpastas `prefixo_valor`) contam como uma linha só;",
             "o valor convergido vem do `convergencia.md` da pasta.", "",
             "| " + " | ".join(CABECALHO) + " |",
             "|" + "---|" * len(CABECALHO)]
    texto += ["| " + " | ".join(l) + " |" for l in linhas]
    saida = "\n".join(texto) + "\n"

    if args.stdout:
        print(saida)
    else:
        Path(args.out).write_text(saida)
        print(f"{len(linhas)} cálculos -> {args.out}")


if __name__ == "__main__":
    main()
