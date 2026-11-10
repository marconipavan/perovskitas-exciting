#!/usr/bin/env python3
"""Confere cada resultado de resultados/ contra o seu SHA256SUMS."""
import argparse
import hashlib
import os
import sys
from pathlib import Path

RESULTADOS = Path(__file__).resolve().parent.parent / "resultados"


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def confere(d):
    problemas = []
    somas = d / "SHA256SUMS"
    if not somas.is_file():
        return ["sem SHA256SUMS"]
    esperado = {}
    for linha in somas.read_text().splitlines():
        h, nome = linha.split(None, 1)
        esperado[nome.strip()] = h
    presentes = {str(p.relative_to(d)) for p in d.rglob("*") if p.is_file()} - {"SHA256SUMS"}
    for nome in sorted(set(esperado) - presentes):
        problemas.append(f"APAGADO: {nome}")
    for nome in sorted(presentes - set(esperado)):
        problemas.append(f"ACRESCENTADO depois da promocao: {nome}")
    for nome in sorted(presentes & set(esperado)):
        if sha256(d / nome) != esperado[nome]:
            problemas.append(f"ALTERADO: {nome}")
    for p in [somas, *(d / n for n in presentes)]:
        if os.access(p, os.W_OK) and os.stat(p).st_mode & 0o222:
            problemas.append(f"perdeu o somente-leitura: {p.relative_to(d)}")
    return problemas


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quieto", action="store_true")
    args = ap.parse_args()
    pastas = sorted(p for p in RESULTADOS.glob("R[0-9]*-*") if p.is_dir())
    ruins = 0
    for d in pastas:
        probs = confere(d)
        if probs:
            ruins += 1
            print(f"x {d.name}")
            for p in probs:
                print(f"    {p}")
        elif not args.quieto:
            print(f"ok {d.name}")
    if not args.quieto or ruins:
        print(f"{len(pastas)} resultado(s), {ruins} com problema")
    sys.exit(1 if ruins else 0)


if __name__ == "__main__":
    main()
