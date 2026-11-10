#!/usr/bin/env python3
"""Roda uma sequencia de testes de convergencia descrita num convergencia.conf."""
import argparse
import configparser
import os
import re
import signal
import subprocess
import sys
import textwrap
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

import leitura

IC = Path(__file__).resolve().parent.parent
RUN_TASK = IC / "bin" / "run-exciting-task.sh"
PLOT = IC / "bin" / "plot-convergencia.py"

PLANO_PADRAO = "convergencia.conf"
BACKUP = "input.xml.antes-da-convergencia"
RESUMO = "convergencia.md"

CRITERIOS = ("pico", "altura", "espectro", "gap", "energia")
ESPECTRAIS = ("pico", "altura", "espectro")
DE_INFO = ("gap", "energia")
PARADAS = ("primeiro", "todos", "maximo")
REFERENCIAS = ("vizinho", "melhor")

HARTREE_EV = 27.211386245988


def unidade(criterio):
    if criterio == "energia":
        return "meV/atomo"
    return "meV" if criterio in ("pico", "gap") else "%"


def caminho_xml(raiz, caminho):
    elem = raiz
    for tag in caminho.split("/"):
        achado = elem.find(tag)
        if achado is None:
            return None
        elem = achado
    return elem


def separa(onde):
    if "@" not in onde:
        raise ValueError(f"'{onde}' nao tem '@': escreva elemento@atributo "
                         f"(ex.: xs/screening@nempty)")
    caminho, attr = onde.rsplit("@", 1)
    return caminho, attr


def tags_de_abertura(texto, tag):
    return [(m.start(), m.end())
            for m in re.finditer(rf"<{re.escape(tag)}(?=[\s/>])[^>]*>", texto)]


def atributos_da_tag(trecho):
    return dict(re.findall(r'([\w:.-]+)\s*=\s*"([^"]*)"', trecho))


def acha_tag(texto, elem, tag):
    candidatos = tags_de_abertura(texto, tag)
    if not candidatos:
        return None
    if len(candidatos) == 1:
        return candidatos[0]
    esperado = {k: " ".join(v.split()) for k, v in elem.attrib.items()}
    casam = [c for c in candidatos
             if {k: " ".join(v.split())
                 for k, v in atributos_da_tag(texto[c[0]:c[1]]).items()} == esperado]
    if len(casam) == 1:
        return casam[0]
    return None


def poe_attr(trecho, attr, valor):
    m = re.search(rf'({re.escape(attr)}\s*=\s*")([^"]*)(")', trecho)
    if m:
        return trecho[:m.start(2)] + valor + trecho[m.end(2):]
    fecho = re.search(r"(\s*)(/?>)$", trecho)
    corpo, espaco, fim = trecho[:fecho.start()], fecho.group(1), fecho.group(2)
    ident = re.findall(r"\n([ \t]*)\S", corpo)
    cola = f"\n{ident[-1]}" if ident else " "
    return f'{corpo}{cola}{attr}="{valor}"{espaco}{fim}'


def escreve_valores(input_xml, mudancas):
    texto = input_xml.read_text()
    raiz = ET.fromstring(texto)
    feitas = []
    for onde, valor in mudancas.items():
        caminho, attr = separa(onde)
        elem = caminho_xml(raiz, caminho)
        if elem is None:
            raise KeyError(f"o input.xml nao tem o elemento <{caminho.split('/')[-1]}> "
                           f"de '{onde}'")
        pos = acha_tag(texto, elem, caminho.split("/")[-1])
        if pos is None:
            raise KeyError(f"nao consegui localizar a tag de '{onde}' no texto do "
                           f"input.xml (ha mais de uma <{caminho.split('/')[-1]}> igual?)")
        i, f = pos
        antes = elem.attrib.get(attr)
        novo = poe_attr(texto[i:f], attr, valor)
        texto = texto[:i] + novo + texto[f:]
        raiz = ET.fromstring(texto)
        if antes != valor:
            feitas.append((onde, antes, valor))
    input_xml.write_text(texto)
    return feitas


class Etapa:
    def __init__(self, nome, onde, valores, criterio, tols, parar, janela_pico,
                 referencia="vizinho"):
        self.nome = nome
        self.onde = onde
        self.valores = valores
        self.criterio = criterio
        self.tols = tols
        self.parar = parar
        self.referencia = referencia
        self.janela_pico = janela_pico
        self.medidas = []
        self.escolhido = None
        self.confirmador = None
        self.delta = None
        self.aviso = None

    def pasta(self, valor):
        return f"{self.nome}_{sufixo(valor)}"

    @property
    def modo(self):
        return "info" if any(c in DE_INFO for c in self.criterio) else "espectro"

    @property
    def contra_o_melhor(self):
        return self.referencia == "melhor" and not self.maximiza

    @property
    def maximiza(self):
        return self.parar == "maximo"

    @property
    def mexe_na_malha(self):
        return any(o.endswith("@ngridk") or o.endswith("@ngridq") for o in self.onde)


def sufixo(valor):
    return re.sub(r"[^0-9A-Za-z]", "", valor)


def lista(valor):
    return [p.strip() for p in valor.split(",") if p.strip()]


def le_plano(arquivo):
    cfg = configparser.ConfigParser(inline_comment_prefixes=("#", ";"),
                                    interpolation=None)
    cfg.optionxform = str
    with arquivo.open() as fh:
        cfg.read_file(fh)

    g = cfg["geral"] if cfg.has_section("geral") else {}

    def geral(chave, padrao=None):
        v = g.get(chave, padrao)
        return v.strip() if isinstance(v, str) else v

    criterio_g = geral("criterio", "pico")
    tols_g = {"pico": float(geral("tol", 20)),
              "altura": float(geral("tol_altura", 2)),
              "espectro": float(geral("tol_espectro", 2)),
              "gap": float(geral("tol_gap", 10)),
              "energia": float(geral("tol_energia", 1))}
    parar_g = geral("parar", "primeiro")
    ref_g = geral("referencia", "vizinho")
    janela_pico_g = float(geral("janela_pico", 1.0))

    def criterios(txt):
        partes = [c.strip() for c in re.split(r"[+,]", txt) if c.strip()]
        ruins = [c for c in partes if c not in CRITERIOS]
        if ruins:
            sys.exit(f"ERRO: criterio desconhecido: {', '.join(ruins)}\n"
                     f"       validos: {' | '.join(CRITERIOS)} (ou 'pico+altura')")
        info = [c for c in partes if c in DE_INFO]
        espectrais = [c for c in partes if c in ESPECTRAIS]
        if info and espectrais:
            sys.exit(f"ERRO: {'/'.join(info)} sai do INFO.OUT e "
                     f"{'/'.join(espectrais)} sai do espectro:\n"
                     f"       nao da para combinar numa etapa so.")
        return partes

    etapas = []
    for nome in cfg.sections():
        if nome == "geral":
            continue
        sec = cfg[nome]
        if sec.get("pular", "nao").strip().lower() in ("sim", "true", "1"):
            continue
        if "onde" not in sec or "valores" not in sec:
            sys.exit(f"ERRO: a secao [{nome}] precisa de 'onde' e 'valores'")
        valores = lista(sec["valores"])
        if len(valores) < 2:
            sys.exit(f"ERRO: [{nome}] tem so um valor - uma varredura precisa de "
                     f"pelo menos dois para haver o que comparar")
        vistos = {}
        for v in valores:
            s = sufixo(v)
            if s in vistos:
                sys.exit(f"ERRO: em [{nome}], '{v}' e '{vistos[s]}' dao a mesma pasta "
                         f"{nome}_{s}. Mude um dos valores.")
            vistos[s] = v
        tols = dict(tols_g)
        for c, chave in (("pico", "tol"), ("altura", "tol_altura"),
                         ("espectro", "tol_espectro"), ("gap", "tol_gap"),
                         ("energia", "tol_energia")):
            if chave in sec:
                tols[c] = float(sec[chave].strip())
        parar = sec.get("parar", parar_g).strip()
        if parar not in PARADAS:
            sys.exit(f"ERRO: em [{nome}], parar = '{parar}' e desconhecido.\n"
                     f"       validos: {' | '.join(PARADAS)}")
        referencia = sec.get("referencia", ref_g).strip()
        if referencia not in REFERENCIAS:
            sys.exit(f"ERRO: em [{nome}], referencia = '{referencia}' e desconhecida.\n"
                     f"       validas: {' | '.join(REFERENCIAS)}")
        etapas.append(Etapa(
            nome=nome,
            onde=lista(sec["onde"]),
            valores=valores,
            criterio=criterios(sec.get("criterio", criterio_g)),
            tols=tols,
            parar=parar,
            referencia=referencia,
            janela_pico=float(sec.get("janela_pico", janela_pico_g)),
        ))

    if not etapas:
        sys.exit(f"ERRO: {arquivo} nao tem nenhuma etapa (so a secao [geral]?)")

    return {
        "etapas": etapas,
        "janela": geral("janela", "auto"),
        "malha_de_teste": geral("malha_de_teste", "").strip(),
        "arquivo": geral("arquivo", leitura.ARQUIVO_PADRAO),
    }


