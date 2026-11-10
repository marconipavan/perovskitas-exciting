#!/usr/bin/env python3
"""Eficiencia maxima de uma celula solar (SLME) a partir de um calculo BSE."""
import argparse
from pathlib import Path

import numpy as np

import leitura

K_EV = 8.617333262e-5
H_EVS = 4.135667696e-15
C_M = 299792458.0
E_C = 1.602176634e-19
HC_EVNM = H_EVS * C_M * 1e9
AM15 = Path(__file__).resolve().parent / "dados" / "am1.5G.dat"
GRADE = np.arange(0.005, 12.0, 0.001)

try:
    integra = np.trapezoid
except AttributeError:
    integra = np.trapz


def sol():
    nm, irr = np.loadtxt(AM15, skiprows=2, usecols=(0, 1), unpack=True)
    energia = HC_EVNM / nm
    phi = irr * nm ** 2 / HC_EVNM / (energia * E_C)
    return energia[::-1], phi[::-1], integra(irr, nm)


def corpo_negro(energia, t):
    return 2 * energia ** 2 / (H_EVS ** 3 * C_M ** 2) / np.expm1(np.minimum(energia / (K_EV * t), 700.0))


def eficiencia(a_de_e, t=298.15, f_r=1.0):
    e_sol, phi, p_sun = sol()
    j_sc = E_C * integra(a_de_e(e_sol) * phi, e_sol)
    j_0 = E_C * np.pi * integra(a_de_e(GRADE) * corpo_negro(GRADE, t), GRADE) / f_r
    kt = K_EV * t
    v_oc = kt * np.log1p(j_sc / j_0)
    v = np.linspace(0.0, v_oc, 20001)
    j = j_sc - j_0 * np.expm1(np.minimum(v / kt, 700.0))
    p = j * v
    return p.max() / p_sun, j_sc / 10, v_oc, p.max() / (j_sc * v_oc), j_0 / 10


def alfa_medio(run, raiz2=True, direcao=None):
    arqs = sorted(Path(run).glob("EPSILON/EPSILON_*_OC[123][123].OUT"))
    arqs = [a for a in arqs if a.name[-8:-4] in ("OC11", "OC22", "OC33")]
    if len(arqs) == 3 and direcao:
        arqs = [a for a in arqs if a.name[-8:-4] == direcao]
    elif len(arqs) != 3:
        raise SystemExit(f"ERRO: {run}: esperava OC11, OC22 e OC33 em EPSILON/, achei {len(arqs)}")
    dados = [np.loadtxt(a, comments="#") for a in arqs]
    energia = dados[0][:, 0]
    eps1 = np.mean([d[:, leitura.COL_RE - 1] for d in dados], axis=0)
    eps2 = np.mean([d[:, leitura.COL_IM - 1] for d in dados], axis=0)
    dentro = np.maximum(np.hypot(eps1, eps2) - eps1, 0.0)
    if raiz2:
        dentro = dentro / 2
    return energia, 2 * energia * np.sqrt(dentro) / leitura.HBAR_C_EVCM


def absortividade(energia, alfa, l_um, corte=0.0, passagens=2):
    def a(e):
        valor = 1 - np.exp(-passagens * np.interp(e, energia, alfa) * l_um * 1e-4)
        return np.where(e >= corte, valor, 0.0)
    return a


def teste():
    print("Limite de Shockley-Queisser (degrau em E_g, 25 C, AM1.5G):")
    for e_g in (1.00, 1.15, 1.34, 1.50, 1.70, 2.00, 2.50):
        eta, j_sc, v_oc, ff, _ = eficiencia(lambda e: np.where(e >= e_g, 1.0, 0.0))
        print(f"  E_g {e_g:.2f} eV: eta {100 * eta:5.2f} %   J_sc {j_sc:5.2f} mA/cm2   V_oc {v_oc:.3f} V   FF {ff:.3f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src")
    ap.add_argument("--gap", type=float, help="gap minimo E_g [eV]")
    ap.add_argument("--dir", type=float, help="gap direto permitido [eV]; padrao: igual a E_g (f_r = 1)")
    ap.add_argument("--corte", type=float, default=0.0, help="zera a(E) abaixo desta energia [eV]")
    ap.add_argument("-L", type=float, nargs="+", default=[0.5, 1, 2, 5, 10], help="espessuras [um]")
    ap.add_argument("-T", type=float, default=298.15)
    ap.add_argument("--sem-raiz2", action="store_true", help="alpha sem o /2 na raiz")
    ap.add_argument("--teste", action="store_true")
    a = ap.parse_args()
    if a.teste:
        return teste()
    if not a.src or a.gap is None:
        ap.error("--src e --gap sao obrigatorios")
    f_r = np.exp(-((a.dir if a.dir is not None else a.gap) - a.gap) / (K_EV * a.T))
    energia, alfa = alfa_medio(a.src, not a.sem_raiz2)
    print(f"{a.src}: E_g {a.gap:.4f} eV, f_r {f_r:.3g}, corte {a.corte:.3f} eV")
    print("  L (um)   eta (%)   J_sc (mA/cm2)   V_oc (V)     FF   J_0 (mA/cm2)")
    for l_um in a.L:
        eta, j_sc, v_oc, ff, j_0 = eficiencia(absortividade(energia, alfa, l_um, a.corte), a.T, f_r)
        print(f"  {l_um:6.2f}   {100 * eta:7.2f}   {j_sc:13.2f}   {v_oc:8.3f}   {ff:.3f}   {j_0:.3e}")


if __name__ == "__main__":
    main()
