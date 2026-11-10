#!/usr/bin/env python3
"""Copia um calculo de runs para resultados como resultado definitivo."""
import argparse
import csv
import getpass
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import leitura

RAIZ = leitura.RAIZ
RESULTADOS = RAIZ / "resultados"
REFERENCIA = RAIZ / "registros" / "referencia-artigo.csv"

SAIDAS = ["INFO.OUT", "WARNINGS.OUT", "WARNING.OUT", "EFERMI.OUT", "TOTENERGY.OUT",
          "EIGVAL.OUT", "KPOINTS.OUT", "LATTICE.OUT", "SYMCRYS.OUT", "EQATOMS.OUT",
          "BONDLENGTH.OUT", "geometry.xml", "BAND.OUT", "BANDLINES.OUT", "TDOS.OUT",
          "exciting.log", "convergencia.md"]


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def git(*args):
    r = subprocess.run(["git", "-C", str(RAIZ), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def proximo_id():
    nums = [int(m.group(1)) for p in RESULTADOS.glob("R[0-9]*")
            if (m := re.match(r"R(\d+)-", p.name))]
    return f"R{(max(nums) + 1 if nums else 1):03d}"


def referencia(material, fase, nivel):
    if not REFERENCIA.is_file():
        return None
    linhas = (l for l in REFERENCIA.read_text().splitlines() if not l.startswith("#"))
    for r in csv.DictReader(linhas):
        if (r["material"], r["fase"], r["nivel"]) == (material, fase, nivel):
            return r
    return None


def le_job(run):
    job = run / "job.slurm"
    if not job.is_file():
        return {}
    t = job.read_text()
    d = {}
    for chave, padrao in (("particao", r"#SBATCH -p (\S+)"), ("ranks", r"--tasks-per-node (\d+)"),
                          ("threads", r"#SBATCH -c (\d+)"), ("tempo", r"#SBATCH -t (\S+)"),
                          ("conta", r"#SBATCH -A (\S+)")):
        m = re.search(padrao, t)
        if m:
            d[chave] = m.group(1)
    return d


def le_log_lise(run, nome_sub=None):
    logs = sorted(run.glob("lise-*.out")) or sorted(run.parent.glob("lise-*.out"))
    if not logs:
        return None, {}
    log = logs[-1]
    t = log.read_text(errors="replace")
    d = {"job": re.search(r"lise-(\d+)\.out", log.name).group(1)}
    m = re.search(r"no: (\S+)", t)
    if m:
        d["no"] = m.group(1)
    if "TIME LIMIT" in t or "CANCELLED" in t:
        d["aviso"] = "o job terminou cancelado (ver o log); confira se ESTE calculo terminou"
    return log, d


def geometria(run):
    a = leitura.vetores_de_rede(run)
    if a is None:
        return None
    ang = a * leitura.BOHR_PARA_ANG
    n = np.linalg.norm(ang, axis=1)

    def angulo(i, j):
        return float(np.degrees(np.arccos(np.dot(ang[i], ang[j]) / (n[i] * n[j]))))

    return {"a": n, "alfa": angulo(1, 2), "beta": angulo(0, 2), "gama": angulo(0, 1),
            "volume": abs(float(np.linalg.det(ang)))}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, help="pasta do calculo em runs/")
    ap.add_argument("--hipotese", required=True,
                    help="o que este calculo afirma e sob quais premissas (vai para a ficha)")
    ap.add_argument("--poscar", help="POSCAR de origem; padrao: estruturas/<material>/POSCAR.<fase>")
    ap.add_argument("--substitui", help="id do resultado que este corrige (ex.: R003)")
    ap.add_argument("--obs", default="", help="observacao livre")
    ap.add_argument("--simular", action="store_true", help="mostra a ficha e nao grava nada")
    args = ap.parse_args()

    run = Path(args.src).resolve()
    if not (run / "input.xml").is_file():
        sys.exit(f"ERRO: sem input.xml em {run}")
    inf = leitura.info(run)
    if inf is None:
        sys.exit("ERRO: sem INFO.OUT: o calculo nao rodou (ou nao foi trazido)")
    if not inf["convergiu"]:
        sys.exit(f"ERRO: o SCF nao convergiu ({inf['iteracoes']} iteracoes). "
                 "Resultado nao convergido nao e definitivo.")
    if args.substitui and not list(RESULTADOS.glob(f"{args.substitui}-*")):
        sys.exit(f"ERRO: {args.substitui} nao existe em resultados/")

    raiz_xml = leitura.raiz_input(run)
    especies = [sp.get("speciesfile") for sp in raiz_xml.iterfind("structure/species")]
    faltam = [e for e in especies if not (run / e).is_file()]
    if faltam:
        sys.exit(f"ERRO: especies ausentes na pasta: {', '.join(faltam)}")

    material = run.name.split("-")[0]
    fase = leitura.fase(run) or "?"
    nivel = leitura.nivel_de_teoria(run)
    poscar = Path(args.poscar) if args.poscar else RAIZ / "estruturas" / material / f"POSCAR.{fase}"
    if not poscar.is_file():
        sys.exit(f"ERRO: POSCAR de origem nao encontrado: {poscar} (use --poscar)")

    rid = proximo_id()
    destino = RESULTADOS / f"{rid}-{run.name}"
    log_lise, lise = le_log_lise(run)
    job = le_job(run) or le_job(run.parent)
    geo = geometria(run)
    ref = referencia(material, fase, nivel)
    versao = re.search(r"version hash id:\s*(\S+)", inf["texto"])
    nsim = re.search(r"Number of crystal symmetries\s*:\s*(\d+)", inf["texto"])
    rel = run.relative_to(RAIZ)
    status_git = git("status", "--porcelain", "--", str(rel / "input.xml"))
    rastreado = git("ls-files", "--error-unmatch", str(rel / "input.xml")) is not None

    copias = [("input.xml", run / "input.xml")]
    copias += [(e, run / e) for e in especies]
    for nome in ["job.slurm"] + SAIDAS:
        if (run / nome).is_file():
            copias.append((nome, run / nome))
    if not (run / "job.slurm").is_file() and (run.parent / "job.slurm").is_file():
        copias.append(("job.slurm", run.parent / "job.slurm"))
    if log_lise:
        copias.append((log_lise.name, log_lise))
    copias.append((f"origem/{poscar.name}", poscar))
    figuras = sorted((RAIZ / "registros").glob(f"semana-*/figuras/{run.name}/*.png"))
    copias += [(f"figuras/{f.name}", f) for f in figuras]

    gap = inf["gap_ev"]
    tipo = "direto" if inf["direto"] else ("indireto" if inf["direto"] is False else "?")
    L = [f"# {rid} - {material} `{fase}` {nivel}", "",
         "> Resultado definitivo. **Imexível:** não se edita nem se apaga. Uma correção é um",
         "> resultado novo com `--substitui`. Conferir: `bin/conferir-resultados.py`.", "",
         "| | |", "|---|---|",
         f"| **id** | {rid} |",
         f"| **promovido em** | {datetime.now():%d/%m/%Y %H:%M} por {git('config', 'user.name') or getpass.getuser()} |",
         f"| **cálculo de origem** | `{rel}` |",
         f"| **commit do repositório** | `{git('rev-parse', '--short', 'HEAD')}`"
         + (" (input.xml **não versionado** ainda)" if not rastreado else
            " (input.xml com alterações não commitadas)" if status_git else "") + " |",
         f"| **substitui** | {args.substitui or '-'} |",
         "", "## Hipótese", "", args.hipotese, ""]
    if args.obs:
        L += ["**Observação:** " + args.obs, ""]

    L += ["## Resultado", "", "| | |", "|---|---|",
          f"| **gap** | **{gap:.4f} eV** ({inf['gap_ha']:.8f} Ha), {tipo} |" if gap is not None
          else "| **gap** | não encontrado |",
          f"| VBM · CBM (ponto k) | {inf['kv']} · {inf['kc']} |",
          f"| energia total | {inf['etot']} Ha |",
          f"| SCF | {inf['iteracoes']} iterações, convergido |"]
    if ref and gap is not None:
        dire = float(ref["direto"]) if ref["direto"] else None
        ind = float(ref["indireto"]) if ref["indireto"] else None
        txt = f"direto {dire:.2f}" if dire is not None else ""
        if ind is not None:
            txt += f", indireto {ind:.2f}"
        delta = gap - (ind if (ind is not None and inf["direto"] is False) else dire)
        L.append(f"| artigo (Tabela S5, VASP) | {txt} eV -> Δ = **{delta:+.2f} eV** |")
    L.append("")

    L += ["## Estrutura", "", "| | |", "|---|---|",
          f"| POSCAR de origem | `{poscar.relative_to(RAIZ)}` (sha256 `{sha256(poscar)[:16]}...`, cópia em `origem/`) |"]
    if geo:
        a = geo["a"]
        L += [f"| \\|a₁\\| · \\|a₂\\| · \\|a₃\\| | {a[0]:.5f} · {a[1]:.5f} · {a[2]:.5f} Å |",
              f"| α · β · γ | {geo['alfa']:.3f}° · {geo['beta']:.3f}° · {geo['gama']:.3f}° |",
              f"| volume | {geo['volume']:.3f} Å³ |"]
    L += [f"| átomos na cela | {inf['natomos']} |",
          f"| simetrias do cristal (`INFO.OUT`) | {nsim.group(1) if nsim else '?'} |", ""]

    contagem = " · ".join(f"{Path(sp.get('speciesfile')).stem} {len(sp.findall('atom'))}"
                          for sp in raiz_xml.iterfind("structure/species"))
    cr = raiz_xml.find("structure/crystal")
    L += ["## Parâmetros (`input.xml`)", "", "| chave | valor |", "|---|---|",
          f"| `crystal@scale` | `{cr.get('scale') if cr is not None else '?'}` bohr |",
          f"| átomos por espécie | {contagem} (posições no `input.xml`) |"]
    L += [f"| `{k}` | `{v}` |" for k, v in leitura.plano_input(run).items()
          if not k.startswith(("title", "structure"))]
    for esp, cut, ion in leitura.r_cut_todos(run):
        L.append(f"| DFT-1/2 em `{esp}` | r_cut {cut} bohr, ionização {ion} |")
    L.append("")

    L += ["## Execução", "", "| | |", "|---|---|",
          f"| exciting | `{versao.group(1) if versao else '?'}` |",
          f"| máquina | {('Lise, nó ' + lise['no']) if lise.get('no') else 'local'} |",
          f"| job | {lise.get('job', '-')} · {job.get('particao', '?')} · {job.get('ranks', '?')} ranks × "
          f"{job.get('threads', '?')} threads · limite {job.get('tempo', '?')}"
          + (f" · conta {job['conta']}" if job.get("conta") else "") + " |",
          f"| pontos k irredutíveis | {int(inf['nk']) if inf['nk'] else '?'} |",
          f"| tempo (`INFO.OUT`) | {inf['tempo']:.0f} s |" if inf["tempo"] else "| tempo | ? |"]
    if lise.get("aviso"):
        L.append(f"| ATENCAO | {lise['aviso']} |")
    L.append("")
    if inf["avisos"]:
        L += ["## Avisos do exciting (`WARNINGS.OUT`)", "", "```", inf["avisos"][:2000], "```", ""]

    L += ["## Arquivos", "", "Checksums em `SHA256SUMS`.", ""]
    L += [f"- `{nome}` <- `{src.relative_to(RAIZ)}`" for nome, src in copias]
    ficha = "\n".join(L) + "\n"

    if args.simular:
        print(ficha)
        print(f"[simulacao] seria gravado em {destino.relative_to(RAIZ)}")
        return

    destino.mkdir(parents=True)
    for nome, src in copias:
        alvo = destino / nome
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, alvo)
    (destino / "FICHA.md").write_text(ficha)
    arquivos = sorted(p for p in destino.rglob("*") if p.is_file())
    somas = "".join(f"{sha256(p)}  {p.relative_to(destino)}\n" for p in arquivos)
    (destino / "SHA256SUMS").write_text(somas)

    for p in sorted(destino.rglob("*"), key=lambda p: -len(p.parts)):
        os.chmod(p, 0o555 if p.is_dir() else 0o444)
    os.chmod(destino, 0o555)

    indice()
    print(f"promovido: {destino.relative_to(RAIZ)}  ({len(arquivos) + 1} arquivos, somente-leitura)")
    print(f"  gap {gap:.4f} eV {tipo}" if gap is not None else "  gap nao encontrado")
    print("  falta: git add resultados/ && commit (o hook so aceita acrescentar)")


