#!/usr/bin/env python3
"""Gera as especies para SOC (svlo) a partir do LO_RECOMMENDATION.OUT de uma fase."""
import argparse
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

IC = Path(__file__).resolve().parent.parent
PADRAO = IC / "exciting" / "species"
REFERENCIA = IC / "registros" / "semana-07" / "species para SOC"
ESPECIES = ("Cs", "Sn", "Br")
LOREC_PM3M = IC / "runs" / "semana-07" / "CsSnBr3-pm3m-lorecommendation"

PBE = {"pm3m": ("runs/semana-06/CsSnBr3-pm3m-producao/CsSnBr3-pm3m-pbe-final", 35, "01:00:00"),
       "p4mbm": ("runs/semana-04/CsSnBr3-p4mbm-pbe", 50, "03:00:00"),
       "r3c": ("runs/semana-04/CsSnBr3-r3c-pbe", 126, "03:00:00"),
       "i4mcm": ("runs/semana-05/CsSnBr3-i4mcm-pbe", 30, "04:30:00"),
       "delta": ("runs/semana-05/CsSnBr3-delta-pbe", 36, "05:00:00"),
       "gamma": ("runs/semana-05/CsSnBr3-gamma-pbe", 48, "06:00:00")}


def le_lorec(pasta):
    rec, atual = {}, None
    for linha in (Path(pasta) / "LO_RECOMMENDATION.OUT").read_text().splitlines():
        m = re.search(r"species:\s*(\w+),\s*l\s*:\s*(\d+)", linha)
        if m:
            atual = (m.group(1), int(m.group(2)))
            continue
        p = linha.split()
        if atual and len(p) == 3 and p[0].isdigit():
            rec[(atual[0], atual[1], int(p[0]))] = float(p[2])
    return rec


def le_atomicos(pasta):
    t = (Path(pasta) / "atoms.xml").read_text()
    out = {}
    for bloco in re.finditer(r'chemicalSymbol="(\w+)".*?</atom>', t, flags=re.S):
        for n, l, k, e in re.findall(r'<state n="(\d+)" l="(\d+)" kappa="(\d+)" energy="([^"]+)"',
                                     bloco.group(0)):
            out[(bloco.group(1), int(n), int(l), int(k))] = float(e)
    return out


def gera_especie(simbolo, rec, atom):
    raiz = ET.parse(PADRAO / f"{simbolo}.xml").getroot()
    sp = raiz.find("sp")
    nao_caroco = []
    for st in sp.findall("atomicState"):
        if st.get("core") == "false":
            nl = (int(st.get("n")), int(st.get("l")))
            if nl not in nao_caroco:
                nao_caroco.append(nl)
    mt_r = ET.parse(REFERENCIA / f"{simbolo}.xml").getroot().find("sp/muffinTin")
    sp.find("muffinTin").set("radialmeshPoints", mt_r.get("radialmeshPoints"))

    los = []
    for n, l in sorted(nao_caroco, key=lambda x: (x[1], x[0])):
        e = rec[(simbolo, l, n - l - 1)]
        los.append((f"{n}{'spdf'[l]}", l, round(e, 2), None, f"regra A: recomendado (l={l}, {n - l - 1} nos) = {e:.4f}"))
    ps = [n for n, l in nao_caroco if l == 1]
    if ps:
        n = max(ps)
        e = atom[(simbolo, n, 1, 1)]
        los.append((f"{n}p1/2", 1, round(e, 2), 1, f"regra B: autovalor atomico {n}p1/2 = {e:.4f}"))

    basis = sp.find("basis")
    sp.remove(basis)
    linhas = ['    <basis>',
              '      <default type="lapw" trialEnergy="0.1500" searchE="false"/>']
    for nome, l, e, kappa, origem in sorted(los, key=lambda x: (x[1], x[2])):
        k = f' kappa="{kappa}"' if kappa else ""
        linhas += [f'      <lo l="{l}">',
                   f'        <wf matchingOrder="0" trialEnergy="{e:.2f}" searchE="false"{k}/>',
                   f'        <wf matchingOrder="1" trialEnergy="{e:.2f}" searchE="false"{k}/>',
                   '      </lo>']
    linhas.append('    </basis>')
    texto = ET.tostring(raiz, encoding="unicode")
    texto = re.sub(r"\s*</sp>", "\n" + "\n".join(linhas) + "\n  </sp>", texto, count=1)
    cab = '<?xml version="1.0" encoding="UTF-8"?>\n'
    return cab + texto + "\n", los