def escada_int(v, passo=None, n=4):
    passo = passo or max(1, round(v / 5))
    vals = [v + passo * k for k in range(-(n - 2), 2)]
    return [x for x in vals if x > 0]


def escada_malha(n):
    inicio = max(2, n - 2)
    return [inicio + k for k in range(4)]


def comprimentos_de_rede(input_xml):
    try:
        cr = ET.parse(input_xml).getroot().find("structure/crystal")
    except ET.ParseError:
        return None
    if cr is None:
        return None
    escala = float((cr.get("scale") or "1.0").replace("d", "e"))
    vs = []
    for bv in cr.findall("basevect"):
        c = [float(x) for x in (bv.text or "").split()]
        if len(c) == 3:
            vs.append(escala * sum(x * x for x in c) ** 0.5)
    return tuple(vs) if len(vs) == 3 else None


def escada_malha_aniso(comprimentos, atual):
    d0 = sum(n * L for n, L in zip(atual, comprimentos)) / 3.0
    malhas = []
    for f in (0.6, 0.8, 1.0, 1.2, 1.4):
        m = tuple(max(1, round(d0 * f / L)) for L in comprimentos)
        if m not in malhas:
            malhas.append(m)
    return malhas


def template(input_xml):
    plano = leitura.plano_input(input_xml)
    raiz = ET.parse(input_xml).getroot()
    etapas = []

    corrigidas = [sp.get("speciesfile", "?") for sp in raiz.iterfind("structure/species")
                  if sp.find("dfthalfparam") is not None]
    if len(corrigidas) > 1:
        print(f"AVISO: {len(corrigidas)} especies tem <dfthalfparam> "
              f"({', '.join(corrigidas)}), e a etapa [rcut] so varre a PRIMEIRA "
              f"({corrigidas[0]}).")
        print("       Se a que interessa for outra, edite o 'onde' da secao [rcut]. Para")
        print("       varrer as duas juntas, ponha os dois caminhos separados por virgula;")
        print("       para varrer uma de cada vez, duplique a secao.")
    for sp in raiz.iterfind("structure/species"):
        dh = sp.find("dfthalfparam")
        if dh is None:
            continue
        arq = sp.get("speciesfile", "")
        base = float(dh.get("cut", 0) or 0) or 3.5
        vals = [round(base + k * 0.5, 2) for k in range(-3, 4)]
        vals = [v for v in vals if v > 0]
        etapas.append((
            "rcut", f"structure/species[@speciesfile='{arq}']/dfthalfparam@cut",
            ", ".join(f"{v:g}" for v in vals),
            f"raio de corte do DFT-1/2 na especie {arq}. NAO e convergencia: a curva\n"
            "#          do gap contra o r_cut tem um MAXIMO, e o r_cut otimo e o do\n"
            "#          maximo - por isso parar = maximo",
            ["criterio = gap", "parar    = maximo"]))
        break

    v = plano.get("xs/screening@nempty")
    if v:
        n = int(float(v))
        vals = sorted({max(5, round(n * f / 5) * 5) for f in (0.25, 0.5, 0.75, 1.0, 1.25)})
        etapas.append(("nempty", "xs/screening@nempty",
                       ", ".join(str(x) for x in vals),
                       "estados vazios do screening (barato: so entra na etapa de "
                       "screening,\n#          e todo o resto depende do screening estar convergido)",
                       []))

    v = plano.get("xs@gqmax")
    if v:
        g = float(v)
        vals = [round(g + k * 0.5, 1) for k in (-2, -1, 0, 1)]
        vals = [x for x in vals if x >= 1.0]
        etapas.append(("gqmax", "xs@gqmax",
                       ", ".join(f"{x:.1f}" for x in vals),
                       "corte |G+q| (barato, mesma etapa de screening; convergi-lo\n"
                       "#          DEPOIS da malha obrigaria a refazer a malha inteira)",
                       []))

    for attr in ("nstlbse", "nstlxas"):
        v = plano.get(f"xs/BSE@{attr}")
        if not v:
            continue
        n = v.split()
        c = int(n[-1])
        vals = [" ".join(n[:-1] + [str(x)]) for x in escada_int(c)]
        etapas.append((attr, f"xs/BSE@{attr}", ", ".join(vals),
                       "bandas na matriz BSE (custo ~ (nv*nc*nk)^2). Esta varredura mexe\n"
                       "#          so no ultimo numero (bandas de conducao); se precisar, faca\n"
                       "#          depois uma segunda etapa mexendo no primeiro (valencia)",
                       []))
        break

    v = plano.get("xs@ngridk")
    malha_barata = ""
    if not v and "groundstate@ngridk" in plano:
        malha_barata = " ".join(str(max(2, int(c) - 4))
                                for c in plano["groundstate@ngridk"].split())
    if v:
        atual = [int(x) for x in v.split()]
        L = comprimentos_de_rede(input_xml)
        if L:
            malhas = escada_malha_aniso(L, atual)
            extra = (f"\n#          Escada por DENSIDADE (n_i * |a_i| constante); "
                     f"|a_i| = {', '.join(f'{x:.2f}' for x in L)} bohr")
        else:
            n = atual[0]
            malhas = [(x, x, x) for x in sorted(set(escada_malha(n)))]
            extra = ""
        malha_barata = " ".join(map(str, malhas[0]))
        onde = "xs@ngridk, xs@ngridq" if "xs@ngridq" in plano else "xs@ngridk"
        etapas.append(("malhaqk", onde,
                       ", ".join(" ".join(map(str, m)) for m in malhas),
                       "malha k/q - o mais caro de todos: multiplica o custo de TODAS as\n"
                       "#          etapas anteriores e a diagonalizacao vai com nk^2.\n"
                       "#          Sempre por ultimo, com o resto ja fixado" + extra,
                       []))

    if "xs@xstype" not in plano:
        v = plano.get("groundstate@ngridk")
        if v:
            atual = [int(x) for x in v.split()]
            L = comprimentos_de_rede(input_xml)
            if L:
                malhas = escada_malha_aniso(L, atual)
                porque = ("malha de pontos-k do groundstate - o mais caro; deixe por "
                          "ultimo.\n#          A escada anda por DENSIDADE de pontos-k "
                          "(n_i * |a_i| constante),\n#          que e o unico jeito certo "
                          f"quando a cela nao e cubica.\n#          |a_i| = "
                          f"{', '.join(f'{x:.2f}' for x in L)} bohr")
            else:
                n = atual[0]
                malhas = [(x, x, x) for x in sorted({max(2, n + 2 * k) for k in (-1, 0, 1, 2)})]
                porque = "malha de pontos-k do groundstate - o mais caro; deixe por ultimo"
            etapas.append(("ngridkgs", "groundstate@ngridk",
                           ", ".join(" ".join(map(str, m)) for m in malhas), porque,
                           ["criterio    = gap", "referencia  = melhor"]))
        v = plano.get("groundstate@rgkmax")
        if v:
            r = float(str(v).replace("d", "e"))
            vals = [round(r + k, 1) for k in (-1, 0, 1, 2)]
            vals = [x for x in vals if x > 0]
            etapas.insert(max(0, len(etapas) - 1),
                          ("rgkmax", "groundstate@rgkmax",
                           ", ".join(f"{x:g}" for x in vals),
                           "tamanho da base APW. ATENCAO: rgkmax = rmt_menor x |G+k|max,\n"
                           "#          entao o mesmo numero da bases diferentes se os raios\n"
                           "#          de muffin-tin mudarem. O gap sozinho engana aqui: ele\n"
                           "#          e uma DIFERENCA de autovalores e o erro de base se\n"
                           "#          cancela nela - por isso a energia entra no criterio",
                           ["criterio    = gap+energia", "referencia  = melhor"]))

    modo_gap = any("criterio = gap" in ex for _, _, _, _, ex in etapas)
    janela = plano.get("xs/energywindow@intv", "auto")

    L = []
    A = L.append
    A("# ---------------------------------------------------------------------------")
    A("# convergencia.conf - plano de convergencia deste input.xml")
    A("#")
    A("# A ORDEM DAS SECOES e a ordem em que os parametros sao varridos: primeiro o")
    A("# que e barato e o que as etapas seguintes dependem; por ultimo a malha k/q,")
    A("# que multiplica o custo de tudo.")
    A("#")
    A("# O valor convergido de cada etapa entra no input.xml antes da etapa seguinte,")
    A("# de modo que todas as varreduras compartilham a mesma linha de base.")
    A("#")
    A("# O nome da secao vira o prefixo da pasta; o sufixo sai do proprio valor:")
    A('#   "3 3 3" -> malhaqk_333    "2.5" -> gqmax_25    "1 5 1 4" -> nstlbse_1514')
    A("#")
    A("# Gerado por: bin/convergir.py --criar-plano -- CONFIRA os valores antes de rodar.")
    A("# ---------------------------------------------------------------------------")
    A("")
    A("[geral]")
    padrao = "gap" if modo_gap else "pico"
    A(f"criterio       = {padrao:<11} # pico | altura | espectro | gap "
      f"(ou 'pico+altura')")
    A("                             # 'gap' le o INFO.OUT; os outros leem os EPSILON")
    A("tol            = 20          # meV - deslocamento maximo aceito do pico")
    A("tol_gap        = 10          # meV - variacao maxima aceita do gap")
    A("tol_energia    = 1           # meV/atomo - variacao maxima da energia total")
    A("tol_altura     = 2           # %   - variacao maxima da altura do pico")
    A("tol_espectro   = 2           # %   - max|dif| do espectro, em % da altura do pico")
    A(f"janela         = {janela:<11} # eV - faixa que interessa"
      f"{' (do <energywindow>)' if janela != 'auto' else ''}")
    A("janela_pico    = 1.0         # eV - largura da busca do pico, para nao comparar")
    A("                             #      picos diferentes quando o espectro muda muito")
    A("parar          = primeiro    # primeiro = para assim que dois vizinhos concordam")
    A("                             # todos    = roda a lista inteira (figura completa)")
    A("                             # maximo   = fica com o valor de MAIOR medida")
    A("                             #            (r_cut do DFT-1/2: maximiza, nao converge)")
    A("referencia     = vizinho     # vizinho = compara cada valor com o anterior")
    A("                             # melhor  = compara com o calculo MAIS COMPLETO da")
    A("                             #           lista. Roda a lista toda, mas e o unico")
    A("                             #           que prova convergencia: o teste de")
    A("                             #           vizinho aprova qualquer deriva lenta")
    A(f"malha_de_teste = {malha_barata:<11} # malha k/q barata nas etapas ANTERIORES a")
    A("                             # [malhaqk]; vazio = usa a que ja esta no input.xml")

    for i, (nome, onde, vals, porque, extras) in enumerate(etapas, 1):
        A("")
        A(f"# ---- etapa {i}: {porque}")
        A(f"[{nome}]")
        A(f"onde    = {onde}"
          f"{'       # os dois mudam juntos' if ',' in onde else ''}")
        for linha in extras:
            A(linha)
        A(f"valores = {vals}")

    if not etapas:
        A("")
        A("# Nenhum parametro conhecido (nempty, gqmax, nstlbse/nstlxas, ngridk,")
        A("# rgkmax, dfthalfparam@cut) foi")
        A("# encontrado neste input.xml. Escreva as etapas a mao, no formato:")
        A("#   [meuparametro]")
        A("#   onde    = xs/BSE@algumatributo")
        A("#   valores = 1, 2, 3")

    return "\n".join(L) + "\n"


