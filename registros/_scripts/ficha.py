#!/usr/bin/env python3
"""Gera em Markdown a ficha de parametros de um calculo."""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "bin"))
import leitura

BOHR_PARA_ANG = leitura.BOHR_PARA_ANG


def ler_input(pasta):
    return leitura.raiz_input(pasta), leitura.plano_input(pasta)


def ler_saida(pasta):
    info = {}
    padroes = {
        "versao": (r"version hash id:\s*(\S+)", "INFO.OUT"),
        "ranks MPI": (r"MPI version using\s+(\d+)\s+processor", "INFO.OUT"),
        "pontos k": (r"Total number of k-points\s*:\s*(\d+)", "INFO.OUT"),
        "volume da cela (bohr³)": (r"Unit cell volume\s*:\s*([-\d.]+)", "INFO.OUT"),
        "energia total (Ha)": (r"Total energy\s*:\s*([-\d.]+)", "INFO.OUT"),
        "energia de Fermi (Ha)": (r"Fermi energy\s*:\s*([-\d.]+)", "INFO.OUT"),
        "tempo total (s)": (r"Total time spent \(seconds\)\s*:\s*([\d.]+)", "INFO.OUT"),
    }
    for rotulo, (padrao, arquivo) in padroes.items():
        caminho = pasta / arquivo
        if not caminho.is_file():
            continue
        achados = re.findall(padrao, caminho.read_text(errors="replace"))
        if achados:
            info[rotulo] = achados[-1]

    infoxs = pasta / "INFOXS.OUT"
    if infoxs.is_file():
        texto = infoxs.read_text(errors="replace")
        achados = re.findall(r"CPU time  \(cumulative\)\s*:\s*([\d.]+) sec", texto)
        if achados:
            info["tempo do xs/BSE (s)"] = achados[-1]
        if re.search(r"is idle", texto):
            info["obs."] = "algum rank MPI ficou ocioso (poucos q-points)"
        achados = re.findall(r"MPI version using\s+(\d+)\s+processor", texto)
        if achados and "ranks MPI" not in info:
            info["ranks MPI"] = achados[0]
    return info


def tabela(titulo, linhas):
    if not linhas:
        return ""
    largura = max(len(str(k)) for k, _ in linhas)
    saida = [f"**{titulo}**", "", "| parâmetro | valor |", "|---|---|"]
    saida += [f"| `{k}` | {v} |" for k, v in linhas]
    saida.append("")
    return "\n".join(saida)


