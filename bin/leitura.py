"""Funcoes de leitura de uma pasta de calculo do exciting."""
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

HARTREE_EV = 27.211386245988
BOHR_PARA_ANG = 0.529177210903
ANG_PARA_BOHR = 1.0 / BOHR_PARA_ANG
HBAR_C_EVCM = 1.9732698e-5
ALFA = 7.2973525693e-3
TEMPO_AU_S = 2.4188843265857e-17

COL_ENERGIA = 1
COL_RE = 2
COL_IM = 3
COL_KKT = 4

COL_EXC_E = 2
COL_EXC_LIG = 3
COL_EXC_OSC = 4

ARQUIVO_PADRAO = "singlet-TDA"


RAIZ = Path(__file__).resolve().parent.parent
RUNS = RAIZ / "runs"


def semana_corrente():
    semanas = sorted((p.name for p in (RAIZ / "registros").glob("semana-[0-9]*") if p.is_dir()),
                     key=lambda s: int(s.split("-")[1]))
    return semanas[-1] if semanas else None


def pastas_de_runs():
    saida = []
    if not RUNS.is_dir():
        return saida
    for d in sorted(RUNS.iterdir()):
        if not d.is_dir():
            continue
        if re.fullmatch(r"semana-\d+", d.name):
            saida += sorted(p for p in d.iterdir() if p.is_dir())
        else:
            saida.append(d)
    return saida


def acha_run(nome):
    achadas = [p for p in pastas_de_runs() if p.name == nome]
    if len(achadas) > 1:
        raise RuntimeError(f"pasta '{nome}' existe em mais de uma semana: "
                           + ", ".join(str(p.relative_to(RAIZ)) for p in achadas))
    return achadas[0] if achadas else None


def pasta_nova(nome):
    s = semana_corrente()
    return RUNS / s / nome if s else RUNS / nome


def _pasta(run):
    return Path(run) if not isinstance(run, Path) else run


def _ultimo(texto, padrao):
    achados = re.findall(padrao, texto)
    return achados[-1] if achados else None


def plano_input(run):
    run = _pasta(run)
    caminho = run / "input.xml" if run.is_dir() else run
    if not caminho.is_file():
        return {}
    plano = {}

    def anda(elem, prefixo):
        nome = f"{prefixo}/{elem.tag}" if prefixo else elem.tag
        for chave, valor in elem.attrib.items():
            plano[f"{nome}@{chave}"] = " ".join(valor.split())
        for filho in elem:
            anda(filho, nome)

    try:
        raiz = ET.parse(caminho).getroot()
    except ET.ParseError:
        return {}
    for filho in raiz:
        anda(filho, "")
    return plano


def _raiz(run):
    run = _pasta(run)
    caminho = run / "input.xml" if run.is_dir() else run
    if not caminho.is_file():
        return None
    try:
        return ET.parse(caminho).getroot()
    except ET.ParseError:
        return None


def raiz_input(run):
    return _raiz(run)


def titulo(run, formula_se_faltar=True):
    raiz = _raiz(run)
    if raiz is None:
        return None
    t = (raiz.findtext("title") or "").strip()
    if t:
        return t
    if not formula_se_faltar:
        return None
    especies = [Path(sp.get("speciesfile", "")).stem
                for sp in raiz.iterfind("structure/species")]
    return "".join(e for e in especies if e) or None


def nivel_de_teoria(run):
    raiz = _raiz(run)
    if raiz is None:
        return "?"
    gs = raiz.find("groundstate")
    if gs is None:
        return "?"
    xc = gs.get("xctype", "?").replace("GGA_", "")
    meio = gs.find("dfthalf") is not None
    spin = gs.find("spin")
    soc = spin is not None and spin.get("spinorb") == "true"
    return xc + ("-1/2" if meio else "") + ("+SOC" if soc else "")


def r_cut(run):
    raiz = _raiz(run)
    if raiz is None:
        return None
    for sp in raiz.iterfind("structure/species"):
        dh = sp.find("dfthalfparam")
        if dh is not None and dh.get("cut"):
            return sp.get("speciesfile", "?"), dh.get("cut")
    return None