def prevoo(src, input_xml, plano, etapas, n_rodadas):
    achados = []
    texto = input_xml.read_text()
    raiz = ET.fromstring(texto)
    flat = leitura.plano_input(input_xml)
    tem_espectral = any(e.modo == "espectro" for e in etapas)

    sp = flat.get("structure@speciespath", "")
    especies = [e.get("speciesfile") for e in raiz.iterfind("structure/species")]
    if "$" in sp:
        var = re.findall(r"\$\{?(\w+)", sp)
        achados.append(("erro",
            f'speciespath = "{sp}" - o run-exciting-task.sh deixa caminhos com "$"\n'
            f'    intactos de proposito, e {"/".join(var) or "a variavel"} nao existe dentro do container:\n'
            f'    o exciting nao vai achar {", ".join(x for x in especies if x)}.\n'
            f'    Troque por um caminho relativo (ex.: "{os.path.relpath(IC / "exciting" / "species", src)}/")\n'
            f'    ou copie os species para ca e use speciespath=".".'))
    elif sp in ("", ".", "./"):
        faltam = [f for f in especies if f and not (src / f).is_file()]
        if faltam:
            achados.append(("erro",
                f'speciespath = "." mas nao ha {", ".join(faltam)} nesta pasta.'))
        else:
            achados.append(("ok", f"{len(especies)} species na propria pasta"))
    else:
        alvo = Path(sp) if Path(sp).is_absolute() else (src / sp)
        faltam = [f for f in especies if f and not (alvo / f).is_file()]
        if faltam:
            achados.append(("erro",
                f'speciespath = "{sp}" nao tem {", ".join(faltam)}.'))
        else:
            achados.append(("ok", f"{len(especies)} species encontrados em {sp}"))

    skip = re.search(r'do[\s]*=[\s]*"skip"', texto)
    if skip and not (src / "STATE.OUT").is_file():
        achados.append(("erro",
            'o <groundstate> tem do="skip" mas nao ha STATE.OUT nesta pasta.\n'
            '    Rode o groundstate primeiro (do="fromscratch"), ou copie o STATE.OUT\n'
            '    do calculo de groundstate correspondente.'))
    elif skip:
        achados.append(("ok", 'do="skip" + STATE.OUT presente: o SCF nao sera refeito'))
    elif tem_espectral:
        achados.append(("aviso",
            f'o <groundstate> nao tem do="skip" e nao ha STATE.OUT aqui: o SCF sera\n'
            f'    refeito nas {n_rodadas} rodadas. Rode o groundstate uma vez nesta pasta\n'
            f'    e acrescente do="skip" para reaproveita-lo.'))
    else:
        achados.append(("ok", "varredura de gap: o SCF e refeito a cada rodada, que e "
                              "justamente\n    o que se esta medindo"))

    cru = input_xml.read_bytes()
    if any(b >= 0x80 for b in cru):
        linhas = [i for i, linha in enumerate(cru.split(b"\n"), 1)
                  if any(c >= 0x80 for c in linha)]
        trecho = ", ".join(str(i) for i in linhas[:6])
        achados.append(("erro",
            f"o input.xml tem caractere nao-ASCII na(s) linha(s) {trecho}.\n"
            f"    O parser do exciting nao le UTF-8 e falha com \"Could not open\n"
            f"    input.xml file\", que parece outra coisa. Troque acentos e\n"
            f"    travessoes por ASCII (o <title> e onde eles costumam entrar)."))
    else:
        achados.append(("ok", "input.xml sem caractere nao-ASCII"))

    faltando, criando = [], []
    for et in etapas:
        for onde in et.onde:
            caminho, attr = separa(onde)
            elem = caminho_xml(raiz, caminho)
            if elem is None:
                faltando.append(onde)
            elif attr not in elem.attrib:
                criando.append(onde)
    if faltando:
        achados.append(("erro",
            f"o input.xml nao tem o elemento de: {', '.join(faltando)}"))
    if criando:
        achados.append(("aviso",
            f"atributo ainda inexistente, vai ser criado: {', '.join(criando)}"))
    if not faltando and not criando:
        achados.append(("ok", f"os {sum(len(e.onde) for e in etapas)} caminhos de "
                              f"'onde' existem no input.xml"))

    if tem_espectral and plano["janela"] == "auto" and "xs/energywindow@intv" not in flat:
        achados.append(("erro",
            "janela = auto mas o input.xml nao tem <energywindow intv=...>.\n"
            "    Escreva a faixa a mao no convergencia.conf (ex.: janela = 0 27)."))

    return achados


