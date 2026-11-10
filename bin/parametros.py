#!/usr/bin/env python3
"""Registro dos parametros convergidos de cada sistema."""
import argparse
import configparser
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

IC = Path(__file__).resolve().parent.parent
ARQUIVO = IC / "registros" / "parametros-convergidos.conf"

CABECALHO = """\
# Parametros ja convergidos, por sistema.
#
# Mantido por bin/parametros.py - mas e um arquivo de texto: editar a mao tambem vale.
# Chaves "_alguma-coisa" sao descritivas; as outras usam o caminho do input.xml
# ("xs/screening@nempty") e podem ser aplicadas com --aplicar.
# "<chave>.origem" diz de onde veio o valor. Parametro sem origem e chute, nao
# convergencia.

"""


def carrega():
    cfg = configparser.ConfigParser()
    cfg.optionxform = str
    if ARQUIVO.is_file():
        cfg.read(ARQUIVO)
    return cfg


def grava(cfg):
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    with ARQUIVO.open("w") as fh:
        fh.write(CABECALHO)
        cfg.write(fh)


def descritivas(secao):
    return [(k, v) for k, v in secao.items() if k.startswith("_")]


def parametros(secao):
    return [(k, v) for k, v in secao.items()
            if not k.startswith("_") and not k.endswith(".origem")]


def tabela(cfg, nome):
    if nome not in cfg:
        sys.exit(f"ERRO: nao ha secao [{nome}].\n"
                 f"      Secoes: {', '.join(s for s in cfg.sections()) or '(nenhuma)'}")
    secao = cfg[nome]
    out = [f"#### Parâmetros convergidos - `{nome}`", ""]

    desc = descritivas(secao)
    if desc:
        out += ["| | |", "|---|---|"]
        out += [f"| **{k.lstrip('_')}** | {v} |" for k, v in desc]
        out.append("")

    pars = parametros(secao)
    if pars:
        out += ["| parâmetro | valor | origem |", "|---|---|---|"]
        for k, v in pars:
            out.append(f"| `{k}` | `{v}` | {secao.get(k + '.origem', '-')} |")
        out.append("")
    return "\n".join(out)


def panorama(cfg):
    if not cfg.sections():
        return "Nenhum sistema registrado ainda."
    out = ["| sistema | descrição | parâmetros | sem procedência |", "|---|---|---|---|"]
    for nome in cfg.sections():
        secao = cfg[nome]
        pars = parametros(secao)
        orfaos = [k for k, _ in pars if not secao.get(k + ".origem")]
        out.append(f"| `{nome}` | {secao.get('_material', '-')} | {len(pars)} | "
                   f"{len(orfaos) or '-'} |")
    return "\n".join(out)


def le_convergencia(src):
    conf, md = src / "convergencia.conf", src / "convergencia.md"
    if not conf.is_file():
        sys.exit(f"ERRO: nao ha convergencia.conf em {src}")
    if not md.is_file():
        sys.exit(f"ERRO: nao ha convergencia.md em {src} - a convergencia ainda nao rodou")

    cfg = configparser.ConfigParser(inline_comment_prefixes=("#", ";"), interpolation=None)
    cfg.optionxform = str
    cfg.read(conf)
    onde_de = {s: [o.strip() for o in cfg[s].get("onde", "").split(",") if o.strip()]
               for s in cfg.sections() if s != "geral"}

    achados, avisos = {}, {}
    for linha in md.read_text(errors="replace").splitlines():
        if linha.startswith("## "):
            break
        campos = [c.strip() for c in linha.strip().strip("|").split("|")]
        if len(campos) >= 3 and campos[0] in onde_de and campos[1] not in ("", "-"):
            confirmado = campos[2] not in ("", "-")
            achados[campos[0]] = (campos[1].replace("×", " "), confirmado)
    for linha in md.read_text(errors="replace").splitlines():
        m = re.match(r"- \*\*(\w+)\*\*: (.+)", linha)
        if m:
            avisos[m.group(1)] = m.group(2)

    return {nome: (onde_de[nome], valor, confirmado, avisos.get(nome))
            for nome, (valor, confirmado) in achados.items() if onde_de.get(nome)}


def importar(cfg, src, nome_secao, semana):
    achados = le_convergencia(src)
    if not achados:
        sys.exit("ERRO: o convergencia.md nao tem nenhum valor convergido.")
    if nome_secao not in cfg:
        cfg[nome_secao] = {}
    secao = cfg[nome_secao]

    rel = src.relative_to(IC) if src.is_relative_to(IC) else src
    origem = (f"semana-{semana} · " if semana else "") + f"`{rel}/convergencia.md`"

    mudou, pulados = [], []
    for nome, (ondes, valor, confirmado, aviso) in sorted(achados.items()):
        if not confirmado:
            pulados.append(f"{nome} = {valor} (nao confirmado por um vizinho)")
            continue
        for onde in ondes:
            antes = secao.get(onde)
            secao[onde] = valor
            secao[onde + ".origem"] = origem + (" ATENCAO com ressalva - ver os avisos "
                                                "do convergencia.md" if aviso else "")
            mudou.append((onde, antes, valor, aviso))
    return mudou, pulados


