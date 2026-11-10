#!/usr/bin/env python3
"""Calcula a extensao espacial do exciton a partir do arquivo .cube."""
import argparse
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import leitura

BOHR_A = leitura.BOHR_PARA_ANG


def le_cube(caminho):
    texto = caminho.read_text(errors="replace").split("\n")
    buraco = None
    if m := re.search(r"hole position:\s*([-\d.\s]+)", texto[1]):
        buraco = np.array([float(v) for v in m.group(1).split()])
    elif m := re.search(r"electron position:\s*([-\d.\s]+)", texto[1]):
        buraco = np.array([float(v) for v in m.group(1).split()])

    cab = texto[2].split()
    natomos, origem = int(cab[0]), np.array([float(v) for v in cab[1:4]])
    dims, passos = [], []
    for i in (3, 4, 5):
        p = texto[i].split()
        dims.append(int(p[0]))
        passos.append([float(v) for v in p[1:4]])
    inicio = 6 + abs(natomos)
    dados = np.array(" ".join(texto[inicio:]).split(), dtype=float)
    n = int(np.prod(dims))
    if dados.size < n:
        sys.exit(f"ERRO: {caminho.name} tem {dados.size} valores, esperados {n}.")
    return dados[:n].reshape(dims), origem, np.array(passos), buraco


FRACOES = (0.50, 0.30, 0.20, 0.10, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001)


def tabela_isovalores(rho):
    total = float(rho.sum())
    maximo = float(rho.max())
    print()
    print(f"  ISOVALORES para o VESTA   (maximo da grade = {maximo:.4g})")
    print()
    print(f"  {'% do max':>9} {'isovalor':>12} {'dentro':>9} {'pontos':>9}")
    print(f"  {'-'*9} {'-'*12} {'-'*9} {'-'*9}")
    linhas = []
    for f in FRACOES:
        iso = maximo * f
        mascara = rho >= iso
        n = int(mascara.sum())
        dentro = float(rho[mascara].sum()) / total if total else 0.0
        linhas.append((f, iso, dentro, n))
        print(f"  {f*100:>8.1f}% {iso:>12.5g} {dentro:>8.1%} {n:>9}")

    poucos = [l for l in linhas if l[3] <= 5]
    if poucos:
        pior = poucos[-1]
        print()
        print(f"  [!] ate {pior[0]*100:.1f}% do maximo a isosuperficie tem "
              f"{pior[3]} ponto(s) de grade e ja contem {pior[2]:.1%} da densidade.")
        print("      Isso e um PICO DE UM PONTO - artefato da grade perto do nucleo, nao")
        print("      a forma do exciton. Usar um isovalor nessa faixa mostra uma bolinha.")
    uteis = [l for l in linhas if l[3] > 20]
    if uteis:
        alvo = min(uteis, key=lambda l: abs(l[2] - 0.5))
        print()
        print(f"  Sugestao: **{alvo[1]:.5g}** ({alvo[0]*100:.1f}% do maximo) - contem "
              f"{alvo[2]:.0%} da densidade em {alvo[3]} pontos.")
    print()
    print("  O isovalor ABSOLUTO nao transfere entre calculos: ele depende da")
    print("  normalizacao da funcao de onda, que muda com os parametros. O que")
    print("  transfere e a fracao do maximo - ou, melhor ainda, a densidade contida.")
    print()
    print("  No VESTA: Properties -> Isosurfaces -> clicar na linha da tabela branca")
    print("  -> 'Isosurface level' = o valor da coluna do meio -> OK.")
    print("  Depois Boundary: trocar 'XCrySDen XSF file' por 'XCrySDen XSF structure")
    print("  data', pôr x/y/z(min) = -1 e x/y/z(max) = 2 (a supercelula 3x3x3), OK.")
    print("  Por fim: vista ao longo do eixo 'a' e desmarcar 'Show session'.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-s", "--src", default=".", help="pasta do calculo")
    ap.add_argument("-a", "--arquivo", default="", help="cube especifico")
    ap.add_argument("--raios", nargs="*", type=float, default=[1, 2, 3, 4],
                    metavar="A", help="raios em angstrom para o peso acumulado")
    ap.add_argument("--isovalores", action="store_true",
                    help="tabela de isovalores para o VESTA")
    args = ap.parse_args()

    pasta = Path(args.src).resolve()
    if args.arquivo:
        cubes = [pasta / args.arquivo]
    else:
        cubes = sorted(pasta.glob("excitonWavefunction-*.cube"))
    cubes = [c for c in cubes if c.is_file()]
    if not cubes:
        sys.exit(f"ERRO: nenhum excitonWavefunction-*.cube em {pasta}\n"
                 f"      Falta a tarefa 'excitonWavefunction' no <plan> e o bloco\n"
                 f"      <excitonPlot> no <xs>.")

    rede = leitura.vetores_de_rede(pasta)
    print()
    print(f"  {pasta}")
    print(f"  {leitura.titulo(pasta) or '?'}")

    for cube in cubes:
        rho, origem, passos, buraco_rede = le_cube(cube)
        dims = rho.shape
        print()
        print(f"  ── {cube.name} ──")
        if buraco_rede is None:
            print("  [!] o cabecalho nao traz a posicao fixa; sem <r>.")
            continue
        if rede is None:
            print("  [!] nao consegui ler os vetores de rede do input.xml; sem <r>.")
            continue

        fixo = buraco_rede @ rede
        eixos = [np.arange(d) for d in dims]
        g0, g1, g2 = np.meshgrid(*eixos, indexing="ij")
        pos = (origem[None, None, None, :]
               + g0[..., None] * passos[0]
               + g1[..., None] * passos[1]
               + g2[..., None] * passos[2])
        r = np.linalg.norm(pos - fixo, axis=-1) * BOHR_A

        peso = rho / rho.sum()
        r_med = float((peso * r).sum())
        r2 = float(np.sqrt((peso * r ** 2).sum()))
        print(f"  posicao fixa    : {buraco_rede} (coord. de rede)")
        print(f"  grade           : {dims[0]}×{dims[1]}×{dims[2]}"
              f"   ·   caixa ate {r.max():.2f} Å do centro")
        print(f"  <r>             : {r_med:.3f} Å")
        print(f"  sqrt(<r²>)      : {r2:.3f} Å")
        print(f"  máximo na grade : {rho.max():.4g}   ·   soma: {rho.sum():.4g}")
        print()
        print(f"  {'raio (Å)':>10} {'peso acumulado':>16}")
        for raio in args.raios:
            print(f"  {raio:>10.1f} {float(peso[r <= raio].sum()):>15.1%}")

        borda = np.zeros(dims, dtype=bool)
        borda[0, :, :] = borda[-1, :, :] = True
        borda[:, 0, :] = borda[:, -1, :] = True
        borda[:, :, 0] = borda[:, :, -1] = True
        fuga = float(peso[borda].sum())
        print()
        print(f"  densidade na borda da caixa: {fuga:.2%}")
        if fuga > 0.01:
            print("  [!] mais de 1% na borda - a supercelula e pequena demais para")
            print("      este exciton, e <r> esta SUBESTIMADO. Aumente o <box>.")
        else:
            print("  [ok] o exciton cabe na caixa.")

        if args.isovalores:
            tabela_isovalores(rho)
    print()


if __name__ == "__main__":
    main()
