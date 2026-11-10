#!/usr/bin/env python3
"""Monta a pasta de calculo de uma fase de perovskita."""
import argparse
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

IC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IC / "bin"))

import leitura
import parametros as par
from poscar2xml import poscar_to_dict, dict_to_xml

BOHR_A = 1.889725989
ESPECIES = IC / "exciting" / "species"
SECAO_GS = "groundstate-padrao"
FASE_ANCORA = "pm3m"

IGNORAR = {"groundstate@ngridk"}


def secao_dfthalf(material):
    cfg = par.carrega()
    nome = f"{material}-dfthalf"
    return cfg[nome] if nome in cfg else None


def raio_da_especie(elemento):
    arq = ESPECIES / f"{elemento}.xml"
    if not arq.is_file():
        return None
    try:
        mt = ET.parse(arq).getroot().find("sp/muffinTin")
    except ET.ParseError:
        return None
    return float(mt.get("radius")) if mt is not None and mt.get("radius") else None


def comprimentos(dados):
    escala = dados["scale_factor"] * BOHR_A
    return [escala * sum(x * x for x in v) ** 0.5 for v in dados["lattice_vectors"]]


def densidade_de_referencia(estruturas, ngridk_ref):
    poscar = estruturas / f"POSCAR.{FASE_ANCORA}"
    if not poscar.is_file():
        return None
    comp = comprimentos(poscar_to_dict(str(poscar)))
    n = [int(x) for x in str(ngridk_ref).split()]
    return sum(ni * L for ni, L in zip(n, comp)) / 3.0