def r_cut_todos(run):
    raiz = _raiz(run)
    if raiz is None:
        return []
    saida = []
    for sp in raiz.iterfind("structure/species"):
        dh = sp.find("dfthalfparam")
        if dh is None:
            continue
        ions = [c.get("ionization") for c in dh.findall("shell") if c.get("ionization")]
        saida.append((sp.get("speciesfile", "?"), dh.get("cut"),
                      " + ".join(ions) if ions else None))
    return saida


FASES = (("pm3m", r"Pm-?3m"), ("p4mbm", r"P4-?/?mbm"), ("i4mcm", r"I4-?/?mcm"),
         ("gamma", r"gamma|γ"), ("delta", r"delta|δ"),
         ("r3c", r"R-?3c"), ("r3m", r"R-?3m"))


def fase(run):
    run = _pasta(run)
    for fonte in (titulo(run, formula_se_faltar=False) or "", run.name):
        for nome, padrao in FASES:
            if re.search(rf"(?<![A-Za-z0-9]){padrao}(?![A-Za-z0-9])", fonte, re.I):
                return nome
    return None


def vetores_de_rede(run):
    raiz = _raiz(run)
    if raiz is None:
        return None
    cr = raiz.find("structure/crystal")
    if cr is None:
        return None
    escala = float((cr.get("scale") or "1.0").replace("d", "e"))
    vs = []
    for bv in cr.findall("basevect"):
        c = [float(x) for x in (bv.text or "").split()]
        if len(c) == 3:
            vs.append([escala * x for x in c])
    return np.array(vs) if len(vs) == 3 else None


def comprimentos_de_rede(run):
    a = vetores_de_rede(run)
    return tuple(float(np.linalg.norm(v)) for v in a) if a is not None else None


def tipo_de_calculo(run):
    raiz = _raiz(run)
    if raiz is None:
        return "?"
    xs = raiz.find("xs")
    if xs is not None:
        xstype = xs.get("xstype", "")
        bse = xs.find("BSE")
        if xstype in ("BSE", "fastBSE"):
            if bse is not None and bse.get("xas") == "true":
                return "BSE (XAS)"
            return "BSE" if xstype == "BSE" else "fastBSE"
        if xs.find("gw") is not None:
            return "GW"
        if xstype:
            return xstype
    gs = raiz.find("groundstate")
    if gs is not None and gs.find("dfthalf") is not None:
        return "DFT-1/2"
    if raiz.find("properties") is not None:
        return "DFT + bandas"
    return "DFT"


def segunda_variacao(run):
    plano = plano_input(run)
    explicito = plano.get("groundstate@tevecsv")
    if explicito is not None:
        return explicito.strip().lower() == "true", "tevecsv no input.xml"
    raiz = _raiz(run)
    gs = raiz.find("groundstate") if raiz is not None else None
    if gs is not None and gs.find("spin") is not None:
        spin = gs.find("spin")
        if spin.get("spinorb") == "true":
            return True, "<spin spinorb=\"true\"> no input.xml"
        return True, "<spin> presente no input.xml"
    return False, "sem <spin> e sem tevecsv (default do exciting)"


def pasta_do_resultado(run):
    run = _pasta(run)
    if (run / "INFO.OUT").is_file():
        return run
    conv = run / "convergencia.md"
    if not conv.is_file():
        return None
    for linha in conv.read_text(errors="replace").split("\n"):
        if linha.startswith("## "):
            break
        campos = [c.strip() for c in linha.strip().strip("|").split("|")]
        if len(campos) < 2 or not campos[0] or campos[0] == "parametro":
            continue
        if set(campos[0]) <= set("-: "):
            continue
        sufixo = re.sub(r"[^0-9A-Za-z]", "", campos[1].replace("×", " "))
        sub = run / f"{campos[0]}_{sufixo}"
        if (sub / "INFO.OUT").is_file():
            return sub
    return None