def gera(pasta_lorec, saida):
    rec, atom = le_lorec(pasta_lorec), le_atomicos(pasta_lorec)
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    tudo = {}
    for s in ESPECIES:
        texto, los = gera_especie(s, rec, atom)
        (saida / f"{s}.xml").write_text(texto)
        tudo[s] = los
    return tudo


def los_referencia(simbolo):
    t = (REFERENCIA / f"{simbolo}.xml").read_text()
    return [(int(l), float(e), bool(k)) for l, e, k in
            re.findall(r'<lo l="(\d)">\s*<wf matchingOrder="0" trialEnergy="([-\d.]+)"[^>]*?(kappa="1")?\s*/>', t)]


def validar():
    tudo = gera(LOREC_PM3M, IC / "runs" / "semana-07" / ".especies-validacao")
    print("LOs gerados pela regra (pm3m) x especies de referencia, em Ha:")
    for s in ESPECIES:
        print(f"  {s}")
        ref = los_referencia(s)
        for nome, l, e, kappa, origem in tudo[s]:
            cand = [x for x in ref if x[0] == l and x[2] == bool(kappa)]
            prox = min(cand, key=lambda x: abs(x[1] - e)) if cand else None
            d = f"{prox[1]:+.2f}  (dif {e - prox[1]:+.2f})" if prox else "-"
            print(f"    {nome:7s} l={l}{' kappa=1' if kappa else '        '}  regra {e:+.2f}   referencia {d}")
        sobra = [x for x in ref if not any(x[0] == l and abs(x[1] - e) < 0.06 and x[2] == bool(k)
                                              for _, l, e, k, _ in tudo[s])]
        for l, e, k in sobra:
            print(f"    (so na referencia: l={l} {e:+.2f}{' kappa=1' if k else ''})")
    shutil.rmtree(IC / "runs" / "semana-07" / ".especies-validacao")


def montar(fase, pasta_lorec):
    src_rel, nk, tempo = PBE[fase]
    src = IC / src_rel
    lote = IC / "runs" / "semana-07" / f"CsSnBr3-{fase}-soc-especies-da-fase"
    base = src.joinpath("input.xml").read_text()
    base = re.sub(r"\s*<properties>.*?</properties>", "", base, flags=re.S)
    base = re.sub(r'do="[a-z]+"', 'do="fromfile"', base, count=1)
    for sub, soc, titulo in (
            ("pbe-especies-da-fase", False, f"CsSnBr3 {fase} PBE - especies do SOC da propria fase (geradas do LO recommendation dela), sem SOC"),
            ("pbe-soc-especies-da-fase", True, f"CsSnBr3 {fase} PBE+SOC (svlo) - especies do SOC da propria fase (geradas do LO recommendation dela)")):
        t = re.sub(r"<title>.*?</title>", f"<title>{titulo}</title>", base)
        if soc:
            t = t.replace('do="fromfile"', 'do="fromfile"\n      useDensityMatrix="false"', 1)
            t = t.replace("</groundstate>", '   <spin spinorb="true" svlo="true"/>\n   </groundstate>', 1)
        d = lote / sub
        gera(pasta_lorec, d)
        (d / "input.xml").write_text(t)
        shutil.copy(src / "STATE.OUT", d / "STATE.OUT")
    r = subprocess.run([sys.executable, str(IC / "bin" / "lise" / "criar-job.py"), "--src", str(lote),
                        "--pontos-k", str(nk), "--tempo", tempo, "--particao", "cpu-clx", "--forcar"],
                       capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())
    print(f"montado: {lote.relative_to(IC)}  (especies de {Path(pasta_lorec).relative_to(IC)})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lorec", help="pasta com LO_RECOMMENDATION.OUT e atoms.xml da fase")
    ap.add_argument("--saida", help="pasta onde gravar Cs.xml, Sn.xml e Br.xml")
    ap.add_argument("--montar", choices=sorted(PBE), help="monta runs/semana-07/CsSnBr3-<fase>-soc-especies-da-fase")
    ap.add_argument("--validar", action="store_true", help="compara a regra com as especies de referencia")
    a = ap.parse_args()
    if a.validar:
        return validar()
    if not a.lorec:
        sys.exit("ERRO: falta --lorec")
    if a.montar:
        return montar(a.montar, IC / a.lorec if not Path(a.lorec).is_absolute() else Path(a.lorec))
    if not a.saida:
        sys.exit("ERRO: falta --saida (ou --montar)")
    for s, los in gera(a.lorec, a.saida).items():
        print(s, [(n, e) for n, _, e, _, _ in los])


if __name__ == "__main__":
    main()