def bloco_sistema(raiz, plano, saida):
    linhas = []
    titulo = raiz.findtext("title")
    if titulo:
        linhas.append(("título", titulo.strip()))

    especies = []
    for esp in raiz.iter("species"):
        arq = esp.get("speciesfile", "?")
        n_atomos = len(esp.findall("atom"))
        especies.append(f"{Path(arq).stem} ({n_atomos} átomo{'s' if n_atomos > 1 else ''})")
    if especies:
        linhas.append(("espécies", ", ".join(especies)))

    cristal = raiz.find(".//crystal")
    if cristal is not None:
        escala = cristal.get("scale")
        if escala:
            a = float(escala)
            linhas.append(("scale", f"{a:g} bohr = {a * BOHR_PARA_ANG:.4f} Å"))
        vetores = [" ".join(v.text.split()) for v in cristal.findall("basevect")]
        if vetores:
            linhas.append(("basevect", "<br>".join(f"`{v}`" for v in vetores)))
            if escala and len(vetores) == 3:
                m = [[float(x) * float(escala) for x in v.split()] for v in vetores]
                det = (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                       - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                       + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
                linhas.append(("volume da cela", f"{abs(det):.4f} bohr³"))

    caminho = plano.get("structure@speciespath")
    if caminho:
        linhas.append(("speciespath", f"`{caminho}`"))
    return tabela("Sistema", linhas)


def bloco_elemento(raiz, nome, titulo):
    elem = raiz.find(nome)
    if elem is None:
        return ""
    linhas = [(k, f"`{v}`") for k, v in sorted(elem.attrib.items())]
    for filho in elem:
        for k, v in sorted(filho.attrib.items()):
            linhas.append((f"{filho.tag}/{k}", f"`{v}`"))
        if filho.tag == "qpointset":
            pontos = [" ".join(q.text.split()) for q in filho.findall("qpoint")]
            linhas.append((f"{filho.tag}", f"{len(pontos)} ponto(s): " +
                           ", ".join(f"`{p}`" for p in pontos)))
    return tabela(titulo, linhas)


def bloco_dfthalf(raiz):
    gs = raiz.find("groundstate")
    ligado = gs is not None and gs.find("dfthalf") is not None
    linhas = []
    for sp in raiz.iterfind("structure/species"):
        dh = sp.find("dfthalfparam")
        if dh is None:
            continue
        nome = Path(sp.get("speciesfile", "?")).stem
        partes = [f"r_cut = `{dh.get('cut', '?')}` bohr"]
        if dh.get("ampl"):
            partes.append(f"A = `{dh.get('ampl')}`")
        if dh.get("exponent"):
            partes.append(f"n = `{dh.get('exponent')}`")
        for casca in dh.findall("shell"):
            partes.append(f"camada `{casca.get('number', '?')}`, "
                          f"ionizacao `{casca.get('ionization', '?')}`")
        linhas.append((nome, " · ".join(partes)))
    if not linhas and not ligado:
        return ""
    if ligado and not linhas:
        linhas.append(("(aviso)", "`<dfthalf>` ligado, mas nenhuma especie tem "
                                  "`<dfthalfparam>` - o calculo sai igual ao DFT padrao"))
    if not ligado and linhas:
        linhas.append(("(aviso)", "ha `<dfthalfparam>`, mas falta `<dfthalf/>` no "
                                  "`<groundstate>` - a correcao NAO foi aplicada"))
    return tabela("DFT-1/2", linhas)


def bloco_resultado(pasta):
    linhas = []
    d = leitura.info(pasta)
    if d and d["gap_ev"] is not None:
        marca = "" if d["direto"] in (True, None) else "* (indireto)"
        linhas.append(("gap (eV)", f"**{d['gap_ev']:.4f}**{marca}"))
        if d["direto"] is not None:
            linhas.append(("VBM -> CBM", f"k {d['kv']} `{d['vbm']}` -> k {d['kc']} `{d['cbm']}`"))
    if d and not d["convergiu"]:
        linhas.append(("ATENCAO SCF", "não reportou `Convergence targets achieved`"))

    exc = leitura.exciton(pasta)
    if exc is not None:
        i = leitura.brilhante(exc)
        if i is not None:
            linhas.append(("1ª excitação brilhante (eV)", f"**{exc['energia'][i]:.4f}**"))
            linhas.append(("energia de ligação (eV)", f"**{exc['ligacao'][i]:.4f}**"))
            linhas.append(("força de oscilador", f"{exc['osc'][i]:.4e}"))
        eps = leitura.eps_estatico(pasta)
        if eps is not None:
            linhas.append(("ε∞ (do BSE)", f"{eps:.4f}"))
    return tabela("Resultado", linhas)


def ficha_unica(pasta, raiz, plano):
    partes = [f"#### Ficha - `{pasta.name}`", ""]
    partes.append(bloco_sistema(raiz, plano, pasta))
    partes.append(bloco_elemento(raiz, "groundstate", "Groundstate"))
    partes.append(bloco_dfthalf(raiz))
    partes.append(bloco_elemento(raiz, "xs", "xs / BSE"))
    partes.append(bloco_elemento(raiz, "properties", "Properties"))
    partes.append(bloco_resultado(pasta))

    exec_info = ler_saida(pasta)
    partes.append(tabela("Execução", list(exec_info.items())))
    return "\n".join(p for p in partes if p)


def ficha_varredura(base, prefixo):
    pastas = sorted(
        (p for p in base.glob(f"{prefixo}_*") if (p / "input.xml").is_file()),
        key=lambda p: (int(m.group(1)) if (m := re.search(rf"{prefixo}_(\d+)", p.name)) else 0),
    )
    if not pastas:
        sys.exit(f"ERRO: nenhuma subpasta {prefixo}_* com input.xml em {base}")

    planos = {}
    for p in pastas:
        _, plano = ler_input(p)
        planos[p] = plano

    todas = set().union(*(set(pl) for pl in planos.values()))
    variam = sorted(k for k in todas
                    if len({planos[p].get(k) for p in pastas}) > 1)

    colunas = ["pasta"] + variam + ["tempo (s)"]
    linhas = []
    for p in pastas:
        exec_info = ler_saida(p)
        tempo = exec_info.get("tempo do xs/BSE (s)", exec_info.get("tempo total (s)", "-"))
        linhas.append([f"`{p.name}`"] + [f"`{planos[p].get(k, '-')}`" for k in variam] + [tempo])

    def curto(chave):
        if "@" not in chave:
            return chave
        caminho, atrib = chave.rsplit("@", 1)
        return f"{caminho.split('/')[-1]}@{atrib}"

    cabecalho = [curto(c) for c in colunas]
    saida = [f"#### Varredura de `{prefixo}` - {len(pastas)} cálculos", "",
             "| " + " | ".join(cabecalho) + " |",
             "|" + "---|" * len(colunas)]
    saida += ["| " + " | ".join(l) + " |" for l in linhas]
    saida.append("")

    if variam:
        saida.append(f"Variou: {', '.join('`' + v + '`' for v in variam)}.")
    else:
        saida.append("Nenhum parâmetro difere entre as pastas.")
    saida.append("")

    raiz, plano = ler_input(pastas[0])
    saida.append(f"Demais parâmetros, comuns a todos os cálculos (de `{pastas[0].name}`):")
    saida.append("")
    saida.append(ficha_unica(pastas[0], raiz, plano))
    return "\n".join(saida)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-s", "--src", default=".", help="pasta do cálculo (default: atual)")
    p.add_argument("-v", "--varia", metavar="PREFIXO", default="",
                   help="tabela comparativa das subpastas PREFIXO_* (ex.: nempty). "
                        "'-' ou vazio = ficha unica (usado pela task do VS Code)")
    p.add_argument("-a", "--append", metavar="ARQUIVO",
                   help="acrescenta a saída ao fim desse arquivo em vez de imprimir")
    args = p.parse_args()

    base = Path(args.src).resolve()
    if not base.is_dir():
        sys.exit(f"ERRO: pasta nao existe: {base}")

    varia = args.varia.strip()
    if varia in ("-", ".", ""):
        varia = ""

    if varia:
        texto = ficha_varredura(base, varia)
    else:
        raiz, plano = ler_input(base)
        if raiz is None:
            sys.exit(f"ERRO: nao ha input.xml em {base}\n"
                     f"      (para uma varredura, use --varia PREFIXO)")
        texto = ficha_unica(base, raiz, plano)

    if args.append:
        destino = Path(args.append)
        if not destino.is_file():
            sys.exit(f"ERRO: arquivo nao existe: {destino}")
        with destino.open("a") as fh:
            fh.write("\n" + texto + "\n")
        print(f"ficha acrescentada em: {destino}")
    else:
        print(texto)


if __name__ == "__main__":
    main()