def monta(fase, material, soc, especie_meio, rcut, ionizacao_pedida,
          malha_pedida, varrer, listar, sufixo="", sem_bandas=False):
    estruturas = IC / "estruturas" / material
    poscar = estruturas / f"POSCAR.{fase}"
    if not poscar.is_file():
        disponiveis = sorted(p.suffix[1:] for p in estruturas.glob("POSCAR.*"))
        sys.exit(f"ERRO: nao ha {poscar}\n"
                 f"      fases de {material}: {', '.join(disponiveis) or '(nenhuma)'}")

    dados = poscar_to_dict(str(poscar))
    comp = comprimentos(dados)
    especies = list(dict.fromkeys(dados["species"]))
    quantos = dict(zip(dados["species"], dados["number_of_atoms"]))

    cfg = par.carrega()
    if SECAO_GS not in cfg:
        sys.exit(f"ERRO: nao ha secao [{SECAO_GS}] em {par.ARQUIVO}")
    attrs = {k: v for k, v in par.parametros(cfg[SECAO_GS]) if k not in IGNORAR}
    ngridk_ref = dict(par.parametros(cfg[SECAO_GS])).get("groundstate@ngridk", "8 8 8")

    aviso_malha = ""
    if malha_pedida:
        malha = [int(x) for x in malha_pedida.split()]
        origem_malha = "pedida na linha de comando"
    else:
        d0 = densidade_de_referencia(estruturas, ngridk_ref)
        if d0 is None:
            malha = [int(x) for x in ngridk_ref.split()]
            origem_malha = f"ngridk de referencia, literal (nao achei a fase {FASE_ANCORA})"
            aviso_malha = "  AVISO: sem a fase ancora, a malha nao foi transportada por densidade"
        else:
            malha = [max(1, round(d0 / L)) for L in comp]
            origem_malha = (f"densidade {d0:.1f} bohr, do {ngridk_ref.replace(' ', '×')} "
                            f"da {FASE_ANCORA}")
    attrs["groundstate@ngridk"] = " ".join(map(str, malha))

    dfthalf = None
    ionizacao = conta_ion = None
    if especie_meio:
        if especie_meio not in especies:
            sys.exit(f"ERRO: {material} {fase} nao tem a especie {especie_meio}.\n"
                     f"      especies: {', '.join(especies)}")
        sec = secao_dfthalf(material)
        if sec is None:
            sys.exit(f"ERRO: nao ha secao [{material}-dfthalf] em {par.ARQUIVO}.\n"
                     f"      Ela e quem guarda a ionizacao, o ampl e o exponent.")
        conf = dict(par.parametros(sec))
        formulas = _formulas(dados)
        por_formula = quantos[especie_meio] // formulas
        ionizacao = ionizacao_pedida or conf.get("shell@ionization")
        if ionizacao is None:
            sys.exit(f"ERRO: sem ionizacao. Passe --ionizacao, ou registre "
                     f"shell@ionization em\n      [{material}-dfthalf] de {par.ARQUIVO}.")
        conta_ion = (f"{quantos[especie_meio]} {especie_meio} na cela "
                     f"({por_formula} por formula), {ionizacao} e- em cada")
        cut = rcut or conf.get("dfthalfparam@cut")
        if not cut:
            sys.exit(f"ERRO: sem r_cut. Passe --rcut, ou registre dfthalfparam@cut em\n"
                     f"      [{material}-dfthalf] de {par.ARQUIVO}.")
        dfthalf = {especie_meio: {"cut": str(cut), "ionization": str(ionizacao),
                                  "ampl": conf.get("dfthalfparam@ampl", "1"),
                                  "exponent": conf.get("dfthalfparam@exponent", "8"),
                                  "number": conf.get("shell@number", "0")}}

    estrutura = dict_to_xml(dados, None, dfthalf)

    nivel = ("pbe12" if especie_meio else "pbe") + ("-soc" if soc else "")
    rotulo = ("PBE-1/2" if especie_meio else "PBE") + ("+SOC" if soc else "")
    nome = f"{material}-{fase}-{nivel}{sufixo}"
    destino = leitura.acha_run(nome) or leitura.pasta_nova(nome)

    formula = "".join(f"{e}{quantos[e]}" for e in especies)
    print(f"  material    : {material}   fase {fase}   "
          f"({formula}, {sum(dados['number_of_atoms'])} atomos)")
    print(f"  |a_i| (bohr): {', '.join(f'{x:.2f}' for x in comp)}")
    print(f"  malha       : {'×'.join(map(str, malha))}   ({origem_malha})")
    print(f"  nivel       : {rotulo}")
    raios = [(e, raio_da_especie(e)) for e in especies]
    print("  raios MT    : " + " · ".join(
        f"{e} {r:.2f}" if r else f"{e} ?" for e, r in raios)
        + "   (do arquivo de especie; nenhum rmt escrito no input)")
    menor = min((r for _, r in raios if r), default=None)
    if menor:
        print(f"                o rgkmax={attrs.get('groundstate@rgkmax', '?')} "
              f"esta medido contra o menor, {menor:.2f} bohr")
    if dfthalf:
        d = dfthalf[especie_meio]
        print(f"  DFT-1/2     : {especie_meio}   r_cut = {d['cut']} bohr   "
              f"ionizacao = {d['ionization']}   (camada {d['number']}, "
              f"A={d['ampl']}, n={d['exponent']})")
        print(f"                {conta_ion}")
    vetores = [[dados["scale_factor"] * c for c in v]
               for v in dados["lattice_vectors"]]
    bloco_props, desc_caminho = (("", None) if sem_bandas
                                 else leitura.caminho_de_bandas(vetores))
    if desc_caminho:
        print(f"  bandas + DOS: {desc_caminho}")
    elif not sem_bandas:
        print("  bandas      : NAO (o ASE nao detectou a rede; instale ase ou use --malha)")
    print(f"  destino     : {destino.relative_to(IC)}")
    if aviso_malha:
        print(aviso_malha)
    if listar:
        return

    destino.mkdir(parents=True, exist_ok=True)

    linhas_gs = []
    for chave in sorted(attrs):
        elem, atrib = chave.split("@", 1)
        if elem == "groundstate":
            linhas_gs.append(f'      {atrib}="{attrs[chave]}"')
    gs = "   <groundstate\n" + "\n".join(linhas_gs) + ">\n"
    if soc:
        gs += '      <spin spinorb="true"/>\n'
    if dfthalf:
        gs += '      <dfthalf printVSfile="false"/>\n'
    gs += "   </groundstate>\n"

    titulo = f"{material} {fase} {rotulo}"
    xml = (f"<input>\n\n   <title>{titulo}</title>\n\n{estrutura}\n{gs}\n"
           f"{bloco_props}</input>\n")
    (destino / "input.xml").write_text(xml, encoding="ascii")

    for e in especies:
        origem = ESPECIES / f"{e}.xml"
        if not origem.is_file():
            sys.exit(f"ERRO: nao ha o arquivo de especie {origem}")
        shutil.copy(origem, destino / f"{e}.xml")

    if varrer:
        r = subprocess.run([sys.executable, str(IC / "bin" / "convergir.py"),
                            "--src", str(destino), "--criar-plano"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("  AVISO: --criar-plano falhou:", (r.stderr or r.stdout).strip()[:200])
        else:
            tiradas = poda_plano(destino / "convergencia.conf")
            print(f"  plano       : convergencia.conf escrito")
            if tiradas:
                print(f"                etapas retiradas: {', '.join(tiradas)} - o "
                      f"groundstate e padrao da equipe e nao se converge")

    print(f"  -> {destino.relative_to(IC)} montada ({1 + len(especies)} arquivos)")


ETAPAS_DE_GROUNDSTATE = ("rgkmax", "ngridkgs")


def poda_plano(conf):
    if not conf.is_file():
        return []
    linhas = conf.read_text().split("\n")
    saida, tiradas, pulando = [], [], False
    for linha in linhas:
        if linha.startswith("["):
            nome = linha.strip()[1:-1]
            pulando = nome in ETAPAS_DE_GROUNDSTATE
            if pulando:
                tiradas.append(nome)
                continue
        if pulando:
            if linha.strip() and not linha.startswith(("#", " ")):
                continue
            if not linha.strip():
                pulando = False
            continue
        if linha.startswith("malha_de_teste"):
            saida.append("malha_de_teste =             # vazio: o r_cut e determinado na "
                         "malha de producao,")
            saida.append("                             # que e a do groundstate padrao")
            continue
        saida.append(linha)
    conf.write_text("\n".join(saida))
    return tiradas


def _formulas(dados):
    from math import gcd
    from functools import reduce
    return reduce(gcd, dados["number_of_atoms"])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fase", nargs="?", help="pm3m, p4mbm, i4mcm, gamma, delta, r3c, r3m")
    ap.add_argument("--todas", action="store_true", help="monta todas as fases do material")
    ap.add_argument("-m", "--material", default="CsSnBr3")
    ap.add_argument("--soc", action="store_true", help="acrescenta <spin spinorb='true'/>")
    ap.add_argument("--dfthalf", metavar="ESPECIE",
                    help="especie que recebe a correcao DFT-1/2 (ex.: Br)")
    ap.add_argument("--rcut", metavar="BOHR",
                    help="r_cut inicial; sem isso, o registrado no .conf")
    ap.add_argument("--ionizacao", metavar="CARGA",
                    help="sobrescreve a ionizacao por atomo (ex.: 0.5); sem isso, o .conf")
    ap.add_argument("--sufixo", default="",
                    help="acrescenta ao nome da pasta (ex.: -ion05), para nao colidir")
    ap.add_argument("--malha", default="", metavar='"n n n"',
                    help="malha explicita; sem isso, a densidade da fase ancora")
    ap.add_argument("--varrer", dest="varrer", action="store_true",
                    help="escreve tambem o convergencia.conf")
    ap.add_argument("--sem-bandas", action="store_true",
                    help="nao escreve <properties>; o calculo sai sem banda nem DOS")
    ap.add_argument("--listar", action="store_true", help="so mostra, nao escreve")
    args = ap.parse_args()

    if args.todas:
        estruturas = IC / "estruturas" / args.material
        fases = sorted(p.suffix[1:] for p in estruturas.glob("POSCAR.*"))
        if not fases:
            sys.exit(f"ERRO: nenhum POSCAR em {estruturas}")
    elif args.fase:
        fases = [args.fase]
    else:
        ap.error("informe uma fase, ou --todas")

    for i, fase in enumerate(fases):
        if i:
            print()
        monta(fase, args.material, args.soc, args.dfthalf, args.rcut,
              args.ionizacao, args.malha, args.varrer, args.listar, args.sufixo,
              args.sem_bandas)


if __name__ == "__main__":
    main()
