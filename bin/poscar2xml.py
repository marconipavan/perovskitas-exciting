#!/usr/bin/env python3
"""Converte um POSCAR no bloco structure do input.xml do exciting."""
import argparse
import sys
from pathlib import Path

import numpy as np

ANGSTROM_BOHR = 1.889725989
FORMATO = "15.10f"
IDENT = " " * 2


def poscar_to_dict(fname: str) -> dict:
    with open(fname, 'r') as f:
        lines = f.readlines()

    offset = 1
    scale_factor = float(lines[offset].split()[0].strip())

    offset += 1
    a = np.zeros((3, 3))
    for i in range(3):
        a[i, :] = [float(x) for x in lines[offset + i].split()]

    offset += 3
    species = lines[offset].split()
    if any(campo.lstrip("-").isdigit() for campo in species):
        sys.exit("ERRO: a linha das especies traz numeros. Este POSCAR parece ser do\n"
                 "      VASP 4, sem os nomes dos elementos. Acrescente a linha com os\n"
                 "      simbolos (ex.: 'Cs Sn Br') antes das quantidades.")

    offset += 1
    number_of_atoms = [int(x) for x in lines[offset].split()]
    assert len(species) == len(number_of_atoms)

    offset += 1
    coord_type = lines[offset].strip().lower()
    if coord_type.startswith("s"):
        offset += 1
        coord_type = lines[offset].strip().lower()
    if not coord_type.startswith("d"):
        sys.exit(f"ERRO: o POSCAR esta em '{lines[offset].strip()}', e o conversor so\n"
                 f"      trata coordenadas diretas (fracionarias).")

    offset += 1
    coords = np.zeros((sum(number_of_atoms), 3))
    for i in range(sum(number_of_atoms)):
        coords[i, :] = [float(x) for x in lines[offset + i].split()[:3]]

    return {
        'scale_factor': scale_factor,
        'lattice_vectors': a,
        'species': species,
        'number_of_atoms': number_of_atoms,
        'coordinates': coords
    }


def dict_to_xml(poscar_data: dict, rmt: dict = None, dfthalf: dict = None) -> str:
    xml_str = IDENT + '<structure speciespath="./">\n'
    xml_str += IDENT * 2 + f'<crystal scale="{ANGSTROM_BOHR * poscar_data["scale_factor"]}">\n'

    a = poscar_data["lattice_vectors"]
    for i in range(3):
        xml_str += (IDENT * 3 + f'<basevect>{a[i][0]:{FORMATO}} {a[i][1]:{FORMATO}} '
                    f'{a[i][2]:{FORMATO}}</basevect>\n')
    xml_str += IDENT * 2 + '</crystal>\n'

    inicio = 0
    for specie, num in zip(poscar_data["species"], poscar_data["number_of_atoms"]):
        if rmt is None:
            attr_rmt = ""
        else:
            attr_rmt = f' rmt="{rmt.get(specie, f"defineHere{specie}")}"'
        xml_str += IDENT * 2 + f'<species speciesfile="{specie}.xml"{attr_rmt}>\n'
        for coord in poscar_data["coordinates"][inicio:inicio + num]:
            xml_str += (IDENT * 3 + f'<atom coord="{coord[0]:{FORMATO}} '
                        f'{coord[1]:{FORMATO}} {coord[2]:{FORMATO}}"/>\n')
        if dfthalf and specie in dfthalf:
            d = dfthalf[specie]
            xml_str += (IDENT * 3 + f'<dfthalfparam cut="{d["cut"]}" '
                        f'ampl="{d.get("ampl", "1")}" '
                        f'exponent="{d.get("exponent", "8")}">\n')
            xml_str += (IDENT * 4 + f'<shell number="{d.get("number", "0")}" '
                        f'ionization="{d["ionization"]}"/>\n')
            xml_str += IDENT * 3 + '</dfthalfparam>\n'
        xml_str += IDENT * 2 + '</species>\n'
        inicio += num

    xml_str += IDENT + '</structure>\n'
    return xml_str


def le_rmt(texto):
    saida = {}
    for par in texto.split(","):
        par = par.strip()
        if not par:
            continue
        if "=" not in par:
            sys.exit(f"ERRO: --rmt espera ESPECIE=VALOR, veio '{par}'")
        especie, valor = par.split("=", 1)
        saida[especie.strip()] = valor.strip()
    return saida


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("poscar", nargs="?", default="POSCAR", help="arquivo POSCAR (default: ./POSCAR)")
    ap.add_argument("-o", "--out", help="grava neste arquivo em vez de imprimir")
    ap.add_argument("--rmt", default="", metavar="ESPECIE=VALOR,...",
                    help="raios de muffin-tin; sem isso fica o marcador defineHere<Especie>")
    ap.add_argument("--sem-rmt", dest="sem_rmt", action="store_true",
                    help="nao escreve o atributo rmt: o exciting usa o do arquivo de especie")
    args = ap.parse_args()

    caminho = Path(args.poscar)
    if caminho.is_dir():
        caminho = caminho / "POSCAR"
    if not caminho.is_file():
        sys.exit(f"ERRO: nao encontrei {caminho}")

    dados = poscar_to_dict(str(caminho))
    xml = dict_to_xml(dados, None if args.sem_rmt else le_rmt(args.rmt))

    if args.out:
        Path(args.out).write_text(xml)
        print(f"{caminho} -> {args.out}")
    else:
        print(xml)

    faltam = [] if args.sem_rmt else [e for e in dados["species"] if e not in le_rmt(args.rmt)]
    formula = " ".join(f"{e}{n}" for e, n in zip(dados["species"], dados["number_of_atoms"]))
    print(f"\n{formula}, {sum(dados['number_of_atoms'])} atomos, "
          f"scale = {ANGSTROM_BOHR * dados['scale_factor']:.6f} bohr", file=sys.stderr)
    if faltam:
        print(f"Falta definir o rmt de: {', '.join(faltam)}  "
              f"(marcados como defineHere<Especie>)", file=sys.stderr)
    print("Copie tambem os arquivos de especie para a pasta: "
          f"{' '.join(e + '.xml' for e in dados['species'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