class Medida:

    def __init__(self, gap=None, vbm=None, cbm=None, energia=None, atomos=None,
                 x=None, y=None, pico=None, altura=None, trocou=False):
        self.gap = gap
        self.energia = energia
        self.atomos = atomos
        self.vbm = vbm
        self.cbm = cbm
        self.x = x
        self.y = y
        self.pico = pico
        self.altura = altura
        self.trocou = trocou

    @property
    def principal(self):
        return self.gap if self.gap is not None else self.pico

    @property
    def direto(self):
        if self.vbm is None or self.cbm is None:
            return None
        return self.vbm == self.cbm

    def resumo(self, modo):
        if modo == "info":
            partes = []
            if self.gap is not None:
                partes.append(f"gap {self.gap:.4f} eV"
                              + ("" if self.direto is None
                                 else ("  (direto)" if self.direto else "  (indireto)")))
            if self.energia is not None:
                partes.append(f"E {self.energia:.6f} eV/atomo")
            return "   ".join(partes)
        return f"pico {self.pico:.3f} eV   altura {self.altura:.2f}"


def le_info(pasta):
    info = pasta / "INFO.OUT"
    if not info.is_file():
        return None
    texto = info.read_text(errors="replace")

    gap = vbm = cbm = None
    completo = re.findall(
        r"Estimated fundamental gap\s*:\s*([-\d.]+)[^\n]*\n"
        r"\s*valence-band maximum at\s+\d+\s+([-\d.\s]+?)\n"
        r"\s*conduction-band minimum at\s+\d+\s+([-\d.\s]+?)\n", texto)
    if completo:
        g, v, c = completo[-1]
        gap, vbm, cbm = float(g) * HARTREE_EV, " ".join(v.split()), " ".join(c.split())
    else:
        simples = re.findall(r"Estimated fundamental gap\s*:\s*([-\d.]+)", texto)
        if simples:
            gap = float(simples[-1]) * HARTREE_EV

    energia = atomos = None
    totais = re.findall(r"Total energy\s*:\s*([-\d.]+)", texto)
    if totais:
        xml = pasta / "input.xml"
        if xml.is_file():
            try:
                atomos = len(ET.parse(xml).getroot().findall("structure/species/atom"))
            except ET.ParseError:
                atomos = None
        energia = float(totais[-1]) * HARTREE_EV / (atomos or 1)

    if gap is None and energia is None:
        return None
    return Medida(gap=gap, vbm=vbm, cbm=cbm, energia=energia, atomos=atomos)


def ja_calculada(et, pasta, arquivo):
    if et.modo == "info":
        return le_info(pasta) is not None
    return leitura.espectro(pasta, arquivo) is not None


def mede(et, pasta, arquivo, janela, pico_ref, largura, col=leitura.COL_IM):
    if et.modo == "info":
        return le_info(pasta)

    xy = leitura.curva(pasta, arquivo, col, avisar=True)
    if xy is None:
        return None
    x, y = xy
    m = (x >= janela[0]) & (x <= janela[1])
    if not m.any():
        sys.exit(f"ERRO: o espectro de {pasta.name}/ nao tem nenhum ponto em "
                 f"{janela[0]:g}-{janela[1]:g} eV. Confira a 'janela' do convergencia.conf.")
    if pico_ref is None:
        i = int(np.argmax(y[m]))
        return Medida(x=x, y=y, pico=float(x[m][i]), altura=float(y[m][i]))
    pico, altura, trocou = leitura.pico_na_janela(x, y, m, pico_ref, largura)
    return Medida(x=x, y=y, pico=float(pico), altura=float(altura), trocou=bool(trocou))


def suspeita(et, d):
    if et.modo == "info":
        if "energia" in et.criterio or "energia" not in d:
            return None
        v = d["energia"][0]
        if np.isnan(v) or abs(v) <= et.tols["energia"]:
            return None
        return (f"atencao: o gap deu convergido, mas a energia total ainda muda "
                f"{abs(v):.1f} meV/atomo (tol_energia = {et.tols['energia']:g} "
                f"meV/atomo). O gap e uma diferenca de autovalores no mesmo ponto-k e "
                f"o erro de base se cancela nela; a energia nao perdoa. Acrescente "
                f"'energia' ao criterio desta etapa.")
    if "espectro" in et.criterio:
        return None
    v = d["espectro"][0]
    if np.isnan(v) or abs(v) <= et.tols["espectro"]:
        return None
    return (f"atencao: o criterio deu convergido, mas o espectro inteiro ainda muda "
            f"{abs(v):.1f}% (tol_espectro = {et.tols['espectro']:g}%). O pico dominante "
            f"desta janela pode ser insensivel a este parametro: estreite a 'janela' "
            f"em torno do pico que interessa, ou use criterio = espectro.")


