#!/usr/bin/env python3
"""Gera as figuras adequadas a uma pasta de calculo."""
import argparse
import subprocess
import sys
from pathlib import Path

IC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(IC / "bin"))
import leitura


def o_que_cabe(pasta):
    p = Path(pasta)
    tarefas = []

    tem_banda = (p / "BAND.OUT").is_file()
    tem_dos = (p / "TDOS.OUT").is_file()
    if tem_banda or tem_dos:
        rot = ("bandas + DOS" if tem_banda and tem_dos else
               "estrutura de bandas" if tem_banda else "densidade de estados")
        tarefas.append((rot, ["python3", "bin/plot-bandas.py", "--src", str(p)], True))

    if (p / "KPATHEXC").is_dir() and any((p / "KPATHEXC").glob("KPATH_*")):
        tarefas.append(("pesos excitonicos na banda",
                        ["python3", "bin/plot-exciton-weights.py", "-d", str(p)], True))

    if leitura.arquivo_exciton(p) is not None:
        tarefas.append(("otica: Im eps e alpha",
                        ["python3", "bin/otica.py", "--src", str(p), "--figura",
                         "-n", "3"], True))

    if any(p.glob("excitonWavefunction-*.cube")):
        tarefas.append(("isovalores do VESTA",
                        ["python3", "bin/exciton-raio.py", "--src", str(p),
                         "--isovalores"], False))

    if (p / "convergencia.conf").is_file():
        import re
        degraus = [d for d in p.iterdir()
                   if d.is_dir() and re.match(r"^[A-Za-z][A-Za-z0-9]*_[\d.]+$", d.name)]
        if len(degraus) >= 2:
            prefixos = sorted({d.name.rsplit("_", 1)[0] for d in degraus})
            for pref in prefixos:
                tarefas.append((f"comparacao da varredura {pref}",
                                ["python3", "bin/plot-convergencia.py", "-d", str(p),
                                 pref], True))
    return tarefas


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-s", "--src", default=".")
    ap.add_argument("--registro", action="store_true",
                    help="copia as figuras para figuras/ da semana")
    ap.add_argument("--listar", action="store_true", help="so diz o que faria")
    ap.add_argument("--silencioso", action="store_true",
                    help="nao imprime a saida de cada script (uso em hook)")
    args = ap.parse_args()

    pasta = Path(args.src).resolve()
    if not pasta.is_dir():
        sys.exit(f"ERRO: pasta nao existe: {pasta}")

    tarefas = o_que_cabe(pasta)
    if not tarefas:
        print(f"  nada a plotar em {pasta.name}: sem BAND.OUT, TDOS.OUT, "
              f"EXCITON/ ou varredura")
        return

    print(f"  {pasta.relative_to(IC) if IC in pasta.parents else pasta}")
    for rot, cmd, registravel in tarefas:
        if args.registro and registravel:
            cmd = cmd + ["--registro"]
        if args.listar:
            print(f"    · {rot}")
            continue
        r = subprocess.run(cmd, cwd=IC, capture_output=True, text=True, timeout=600)
        if r.returncode == 0:
            linha = next((l for l in r.stdout.splitlines() if "figura:" in l), "")
            nome = linha.split("figura:")[-1].strip() if linha else "ok"
            print(f"    ok {rot:<32} {Path(nome).name if linha else ''}")
            if not args.silencioso and not linha:
                print("      " + (r.stdout.strip().splitlines() or [""])[-1])
        else:
            erro = (r.stderr or r.stdout).strip().splitlines()
            print(f"    x {rot:<32} {erro[-1][:60] if erro else 'falhou'}")


if __name__ == "__main__":
    main()