def aplicar(cfg, nome_secao, src, escrever):
    import convergir
    if nome_secao not in cfg:
        sys.exit(f"ERRO: nao ha secao [{nome_secao}]")
    input_xml = src / "input.xml"
    if not input_xml.is_file():
        sys.exit(f"ERRO: nao ha input.xml em {src}")

    mudancas = dict(parametros(cfg[nome_secao]))
    plano_atual = {}
    raiz = convergir.ET.parse(input_xml).getroot()

    linhas = []
    for onde, valor in mudancas.items():
        caminho, attr = convergir.separa(onde)
        elem = convergir.caminho_xml(raiz, caminho)
        atual = elem.attrib.get(attr) if elem is not None else None
        if elem is None:
            linhas.append(f"  [ausente] {onde}: o input.xml nao tem esse elemento")
        elif atual == valor:
            linhas.append(f"  [igual]   {onde} = {valor}")
        else:
            linhas.append(f"  [muda]    {onde}: {atual} -> {valor}")
            plano_atual[onde] = valor

    print(f"{src}  <-  [{nome_secao}]")
    print("\n".join(linhas))
    if not plano_atual:
        print("\nNada a mudar.")
        return
    if not escrever:
        print(f"\n{len(plano_atual)} mudanca(s). Rode de novo com --escrever para aplicar.")
        return
    feitas = convergir.escreve_valores(input_xml, plano_atual)
    print(f"\n{len(feitas)} atributo(s) escrito(s) em {input_xml}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("secao", nargs="?", help="sistema a mostrar")
    ap.add_argument("--listar", action="store_true", help="panorama de todos os sistemas")
    ap.add_argument("--secao", dest="secao_op", help="sistema alvo de --importar/--set/--aplicar")
    ap.add_argument("--importar", action="store_true",
                    help="le o convergencia.conf/.md de --src e registra os valores")
    ap.add_argument("--src", default=".", help="pasta do calculo")
    ap.add_argument("--semana", default="", help="semana que fica registrada como origem")
    ap.add_argument("--set", dest="sets", action="append", default=[],
                    metavar="ONDE=VALOR", help="define um parametro (pode repetir)")
    ap.add_argument("--origem", default="", help="procedencia dos --set")
    ap.add_argument("--aplicar", action="store_true",
                    help="escreve os parametros da secao no input.xml de --src")
    ap.add_argument("--escrever", action="store_true", help="--aplicar de verdade")
    args = ap.parse_args()

    cfg = carrega()
    alvo = args.secao_op or args.secao
    if alvo in ("-", ".", ""):
        alvo = None

    if args.importar:
        if not alvo:
            sys.exit("ERRO: --importar precisa de --secao NOME")
        mudou, pulados = importar(cfg, Path(args.src).resolve(), alvo, args.semana)
        grava(cfg)
        for onde, antes, valor, aviso in mudou:
            marca = "novo" if antes is None else ("igual" if antes == valor else f"era {antes}")
            print(f"  {onde} = {valor}   ({marca})" + (f"\n      aviso: {aviso}" if aviso else ""))
        for p in pulados:
            print(f"  [pulado] {p}")
        print(f"\n[{alvo}] atualizada em {ARQUIVO.relative_to(IC)}")
        return

    if args.sets:
        if not alvo:
            sys.exit("ERRO: --set precisa de --secao NOME")
        if alvo not in cfg:
            cfg[alvo] = {}
        for par in args.sets:
            if "=" not in par:
                sys.exit(f"ERRO: --set espera ONDE=VALOR, veio '{par}'")
            onde, valor = par.split("=", 1)
            cfg[alvo][onde.strip()] = valor.strip()
            if args.origem and not onde.startswith("_"):
                cfg[alvo][onde.strip() + ".origem"] = args.origem
        grava(cfg)
        print(f"[{alvo}]: {len(args.sets)} chave(s) gravada(s) em {ARQUIVO.relative_to(IC)}")
        return

    if args.aplicar:
        if not alvo:
            sys.exit("ERRO: --aplicar precisa de --secao NOME")
        aplicar(cfg, alvo, Path(args.src).resolve(), args.escrever)
        return

    if args.listar or not alvo:
        print(panorama(cfg))
        return

    print(tabela(cfg, alvo))


if __name__ == "__main__":
    main()