def compara(et, atual, anterior, janela):
    d = {}

    if et.modo == "info":
        for chave, u in (("gap", "meV"), ("energia", "meV/atomo")):
            a, b = getattr(atual, chave), getattr(anterior, chave)
            d[chave] = (((a - b) * 1000.0) if (a is not None and b is not None)
                        else float("nan"), u)
        convergiu = all(abs(d[c][0]) < et.tols[c] for c in et.criterio) \
            and not any(np.isnan(d[c][0]) for c in et.criterio)
        return convergiu, d

    xa, ya, pico_a, alt_a = anterior.x, anterior.y, anterior.pico, anterior.altura
    x, y, pico, altura, trocou = (atual.x, atual.y, atual.pico, atual.altura,
                                  atual.trocou)

    d["pico"] = ((pico - pico_a) * 1000.0, "meV")
    d["altura"] = (100.0 * (altura - alt_a) / alt_a if alt_a else float("nan"), "%")

    if x.shape == xa.shape and np.allclose(x, xa):
        m = (x >= janela[0]) & (x <= janela[1])
        pico_max = np.abs(ya[m]).max()
        dif = np.abs(y[m] - ya[m]).max()
        d["espectro"] = (100.0 * dif / pico_max if pico_max else float("nan"), "%")
    else:
        d["espectro"] = (float("nan"), "%")

    if trocou:
        return False, d
    convergiu = all(abs(d[c][0]) < et.tols[c] for c in et.criterio) \
        and not any(np.isnan(d[c][0]) for c in et.criterio)
    return convergiu, d


LARG = 76
TRACO = "─" * LARG


def embrulha(prefixo, texto, larg=LARG):
    return textwrap.fill(texto, width=larg, initial_indent=f"{prefixo} ",
                         subsequent_indent=" " * (len(prefixo) + 1))


def hhmmss(s):
    s = int(s)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def mostra_plano(src, input_xml, plano, etapas, janela, modo, achados, n_rodadas):
    flat = leitura.plano_input(input_xml)
    titulo = (ET.parse(input_xml).getroot().findtext("title") or "").strip()
    extra = []
    if flat.get("xs@xstype"):
        extra.append(f"xstype={flat['xs@xstype']}")
    if flat.get("xs/BSE@xas") == "true":
        extra.append(f"xas borda {flat.get('xs/BSE@xasedge', '?')}")
    elif flat.get("xs/BSE@bsetype"):
        extra.append(f"bsetype={flat['xs/BSE@bsetype']}")

    try:
        onde_src = src.relative_to(IC)
    except ValueError:
        onde_src = src

    print(TRACO)
    print(f" PLANO DE CONVERGENCIA{'':<{max(1, LARG - 22 - len(str(onde_src)))}}{onde_src}/")
    print(TRACO)
    print(f" sistema  : {titulo or '(sem <title>)'}"
          f"{'   (' + ', '.join(extra) + ')' if extra else ''}")
    print(f" plano    : {PLANO_PADRAO}")
    print(f" modo     : {modo}")
    for et in etapas:
        regra = ("maximiza (fica com o maior)" if et.maximiza else
                 "   ".join(f"tol {c} = {et.tols[c]:g} {unidade(c)}"
                            for c in et.criterio))
        alvo = ("contra o mais completo da lista" if et.contra_o_melhor
                else f"parar: {et.parar}")
        print(f" criterio : {et.nome:<9} {'+'.join(et.criterio):<14} {regra}   {alvo}")
    if any(e.modo == "espectro" for e in etapas):
        print(f" janela   : {janela[0]:g}-{janela[1]:g} eV"
              f"{'   (do <energywindow>)' if plano['janela'] == 'auto' else ''}")
    print()

    faixas = {et.nome: f"{et.pasta(et.valores[0])} ... {et.pasta(et.valores[-1])}"
              for et in etapas}
    larg = max(len(f) for f in faixas.values())
    for i, et in enumerate(etapas, 1):
        prontas = sum(1 for v in et.valores
                      if ja_calculada(et, src / et.pasta(v), plano["arquivo"]))
        print(f" etapa {i}/{len(etapas)}  {et.nome:<9} {' + '.join(et.onde)}")
        print(f"            valores : {', '.join(et.valores)}")
        print(f"            pastas  : {faixas[et.nome]:<{larg}}   "
              f"({prontas}/{len(et.valores)} ja calculadas)")
    print()

    malha = plano["malha_de_teste"]
    if malha and any(e.mexe_na_malha for e in etapas):
        antes = [e.nome for e in etapas[:next(i for i, e in enumerate(etapas)
                                              if e.mexe_na_malha)]]
        if antes:
            print(f" As etapas {', '.join(antes)} rodam com a malha de teste "
                  f"{leitura.bonito(malha)}; o valor")
            print(" convergido de cada etapa entra no input.xml antes da seguinte.")
    else:
        print(" O valor convergido de cada etapa entra no input.xml antes da seguinte.")
    print(f" Ate {n_rodadas} rodadas"
          f"{'; com parar=primeiro, provavelmente menos.' if etapas[0].parar == 'primeiro' else '.'}")
    print()

    print(" CONFERIR ANTES DE RODAR")
    for nivel, txt in achados:
        marca = {"erro": "[erro]", "aviso": "[!]", "ok": "[ok]"}[nivel]
        print(f"  {marca} {txt}")
    print()
    print(" O input.xml sera MODIFICADO a cada rodada.")
    print(f" Copia de seguranca: {BACKUP} (restaurada em Ctrl+C)")
    print(TRACO)


def derruba(proc):
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        proc.wait()


def roda_exciting(src, pasta, args):
    cmd = [str(RUN_TASK), "--src", str(src), "--out", pasta,
           "-t", str(args.threads)]
    destino = src / pasta
    if destino.is_dir() and any(destino.iterdir()):
        cmd.append("--reusar")
    if args.mpi:
        cmd += ["--mpi", "-n", str(args.nproc)]
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, start_new_session=True)
    try:
        return proc.wait()
    except BaseException:
        derruba(proc)
        raise