def info(run):
    run = _pasta(run)
    caminho = run / "INFO.OUT"
    if not caminho.is_file():
        return None
    texto = caminho.read_text(errors="replace")
    d = {"pasta": run, "texto": texto}

    completo = re.findall(
        r"Estimated fundamental gap\s*:\s*([-\d.]+)[^\n]*\n"
        r"\s*valence-band maximum at\s+(\d+)\s+([-\d.\s]+?)\n"
        r"\s*conduction-band minimum at\s+(\d+)\s+([-\d.\s]+?)\n", texto)
    d["vbm"] = d["cbm"] = None
    d["kv"] = d["kc"] = None
    if completo:
        g, kv, vbm, kc, cbm = completo[-1]
        d["gap_ha"] = float(g)
        d["vbm"], d["cbm"] = " ".join(vbm.split()), " ".join(cbm.split())
        d["kv"], d["kc"] = int(kv), int(kc)
    else:
        g = _ultimo(texto, r"Estimated fundamental gap\s*:\s*([-\d.]+)")
        d["gap_ha"] = float(g) if g else None
    d["gap_ev"] = d["gap_ha"] * HARTREE_EV if d["gap_ha"] is not None else None
    d["direto"] = (d["vbm"] == d["cbm"]) if d["vbm"] is not None else None

    for chave, padrao in (
            ("etot", r"Total energy\s*:\s*([-\d.]+)"),
            ("fermi", r"Fermi energy\s*:\s*([-\d.]+)"),
            ("dos_fermi", r"DOS at Fermi energy \(states/Ha/cell\)\s*:\s*([-\d.]+)"),
            ("tempo_scf", r"Total time spent \(seconds\)\s*:\s*([\d.]+)"),
            ("volume", r"Unit cell volume\s*:\s*([-\d.]+)"),
            ("nk", r"Total number of k-points\s*:\s*(\d+)"),
            ("nempty", r"Number of empty states\s*:\s*(\d+)"),
            ("carga", r"total charge\s*:\s*([-\d.]+)")):
        v = _ultimo(texto, padrao)
        d[chave] = float(v) if v else None

    natomos = len(re.findall(r"atomic positions", texto)) and None
    raiz = _raiz(run)
    if raiz is not None:
        natomos = sum(1 for _ in raiz.iterfind("structure/species/atom")) or None
    d["natomos"] = natomos
    d["etot_por_atomo"] = (d["etot"] / natomos) if (d["etot"] and natomos) else None

    d["iteracoes"] = len(re.findall(r"SCF iteration number", texto))
    d["convergiu"] = "Convergence targets achieved" in texto
    d["parou"] = "stopped" in texto
    avisos = run / "WARNING.OUT"
    if not avisos.is_file():
        avisos = run / "WARNINGS.OUT"
    d["avisos"] = avisos.read_text(errors="replace").strip() if avisos.is_file() else ""

    d["tempo"] = tempo(run)
    return d


def tempo(run):
    run = _pasta(run)
    for arquivo, padrao in (("INFOXS.OUT", r"CPU time  \(cumulative\)\s*:\s*([\d.]+) sec"),
                            ("INFO.OUT", r"Total time spent \(seconds\)\s*:\s*([\d.]+)")):
        caminho = run / arquivo
        if caminho.is_file():
            achados = re.findall(padrao, caminho.read_text(errors="replace"))
            if achados:
                return float(achados[-1])
    return None


def espectro(run, arquivo=ARQUIVO_PADRAO, avisar=False):
    run = _pasta(run)
    direto = run / arquivo
    if direto.is_file():
        return direto
    candidatos = sorted(run.glob("EPSILON/EPSILON_*OC11.OUT"),
                        key=lambda f: f.stat().st_mtime, reverse=True)
    if not candidatos:
        return None
    if avisar and len(candidatos) > 1:
        print(f"AVISO: {run.name}/ tem {len(candidatos)} espectros; usando o mais "
              f"recente ({candidatos[0].name}).")
        for outro in candidatos[1:]:
            print(f"       para usar outro: --file EPSILON/{outro.name}")
    return candidatos[0]