def indice():
    linhas = ["# Resultados definitivos", "",
              "Gerado por `bin/promover-resultado.py`. Regras em [README.md](README.md).", "",
              "| id | cálculo | gap (eV) | promovido em | substitui |", "|---|---|---:|---|---|"]
    for d in sorted(RESULTADOS.glob("R[0-9]*-*")):
        f = d / "FICHA.md"
        if not f.is_file():
            continue
        t = f.read_text()
        gap = re.search(r"\| \*\*gap\*\* \| \*\*([\d.]+) eV\*\*[^|]*?, (\w+)", t)
        quando = re.search(r"\*\*promovido em\*\* \| (\S+)", t)
        subst = re.search(r"\*\*substitui\*\* \| (\S+)", t)
        nome = d.name.split("-", 1)[1]
        linhas.append(f"| [{d.name.split('-')[0]}]({d.name}/FICHA.md) | `{nome}` | "
                      f"{gap.group(1) + ' ' + gap.group(2) if gap else '-'} | "
                      f"{quando.group(1) if quando else '?'} | {subst.group(1) if subst else '-'} |")
    alvo = RESULTADOS / "INDICE.md"
    if alvo.exists():
        os.chmod(alvo, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    alvo.write_text("\n".join(linhas) + "\n")


if __name__ == "__main__":
    main()