def plota_gap(src, et, args):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    valores = [m[0] for m in et.medidas]
    chaves = [c for c in ("gap", "energia") if c in et.criterio] or ["gap"]
    UNIDADE = {"gap": ("gap [eV]", "eV"),
               "energia": ("energia total [eV/átomo]", "eV/átomo")}

    try:
        xs = [float(v) for v in valores]
        rotulos = None
    except ValueError:
        xs = list(range(len(valores)))
        rotulos = [leitura.bonito(v) for v in valores]

    titulo = (ET.parse(src / "input.xml").getroot().findtext("title") or src.name).strip()
    fig, axes = plt.subplots(len(chaves), 1, figsize=(7, 4 * len(chaves)), sharex=True,
                             squeeze=False)
    axes = [a for linha_ax in axes for a in linha_ax]
    for ax, chave in zip(axes, chaves):
        ys = [getattr(m[1], chave) for m in et.medidas]
        rotulo_y, unidade = UNIDADE[chave]
        if all(y is None for y in ys):
            ax.text(0.5, 0.5, f"sem {chave} medido", ha="center", va="center",
                    transform=ax.transAxes)
            ax.set_ylabel(rotulo_y)
            continue
        ax.plot(xs, ys, "o-", color="steelblue")
        if et.escolhido is not None and et.escolhido in valores:
            i = valores.index(et.escolhido)
            if ys[i] is not None:
                casas = 6 if chave == "energia" else 4
                ax.plot(xs[i], ys[i], "r*", markersize=16,
                        label=("máximo: " if et.maximiza else "escolhido: ")
                              + f"{ys[i]:.{casas}f} {unidade} em "
                                f"{leitura.bonito(et.escolhido)}")
                ax.legend()
        ax.set_ylabel(rotulo_y)
        ax.grid(True, alpha=0.3)
    if rotulos:
        axes[-1].set_xticks(xs)
        axes[-1].set_xticklabels(rotulos)
    axes[-1].set_xlabel(et.nome)
    axes[0].set_title(f"{titulo} - {' e '.join(chaves)} contra {et.nome}")
    fig.tight_layout()

    png = src / f"{et.nome}-gap.png"
    fig.savefig(png, dpi=150)
    plt.close(fig)
    print(f"[{et.nome}] figura: {png.name}")

    legenda = f"{' e '.join(chaves).capitalize()} contra {et.nome} - {titulo}"
    if args.registro:
        add_figura = IC / "registros" / "_scripts" / "add-figura.sh"
        if add_figura.is_file():
            subprocess.run([str(add_figura), "-f", str(png), "-l", legenda],
                           capture_output=True, text=True)

    ref = et.medidas[-1][1] if et.contra_o_melhor else None
    cab = f"| {et.nome} | gap (eV) | d gap (meV) | E (eV/atomo) | d E (meV/atomo) | direto? | tempo (s) |"
    linhas = [f"![{legenda}](figuras/{png.name})", f"*{legenda}*", "",
              cab, "|---|---:|---:|---:|---:|---|---:|"]
    for k, (valor, m, tempo) in enumerate(et.medidas):
        base = ref if ref is not None else (et.medidas[k - 1][1] if k else None)
        def delta(chave):
            a, b = getattr(m, chave), getattr(base, chave) if base else None
            if a is None or b is None:
                return "(ref)" if base is None else "-"
            return f"{(a - b) * 1000:+.1f}"
        direto = {True: "direto", False: "indireto", None: "-"}[m.direto]
        marca = " **<-**" if valor == et.escolhido else ""
        g = f"{m.gap:.4f}" if m.gap is not None else "-"
        e = f"{m.energia:.6f}" if m.energia is not None else "-"
        tt = f"{tempo:.1f}" if tempo else "-"
        linhas.append(f"| {leitura.bonito(valor)}{marca} | {g} | {delta('gap')} | "
                      f"{e} | {delta('energia')} | {direto} | {tt} |")
    if ref is not None:
        alvo = leitura.bonito(et.medidas[-1][0])
        aviso = ("" if alvo == leitura.bonito(et.valores[-1]) else
                 f" A lista pedia ate `{leitura.bonito(et.valores[-1])}`, que nao rodou.")
        linhas += ["", f"Deltas contra o calculo mais completo que rodou (`{alvo}`), "
                       f"nao contra o vizinho.{aviso}"]
    return "\n".join(linhas)


def escolhe_maximo(et):
    if not et.medidas:
        return
    valores = [m[0] for m in et.medidas]
    medidas = [m[1].principal for m in et.medidas]
    i = int(max(range(len(medidas)), key=lambda k: medidas[k]))
    et.escolhido = valores[i]
    et.confirmador = None

    vizinhos = [medidas[k] for k in (i - 1, i + 1) if 0 <= k < len(medidas)]
    if vizinhos:
        et.delta = (medidas[i] - max(vizinhos)) * 1000.0
    if len(medidas) > 1 and i in (0, len(medidas) - 1):
        lado = "para baixo" if i == 0 else "para cima"
        et.aviso = (f"o maximo caiu na BORDA da lista (em {valores[i]}): um maximo na "
                    f"ponta quase nunca e o maximo de verdade. Estenda 'valores' em "
                    f"[{et.nome}] {lado} e rode de novo.")


def escolhe_contra_melhor(et, janela):
    if len(et.medidas) < 2:
        return
    alvo_valor, alvo, _ = et.medidas[-1]
    for k in range(len(et.medidas) - 1):
        ok, d = compara(et, et.medidas[k][1], alvo, janela)
        if ok:
            et.escolhido = et.medidas[k][0]
            et.confirmador = alvo_valor
            et.delta = d[et.criterio[0]][0]
            et.aviso = et.aviso or suspeita(et, d)
            return
    _, d = compara(et, et.medidas[-2][1], alvo, janela)
    et.escolhido = alvo_valor
    et.delta = d[et.criterio[0]][0]
    et.aviso = et.aviso or (
        f"nenhum valor da lista concorda com o mais completo "
        f"({leitura.bonito(alvo_valor)}) dentro de {et.tols[et.criterio[0]]:g} "
        f"{unidade(et.criterio[0])} - nem o penultimo. A lista acabou antes da "
        f"convergencia: estenda 'valores' para alem de {leitura.bonito(alvo_valor)}.")


def roda_plot(src, et, janela, args):
    if et.modo == "info":
        return plota_gap(src, et, args)
    cmd = [sys.executable, str(PLOT), "-d", str(src), et.nome, "--diff",
           "-x", str(janela[0]), str(janela[1]),
           "--janela-pico", str(et.janela_pico), "-f", args.arquivo]
    if args.registro:
        cmd.append("--registro")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[convergir] AVISO: o plot de '{et.nome}' falhou:")
        print("    " + (r.stderr or r.stdout).strip().replace("\n", "\n    "))
        return None
    for linha in r.stdout.splitlines():
        if linha.startswith("grafico salvo em:"):
            print(f"[{et.nome}] figura: {Path(linha.split(':', 1)[1].strip()).name}")
    marca = "─" * 30 + " para colar no REGISTRO.md "
    if marca not in r.stdout:
        return None
    bloco = r.stdout.split(marca, 1)[1].split("\n", 1)[1]
    return bloco.split("─" * 87)[0].strip()


def escreve_resumo(src, etapas, feitas, inicio, n_rodadas, blocos):
    linhas = ["# Convergencia - " + src.name, ""]
    linhas.append(f"Gerado por `bin/convergir.py` a partir de `{PLANO_PADRAO}`.")
    linhas.append(f"{n_rodadas} rodada(s), {hhmmss(time.time() - inicio)} no total.")
    linhas.append("")
    linhas.append("| parametro | escolhido | confirmado por | delta | criterio |")
    linhas.append("|---|---|---|---|---|")
    for et in feitas:
        d = "-" if et.delta is None else f"{et.delta:+.1f} {unidade(et.criterio[0])}"
        conf = et.confirmador or "-"
        regra = (f"maximo do {et.criterio[0]}" if et.maximiza else
                 f"{'+'.join(et.criterio)} < {et.tols[et.criterio[0]]:g} "
                 f"{unidade(et.criterio[0])}")
        linhas.append(f"| {et.nome} | {leitura.bonito(et.escolhido or '-')} | "
                      f"{leitura.bonito(conf)} | {d} | {regra} |")
    if any(e.aviso for e in feitas):
        linhas += ["", "Avisos:"]
        linhas += [f"- **{e.nome}**: {e.aviso}" for e in feitas if e.aviso]
    for et in feitas:
        if blocos.get(et.nome):
            linhas += ["", f"## {et.nome}", "", blocos[et.nome]]
    if len(feitas) < len(etapas):
        faltam = [e.nome for e in etapas[len(feitas):]]
        linhas += ["", f"> Interrompido: faltaram as etapas {', '.join(faltam)}."]
    (src / RESUMO).write_text("\n".join(linhas) + "\n")