def curva(run, arquivo=ARQUIVO_PADRAO, col=COL_IM, avisar=False):
    arq = espectro(run, arquivo, avisar)
    if arq is None:
        return None
    dados = np.loadtxt(arq, comments="#")
    return dados[:, 0], dados[:, col - 1]


def cabecalho_epsilon(run, arquivo=ARQUIVO_PADRAO):
    arq = espectro(run, arquivo)
    if arq is None:
        return {}
    d = {}
    for linha in arq.read_text(errors="replace").splitlines():
        if not linha.startswith("#"):
            break
        if m := re.search(r"Unit cell volume \[au\]=\s*([\d.E+-]+)", linha):
            d["volume"] = float(m.group(1))
        elif m := re.search(r"Number of k-points=\s*(\d+)", linha):
            d["nk"] = int(m.group(1))
        elif m := re.search(r"Energy scale=\s*([\d.E+-]+)", linha):
            d["escala"] = float(m.group(1))
        elif m := re.search(r"Used broadening in scaled energy units:\s*([\d.E+-]+)", linha):
            d["broad"] = float(m.group(1))
    return d


def eps_estatico(run, arquivo=ARQUIVO_PADRAO):
    c = curva(run, arquivo, col=COL_RE)
    if c is None:
        return None
    x, y = c
    return float(y[np.argmin(x)])


def absorcao(run, arquivo=ARQUIVO_PADRAO):
    re_ = curva(run, arquivo, col=COL_RE)
    im_ = curva(run, arquivo, col=COL_IM)
    if re_ is None or im_ is None:
        return None
    energia, eps1 = re_
    _, eps2 = im_
    modulo = np.sqrt(eps1 ** 2 + eps2 ** 2)
    kappa = np.sqrt(np.maximum(0.5 * (modulo - eps1), 0.0))
    alpha = 2.0 * energia * kappa / HBAR_C_EVCM
    return energia, alpha


def bonito(valor):
    if valor and len(valor.split()) == 3:
        return valor.replace(" ", "×")
    return valor


def pico_na_janela(x, y, mascara, pico_ref, largura):
    janela = mascara & (np.abs(x - pico_ref) <= largura)
    if not janela.any():
        return float("nan"), float("nan"), True
    i = np.argmax(y[janela])
    global_max = x[mascara][np.argmax(y[mascara])]
    return x[janela][i], y[janela][i], abs(global_max - pico_ref) > largura


def manda_para_registro(png, legenda):
    import subprocess
    script = Path(__file__).resolve().parent.parent / "registros" / "_scripts" / "add-figura.sh"
    if not script.is_file():
        return None
    r = subprocess.run([str(script), "-f", str(png), "-l", legenda],
                       capture_output=True, text=True)
    if r.returncode != 0 and r.stderr:
        print(r.stderr.strip())
    return r.returncode


def arquivo_exciton(run, oc="OC11"):
    run = _pasta(run)
    candidatos = sorted(run.glob(f"EXCITON/EXCITON_*_{oc}.OUT"),
                        key=lambda f: f.stat().st_mtime, reverse=True)
    return candidatos[0] if candidatos else None


def exciton(run, oc="OC11", arquivo_epsilon=ARQUIVO_PADRAO):
    arq = arquivo_exciton(run, oc)
    if arq is None:
        return None
    texto = arq.read_text(errors="replace")
    d = {"arquivo": arq, "oc": oc}

    if m := re.search(r"E_shift\s*:\s*([-\d.E+]+)", texto):
        d["e_shift"] = float(m.group(1))
    else:
        d["e_shift"] = None

    dados = np.loadtxt(arq, comments="#")
    if dados.ndim == 1:
        dados = dados.reshape(1, -1)
    d["nr"] = dados[:, 0].astype(int)
    d["energia"] = dados[:, COL_EXC_E - 1]
    d["ligacao"] = dados[:, COL_EXC_LIG - 1]
    d["osc"] = dados[:, COL_EXC_OSC - 1]
    d["re"] = dados[:, 4] if dados.shape[1] > 4 else None
    d["im"] = dados[:, 5] if dados.shape[1] > 5 else None

    d.update(cabecalho_epsilon(run, arquivo_epsilon))
    usa_sv, motivo = segunda_variacao(run)
    d["tevecsv"], d["tevecsv_motivo"] = usa_sv, motivo
    if d.get("volume") and d.get("nk"):
        denominador = 4.0 * math.pi if usa_sv else 8.0 * math.pi
        d["fator_osc"] = d["volume"] * d["nk"] / denominador
    else:
        d["fator_osc"] = None
    return d


