#!/usr/bin/env python3
"""Monta o calculo de bandas e DOS a partir de um estado fundamental convergido."""
import argparse
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

IC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IC / "bin"))
import leitura


LOGS = {"INFO.OUT", "WARNINGS.OUT", "TOTENERGY.OUT", "RMSDVEFF.OUT", "DTOTENERGY.OUT",
        "CHGDIST.OUT", "DFSCFMAX.OUT", "BAND.OUT", "BANDLINES.OUT", "TDOS.OUT"}
LIMITE_LINK = 4 << 20
SEMPRE_COPIA = {"STATE.OUT"}


def convergiu(run):
    info = Path(run) / "INFO.OUT"
    return info.is_file() and "Convergence targets achieved" in info.read_text(
        errors="replace")


def pronto_para_banda(run):
    p = Path(run)
    if not (p / "input.xml").is_file():
        return False, "sem input.xml"
    if not (p / "STATE.OUT").is_file():
        return False, "sem STATE.OUT"
    if not convergiu(p):
        return False, "SCF nao convergiu"
    if (p / "BAND.OUT").is_file():
        return False, "ja tem BAND.OUT"
    return True, ""


def monta(run, destino=None, listar=False, passos=400, copiar_tudo=False):
    p = Path(run).resolve()
    pode, motivo = pronto_para_banda(p)
    if not pode:
        return None, motivo

    vetores = leitura.vetores_de_rede(p)
    if vetores is None:
        return None, "nao consegui ler os vetores de rede do input.xml"
    bloco, desc = leitura.caminho_de_bandas(vetores, passos=passos)
    if not bloco:
        return None, "o ASE nao detectou a rede de Bravais (instale ase)"

    destino = Path(destino) if destino else p.parent / f"{p.name}-bandas"
    print(f"  origem  : {p.relative_to(IC)}")
    print(f"  caminho : {desc}")
    print(f"  destino : {destino.relative_to(IC)}")
    if listar:
        return destino, None

    destino.mkdir(parents=True, exist_ok=True)

    texto = (p / "input.xml").read_text()
    if re.search(r'<groundstate\b[^>]*\bdo\s*=', texto):
        texto = re.sub(r'(<groundstate\b[^>]*\bdo\s*=\s*")[^"]*(")',
                       r'\1skip\2', texto, count=1)
    else:
        texto = re.sub(r'(<groundstate\b)', r'\1 do="skip"', texto, count=1)
    texto = re.sub(r'(<properties\b.*?</properties>\s*)', "", texto, flags=re.S)
    texto = texto.replace("</input>", bloco + "</input>")
    (destino / "input.xml").write_text(texto)

    n_copia, n_liga, bytes_ligados = 1, 0, 0
    for arq in sorted(p.glob("*.OUT")):
        if arq.name in LOGS:
            continue
        alvo = destino / arq.name
        if alvo.exists():
            alvo.unlink()
        if (arq.stat().st_size > LIMITE_LINK and not copiar_tudo
                and arq.name not in SEMPRE_COPIA):
            try:
                os.link(arq, alvo)
                n_liga += 1
                bytes_ligados += arq.stat().st_size
                continue
            except OSError:
                pass
        shutil.copy2(arq, alvo)
        n_copia += 1

    for esp in p.glob("*.xml"):
        if re.fullmatch(r"[A-Z][a-z]?\.xml", esp.name):
            shutil.copy2(esp, destino / esp.name)
            n_copia += 1

    aviso = (f", {n_liga} ligados ({bytes_ligados / 1e6:.0f} MB economizados)"
             if n_liga else "")
    print(f"  -> {n_copia} arquivos copiados{aviso}")
    return destino, None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-s", "--src", help="pasta do calculo ja convergido")
    ap.add_argument("--todos-prontos", action="store_true",
                    help="varre runs/ e monta para todo groundstate convergido sem banda")
    ap.add_argument("--passos", type=int, default=400, help="pontos do caminho")
    ap.add_argument("--copiar", action="store_true",
                    help="copia os autovetores em vez de ligar (gasta disco a toa)")
    ap.add_argument("--listar", action="store_true", help="so mostra, nao escreve")
    args = ap.parse_args()

    if args.todos_prontos:
        alvos = sorted(d for d in leitura.pastas_de_runs() if pronto_para_banda(d)[0])
        if not alvos:
            print("nenhum groundstate convergido sem BAND.OUT em runs/")
            return
    elif args.src:
        alvos = [Path(args.src)]
    else:
        ap.error("informe --src ou --todos-prontos")

    feitos = []
    for a in alvos:
        d, erro = monta(a, listar=args.listar, passos=args.passos,
                        copiar_tudo=args.copiar)
        if erro:
            print(f"  {Path(a).name}: {erro}")
        else:
            feitos.append(d)
        print()
    if feitos and not args.listar:
        print("Para rodar no Lise (cada um leva minutos, nao horas - o SCF ja esta feito):")
        print("  tasks 'Lise: criar job.slurm' e 'Lise: enviar e submeter', com o input.xml de cada pasta aberto:")
        for d in feitos:
            print(f"  {d.relative_to(IC)}")


if __name__ == "__main__":
    main()