def executa(src, input_xml, plano, etapas, janela, args):
    inicio = time.time()
    flat = leitura.plano_input(input_xml)
    malha = plano["malha_de_teste"]
    i_malha = next((i for i, e in enumerate(etapas) if e.mexe_na_malha), None)
    feitas, blocos, n_rodadas = [], {}, 0

    for i, et in enumerate(etapas, 1):
        marca = f"[{i}/{len(etapas)} {et.nome}]"

        if malha and i_malha is not None and (i - 1) < i_malha:
            candidatas = ("xs@ngridk", "xs@ngridq") if "xs@ngridk" in flat \
                else ("groundstate@ngridk",)
            alvos = {o: malha for o in candidatas if o in flat}
            if alvos:
                escreve_valores(input_xml, alvos)
                print(f"{marca} malha de teste: {' + '.join(alvos)} = "
                      f"{leitura.bonito(malha)}")

        anterior = None
        for j, valor in enumerate(et.valores):
            pasta = et.pasta(valor)
            escreve_valores(input_xml, {onde: valor for onde in et.onde})

            print()
            print(f"{marca} {et.nome} = {valor}  ->  {pasta}/")
            if ja_calculada(et, src / pasta, plano["arquivo"]) and not args.refazer:
                print(f"{marca} pasta ja calculada - reaproveitando (use --refazer "
                      f"para recalcular)")
            else:
                rc = roda_exciting(src, pasta, args)
                n_rodadas += 1
                if rc != 0:
                    et.aviso = (f"o exciting saiu com codigo {rc} em {pasta}/; "
                                f"a etapa parou aqui")
                    print(f"{marca} ERRO: o exciting falhou (codigo {rc}). "
                          f"Parando esta etapa.")
                    break

            pico_ref = anterior.pico if anterior else None
            medida = mede(et, src / pasta, plano["arquivo"], janela, pico_ref,
                          et.janela_pico)
            if medida is None:
                falta = "gap/energia no INFO.OUT" if et.modo == "info" else "EPSILON"
                et.aviso = f"{pasta}/ nao produziu {falta}; a etapa parou aqui"
                print(f"{marca} ERRO: {pasta}/ nao tem {falta}. Parando esta etapa.")
                break

            t = leitura.tempo(src / pasta)
            et.medidas.append((valor, medida, t))

            if anterior is None:
                print(f"{marca} {medida.resumo(et.modo)}"
                      f"{'   ' + f'{t:.0f} s' if t else ''}")
            else:
                ok, d = compara(et, medida, anterior, janela)
                partes = "   ".join(
                    f"d {c} {d[c][0]:+.1f} {d[c][1]}" for c in et.criterio)
                limite = "   ".join(
                    f"{et.tols[c]:g} {unidade(c)}" for c in et.criterio)
                alvo = ("" if et.maximiza
                        else f"   ({'<' if ok else '>'} {limite})")
                print(f"{marca} {medida.resumo(et.modo)}   {partes}{alvo}"
                      f"{'   ' + f'{t:.0f} s' if t else ''}")
                if medida.trocou:
                    print(f"{marca} * o maximo do espectro esta fora de "
                          f"±{et.janela_pico:g} eV do pico anterior: o pico dominante "
                          f"mudou,\n{marca}   o espectro ainda nao tem a forma correta")
                if ok and not et.maximiza:
                    et.aviso = et.aviso or suspeita(et, d)
                if ok and et.parar == "primeiro" and not et.contra_o_melhor:
                    et.escolhido = et.valores[j - 1]
                    et.confirmador = valor
                    et.delta = d[et.criterio[0]][0]
                    if et.aviso:
                        print(embrulha(marca, "* " + et.aviso))
                    break
            anterior = medida

        if et.maximiza:
            escolhe_maximo(et)
        elif et.contra_o_melhor:
            escolhe_contra_melhor(et, janela)
        elif et.escolhido is None and len(et.medidas) >= 2:
            for k in range(1, len(et.medidas)):
                ok, d = compara(et, et.medidas[k][1], et.medidas[k - 1][1], janela)
                if ok:
                    et.escolhido = et.medidas[k - 1][0]
                    et.confirmador = et.medidas[k][0]
                    et.delta = d[et.criterio[0]][0]
                    et.aviso = et.aviso or suspeita(et, d)
                    break
        if et.escolhido is None and et.medidas:
            et.escolhido = et.medidas[-1][0]
            _, d = (compara(et, et.medidas[-1][1], et.medidas[-2][1], janela)
                    if len(et.medidas) >= 2 else (None, None))
            et.delta = d[et.criterio[0]][0] if d else None
            et.aviso = et.aviso or (
                f"nao convergiu dentro da lista; ficou com o ultimo valor rodado "
                f"({et.escolhido}). Estenda 'valores' em [{et.nome}].")
            print(f"{marca} NAO CONVERGIU na lista dada - ficando com "
                  f"{et.nome} = {et.escolhido}")
        elif et.escolhido is not None and et.maximiza:
            melhor = next(m[1] for m in et.medidas if m[0] == et.escolhido)
            margem = ("" if et.delta is None
                      else f"  (+{abs(et.delta):.1f} meV sobre o vizinho)")
            print(f"{marca} MAXIMO em {et.nome} = {et.escolhido}   "
                  f"{melhor.resumo(et.modo)}{margem}")
            if et.aviso:
                print(embrulha(marca, "* " + et.aviso))
        elif et.escolhido is not None:
            prova = ""
            if et.confirmador is not None and et.delta is not None:
                prova = (f"  ({et.confirmador} confirma: {abs(et.delta):.1f} "
                         f"{unidade(et.criterio[0])} < "
                         f"{et.tols[et.criterio[0]]:g} {unidade(et.criterio[0])})")
            print(f"{marca} CONVERGIU em {et.nome} = {et.escolhido}{prova}")

        if et.escolhido is None:
            print(f"{marca} nenhuma rodada utilizavel; o input.xml fica como estava")
            feitas.append(et)
            escreve_resumo(src, etapas, feitas, inicio, n_rodadas, blocos)
            continue

        mudou = escreve_valores(input_xml, {onde: et.escolhido for onde in et.onde})
        for onde, antes, depois in mudou:
            print(f"{marca} input.xml: {onde} = {depois}")

        blocos[et.nome] = roda_plot(src, et, janela, args)
        feitas.append(et)
        escreve_resumo(src, etapas, feitas, inicio, n_rodadas, blocos)

    total = time.time() - inicio
    print()
    print(TRACO)
    print(f" RESULTADO{'':<{max(1, LARG - 40)}}{hhmmss(total)}, {n_rodadas} rodada(s)")
    print(TRACO)
    print(f" {'parametro':<12}{'escolhido':<14}{'confirmado por':<16}"
          f"{'delta':>10}{'tempo':>10}")
    for et in feitas:
        t = next((m[2] for m in reversed(et.medidas) if m[2]), None)
        u = unidade(et.criterio[0])
        print(f" {et.nome:<12}{leitura.bonito(et.escolhido or '-'):<14}"
              f"{leitura.bonito(et.confirmador or '-'):<16}"
              f"{(f'{et.delta:+.1f} {u}' if et.delta is not None else '-'):>10}"
              f"{(f'{t:.0f} s' if t else '-'):>10}")
    for et in feitas:
        if et.aviso:
            print()
            print(embrulha(f" [!] {et.nome}:", et.aviso))
    print()
    print(" O input.xml agora tem os valores escolhidos.")
    print(f" Resumo: {RESUMO}   (tabelas prontas para colar no REGISTRO.md)")
    print(TRACO)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=".", help="pasta com o input.xml (default: .)")
    ap.add_argument("--plano", default=None,
                    help=f"arquivo do plano (default: {PLANO_PADRAO} ao lado do input.xml)")
    ap.add_argument("--mpi", action="store_true", help="usa MPI (senao, SMP serial)")
    ap.add_argument("-n", "--np", dest="nproc", type=int, default=2, help="ranks MPI")
    ap.add_argument("-t", "--threads", type=int, default=1, help="threads OpenMP por rank")
    ap.add_argument("--criterio", default="-",
                    help="sobrescreve o 'criterio' de TODAS as etapas do plano "
                         f"({' | '.join(CRITERIOS)}); '-' = usa o do convergencia.conf")
    ap.add_argument("--parar", default="-",
                    help="sobrescreve o 'parar' de todas as etapas "
                         f"({' | '.join(PARADAS)}); '-' = usa o do convergencia.conf")
    ap.add_argument("--etapas", default="-",
                    help="so estas etapas, separadas por espaco ('-' = todas)")
    ap.add_argument("--refazer", action="store_true",
                    help="recalcula pastas que ja tem espectro")
    ap.add_argument("--registro", action="store_true",
                    help="copia as figuras para figuras/ da semana atual")
    ap.add_argument("--sem-confirmar", dest="confirmar", action="store_false",
                    help="nao pergunta antes de comecar")
    ap.add_argument("--criar-plano", action="store_true",
                    help=f"escreve um {PLANO_PADRAO} a partir do input.xml e sai")
    ap.add_argument("--listar", action="store_true",
                    help="so mostra o plano e o pre-voo; nao roda nada")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    src = Path(args.src).resolve()
    input_xml = src / "input.xml"
    if not input_xml.is_file():
        sys.exit(f"ERRO: nao ha input.xml em {src}")

    arquivo_plano = Path(args.plano).resolve() if args.plano else src / PLANO_PADRAO

    if args.criar_plano:
        if arquivo_plano.exists():
            sys.exit(f"ERRO: {arquivo_plano.name} ja existe em {src}.\n"
                     f"       Apague-o ou edite-o a mao; nao vou sobrescrever.")
        arquivo_plano.write_text(template(input_xml))
        print(f"[convergir] escrito: {arquivo_plano}")
        print()
        print(arquivo_plano.read_text())
        print("[convergir] CONFIRA os valores acima antes de rodar a task.")
        return 0

    if not arquivo_plano.is_file():
        print(f"[convergir] nao ha {arquivo_plano.name} em {src}.")
        print("[convergir] escrevendo um a partir do input.xml...")
        print()
        arquivo_plano.write_text(template(input_xml))
        print(arquivo_plano.read_text())
        print(f"[convergir] escrito: {arquivo_plano}")
        print("[convergir] CONFIRA e ajuste os valores; depois rode a task de novo.")
        return 1

    plano = le_plano(arquivo_plano)
    etapas = plano["etapas"]
    args.arquivo = plano["arquivo"]

    crit = args.criterio.strip()
    if crit not in ("-", ".", ""):
        partes = [c.strip() for c in re.split(r"[+,]", crit) if c.strip()]
        ruins = [c for c in partes if c not in CRITERIOS]
        if ruins:
            sys.exit(f"ERRO: --criterio desconhecido: {', '.join(ruins)}\n"
                     f"       validos: {' | '.join(CRITERIOS)}")
        de_info = [c for c in partes if c in DE_INFO]
        espectrais = [c for c in partes if c in ESPECTRAIS]
        if de_info and espectrais:
            sys.exit(f"ERRO: --criterio mistura medidas do INFO.OUT "
                     f"({', '.join(de_info)}) com medidas do espectro "
                     f"({', '.join(espectrais)}). Escolha um dos dois grupos.")
        for e in etapas:
            e.criterio = list(partes)
    par = args.parar.strip()
    if par not in ("-", ".", ""):
        if par not in PARADAS:
            sys.exit(f"ERRO: --parar '{par}' e desconhecido.\n"
                     f"       validos: {' | '.join(PARADAS)}")
        for e in etapas:
            e.parar = par

    pedidas = [e for e in args.etapas.split() if e not in ("-", ".", "")]
    if pedidas:
        nomes = {e.nome for e in etapas}
        faltam = [p for p in pedidas if p not in nomes]
        if faltam:
            sys.exit(f"ERRO: etapa desconhecida: {', '.join(faltam)}\n"
                     f"       o {arquivo_plano.name} tem: {', '.join(sorted(nomes))}")
        etapas = [e for e in etapas if e.nome in pedidas]

    if plano["janela"] == "auto":
        intv = leitura.plano_input(input_xml).get("xs/energywindow@intv")
        janela = tuple(float(v) for v in intv.split()) if intv else (0.0, 27.0)
    else:
        janela = tuple(float(v) for v in plano["janela"].split())
    if len(janela) != 2 or janela[0] >= janela[1]:
        sys.exit(f"ERRO: 'janela' precisa ser 'min max' em eV (li: {plano['janela']})")

    n_rodadas = sum(len(e.valores) for e in etapas)
    modo = (f"MPI, {args.nproc} rank(s) x {args.threads} thread(s)" if args.mpi
            else f"SMP, {args.threads} thread(s)")
    achados = prevoo(src, input_xml, plano, etapas, n_rodadas)

    print()
    mostra_plano(src, input_xml, plano, etapas, janela, modo, achados, n_rodadas)

    erros = [t for nivel, t in achados if nivel == "erro"]
    if erros:
        print()
        print(f"[convergir] {len(erros)} problema(s) [erro] impedem a execucao. "
              f"Corrija o input.xml e rode de novo.")
        return 1

    if args.listar:
        print("\n[convergir] --listar: nada foi executado.")
        return 0

    if args.confirmar:
        if not sys.stdin.isatty():
            print("\n[convergir] sem terminal para confirmar. Use --sem-confirmar "
                  "se e isso mesmo que voce quer.")
            return 1
        print(" Enter = comecar    l = so listar e sair    Ctrl+C = cancelar")
        try:
            r = input("> ").strip().lower()
        except EOFError:
            print("\n[convergir] cancelado.")
            return 130
        if r in ("l", "listar"):
            print("[convergir] nada foi executado.")
            return 0
        if r not in ("", "s", "sim", "y"):
            print("[convergir] cancelado.")
            return 130

    backup = src / BACKUP
    backup.write_bytes(input_xml.read_bytes())
    print(f"\n[convergir] copia de seguranca: {BACKUP}")

    def _termina(sig, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _termina)
    try:
        return executa(src, input_xml, plano, etapas, janela, args)
    except KeyboardInterrupt:
        input_xml.write_bytes(backup.read_bytes())
        print(f"\n[convergir] interrompido - input.xml restaurado de {BACKUP}.")
        if (src / RESUMO).is_file():
            print(f"[convergir] as etapas ja concluidas estao em {RESUMO}.")
        print("[convergir] as pastas ja calculadas serao reaproveitadas se voce "
              "rodar de novo.")
        return 130
    except Exception:
        input_xml.write_bytes(backup.read_bytes())
        print(f"\n[convergir] erro - input.xml restaurado de {BACKUP}.")
        raise


if __name__ == "__main__":
    sys.exit(main())
