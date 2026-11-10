#!/usr/bin/env python3
"""Mostra o resultado principal de um calculo do exciting."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import leitura

HARTREE_EV = leitura.HARTREE_EV


def mostra_gs(d, pasta):
    print(f"  {pasta}")
    print(f"  nivel de teoria : {leitura.nivel_de_teoria(pasta)}")
    for arquivo, cut, ion in leitura.r_cut_todos(pasta):
        extra = f", ionizacao {ion}" if ion else ""
        print(f"  r_cut           : {cut} bohr  (em {arquivo}{extra})")
    print()

    if not d["convergiu"]:
        print("  [!] o SCF NAO reportou 'Convergence targets achieved' - o resultado")
        print("      abaixo pode ser de um calculo que parou no limite de iteracoes.")
        print()

    if d["gap_ev"] is None:
        print("  gap             : nao reportado no INFO.OUT")
    else:
        print(f"  GAP             : {d['gap_ev']:.4f} eV   ({d['gap_ha']:.8f} Ha)")
        if d["vbm"] is not None:
            print(f"                    {'DIRETO' if d['direto'] else 'INDIRETO'}"
                  f"{'' if d['direto'] else '  (leva * na tabela)'}")
            print(f"  topo da valencia: k {d['kv']:>4}   {d['vbm']}")
            print(f"  fundo da conduc.: k {d['kc']:>4}   {d['cbm']}")
        if d["gap_ev"] < 1e-3:
            print()
            print("  [!] gap praticamente zero. Se o material devia ser semicondutor,")
            print("      suspeite de 'nempty' pequeno demais antes de suspeitar da fisica.")
    print()
    if d["etot"] is not None:
        por_atomo = (f"  = {d['etot_por_atomo']:.6f} Ha/atomo ({d['natomos']} atomos)"
                     if d["etot_por_atomo"] else "")
        print(f"  energia total   : {d['etot']:.8f} Ha{por_atomo}")
    if d["fermi"] is not None:
        print(f"  energia de Fermi: {d['fermi']:.8f} Ha = {d['fermi'] * HARTREE_EV:.4f} eV")
    if d["nk"]:
        print(f"  pontos k        : {d['nk']:.0f}")
    print(f"  iteracoes SCF   : {d['iteracoes']}")
    if d["tempo"]:
        t = d["tempo"]
        print(f"  tempo           : {t:.1f} s" + (f" = {t / 60:.1f} min" if t > 90 else ""))


def mostra_bse(pasta):
    exc = leitura.exciton(pasta)
    if exc is None:
        print("  [!] pasta de BSE sem EXCITON/ - o calculo nao chegou ao fim,")
        print("      ou a task 'bse' nao estava no <plan>.")
        return
    i = leitura.brilhante(exc)
    print()
    print("  ── BSE ─────────────────────────────────────────────────────")
    print(f"  arquivo         : {exc['arquivo'].parent.name}/{exc['arquivo'].name}")
    print(f"  solucoes BSE    : {len(exc['nr'])}")
    if exc["e_shift"] is not None:
        print(f"  E_shift (=-gap) : {exc['e_shift']:.4f} eV")
    print()
    if i is None:
        print("  [!] nenhum exciton com forca de oscilador acima do limiar.")
    else:
        escuras = i
        print(f"  1a EXCITACAO BRILHANTE  (#{exc['nr'][i]}"
              + (f", apos {escuras} estado(s) escuro(s))" if escuras else ")"))
        print(f"    energia       : {exc['energia'][i]:.4f} eV")
        lig = exc["ligacao"][i]
        print(f"    ENERGIA DE LIGACAO: {lig:.4f} eV"
              + ("   (negativa -> exciton LIGADO)" if lig < 0 else
                 "   [!] positiva -> NAO ligado"))
        print(f"    forca de oscil.: {exc['osc'][i]:.4e}")
        if exc["fator_osc"]:
            print(f"    |t_lambda|^2   : {exc['osc'][i] * exc['fator_osc']:.4e}")
            print(f"                     (fator {exc['fator_osc']:.2f} = V*nk/"
                  f"{'4pi' if exc['tevecsv'] else '8pi'}; segunda variacao: "
                  f"{'SIM' if exc['tevecsv'] else 'nao'} - {exc['tevecsv_motivo']})")
    print()
    eps = leitura.eps_estatico(pasta)
    if eps is not None:
        print(f"  eps_inf (BSE)   : {eps:.4f}")
    dt = leitura.dieltens(pasta)
    if dt:
        print(f"  DIELTENS (RPA)  : {dt[0]:.4f}  {dt[1]:.4f}  {dt[2]:.4f}")
    a = leitura.absorcao(pasta)
    if a is not None:
        import numpy as np
        j = int(np.argmax(a[1]))
        print(f"  pico de alpha   : {a[1][j]:.3e} cm^-1 em {a[0][j]:.2f} eV")
    if exc.get("nk"):
        print(f"  pontos k (xs)   : {exc['nk']}   volume: {exc.get('volume', 0):.2f} au")


def linha_gaps(d, pasta, rotulo):
    estrela = "" if d["direto"] in (True, None) else "*"
    rcs = leitura.r_cut_todos(pasta)
    corte = ""
    if rcs:
        corte = "   ·   " + " · ".join(
            f"r_cut({Path(arq).stem}) = {cut}" for arq, cut, _ in rcs if cut)
    print()
    print("  para a TABELA-GAPS.md:")
    print(f"    {rotulo or leitura.nivel_de_teoria(pasta)} = "
          f"**{d['gap_ev']:.2f}{estrela}** eV" + corte)


def linha_bse(pasta, rotulo):
    exc = leitura.exciton(pasta)
    if exc is None:
        return
    i = leitura.brilhante(exc)
    if i is None:
        return
    eps = leitura.eps_estatico(pasta)
    print()
    print("  para a TABELA-BSE.md:")
    print(f"    {rotulo or leitura.titulo(pasta) or pasta.name}:")
    print(f"    E1 = **{exc['energia'][i]:.3f}** eV   ·   "
          f"E_b = **{exc['ligacao'][i]:.3f}** eV   ·   "
          f"osc = {exc['osc'][i]:.3e}"
          + (f"   ·   eps_inf = {eps:.3f}" if eps is not None else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-s", "--src", default=".", help="pasta do calculo (default: atual)")
    ap.add_argument("-l", "--linha", nargs="?", const="", default=None, metavar="ROTULO",
                    help="imprime tambem a linha pronta para a tabela")
    args = ap.parse_args()

    pasta = Path(args.src).resolve()
    if not pasta.is_dir():
        sys.exit(f"ERRO: pasta nao existe: {pasta}")

    d = leitura.info(pasta)
    e_bse = leitura.arquivo_exciton(pasta) is not None
    if d is None and not e_bse:
        sys.exit(f"ERRO: nao ha INFO.OUT nem EXCITON/ em {pasta}\n"
                 f"      O calculo ainda nao rodou, ou rodou em outra pasta.")

    print()
    if d is not None:
        mostra_gs(d, pasta)
    else:
        print(f"  {pasta}")
        print(f"  nivel de teoria : {leitura.nivel_de_teoria(pasta)}")
    if leitura.tipo_de_calculo(pasta).startswith(("BSE", "fastBSE")) or e_bse:
        mostra_bse(pasta)

    if d is not None and d["avisos"]:
        print()
        print("  avisos do exciting:")
        for linha in d["avisos"].splitlines():
            if linha.strip():
                print(f"    {linha.strip()}")

    if args.linha is not None:
        if d is not None and d["gap_ev"] is not None:
            linha_gaps(d, pasta, args.linha)
        if e_bse:
            linha_bse(pasta, args.linha)
    print()


if __name__ == "__main__":
    main()