def reconstroi_epsilon(exc, energias_ev):
    if exc is None or not exc.get("broad"):
        return None
    d = exc["broad"] / HARTREE_EV
    e = exc["energia"] / HARTREE_EV
    o = exc["osc"]
    w = np.asarray(energias_ev, dtype=float)[:, None] / HARTREE_EV
    soma = (o[None, :] / (e[None, :] - w - 1j * d)
            + o[None, :] / (e[None, :] + w + 1j * d)).sum(axis=1)
    return 1.0 + soma


def dipolo2(exc):
    if exc is None or not exc.get("volume"):
        return None
    return exc["osc"] * exc["volume"] / (4.0 * math.pi)


def taxa_einstein(exc):
    d2 = dipolo2(exc)
    if d2 is None:
        return None, None
    e_ha = exc["energia"] / HARTREE_EV
    a_au = (4.0 / 3.0) * ALFA ** 3 * e_ha ** 3 * d2
    with np.errstate(divide="ignore", invalid="ignore"):
        a_s = a_au / TEMPO_AU_S
        tau = np.where(a_s > 0, 1.0 / a_s, np.inf)
    return a_s, tau


def brilhante(exc, fracao=1e-3):
    if exc is None or len(exc["osc"]) == 0:
        return None
    limiar = float(np.max(exc["osc"])) * fracao
    candidatos = np.nonzero(exc["osc"] > limiar)[0]
    return int(candidatos[0]) if len(candidatos) else None


def dieltens(run, arquivo="DIELTENS.OUT"):
    run = _pasta(run)
    caminho = run / arquivo
    if not caminho.is_file():
        return None
    linhas = caminho.read_text(errors="replace").splitlines()
    for i, linha in enumerate(linhas):
        if "real part" in linha:
            bloco = []
            for l in linhas[i + 1:i + 4]:
                nums = [float(v) for v in l.split()]
                if len(nums) < 3:
                    return None
                bloco.append(nums)
            return bloco[0][0], bloco[1][1], bloco[2][2]
    return None


BONITO = {"G": "GAMMA"}


def caminho_de_bandas(vetores, passos=400):
    try:
        from ase.cell import Cell
    except ImportError:
        return "", None

    try:
        cell = Cell(np.asarray(vetores, dtype=float))
        bp = cell.bandpath(npoints=0)
        rede = str(cell.get_bravais_lattice()).split("(")[0]
    except Exception:
        return "", None

    trechos = [re.findall(r"[A-Z][0-9]?", t) for t in bp.path.split(",")]
    trechos = [t for t in trechos if len(t) >= 2]
    if not trechos:
        return "", None

    linhas = []
    for i, trecho in enumerate(trechos):
        for j, r in enumerate(trecho):
            corta = j == len(trecho) - 1 and i < len(trechos) - 1
            coord = " ".join(f"{x:.6f}" for x in bp.special_points[r])
            linhas.append(f'           <point coord="{coord}" label="{BONITO.get(r, r)}"'
                          + (' breakafter="true"/>' if corta else "/>"))

    xml = ("   <properties>\n"
           "      <bandstructure>\n"
           "       <plot1d>\n"
           f'        <path steps="{passos}">\n'
           + "\n".join(linhas) + "\n"
           "        </path>\n"
           "       </plot1d>\n"
           "      </bandstructure>\n"
           '      <dos nsmdos="2" nwdos="1000" winddos="-0.5 0.5"/>\n'
           "   </properties>\n\n")
    desc = " | ".join("-".join(BONITO.get(r, r) for r in t) for t in trechos)
    return xml, f"{rede} · {desc}"
