#!/usr/bin/env python3
"""Eficiencia em funcao da espessura, com o programa de eficiencia_funcoes.py."""
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DADOS = Path(__file__).resolve().parent
RAIZ = DADOS.parent
exec((DADOS / "eficiencia_funcoes.py").read_text())

from scipy.interpolate import interp1d
from scipy.optimize import minimize_scalar

fonte = (DADOS / "eficiencia_principal.py").read_text()
exec(fonte[fonte.index("def minus_power"):fonte.index("fig, ax = plt.subplots")])

R = RAIZ / "runs"
FASES = {
    "pm3m": (R / "semana-08/CsSnBr3-pm3m-bse", R / "semana-08/CsSnBr3-pm3m-grupo-teste/3-pbe12-soc"),
    "i4mcm": (R / "semana-08/CsSnBr3-i4mcm-bse", R / "semana-08/CsSnBr3-i4mcm-pbe12-soc/pbe12-soc"),
    "p4mbm": (R / "semana-09/CsSnBr3-p4mbm-bse", R / "semana-08/CsSnBr3-p4mbm-pbe12-soc/pbe12-soc"),
    "gamma": (R / "semana-08/CsSnBr3-gamma-bse", R / "semana-08/CsSnBr3-gamma-pbe12-soc/pbe12-soc"),
    "r3c": (R / "semana-08/CsSnBr3-r3c-bse", R / "semana-08/CsSnBr3-r3c-pbe12-soc/pbe12-soc"),
}
if (R / "semana-09/CsSnBr3-delta-bse/EXCITON").exists():
    FASES["delta"] = (R / "semana-09/CsSnBr3-delta-bse", R / "semana-08/CsSnBr3-delta-pbe12-soc/pbe12-soc")

temperature = 300.0
kB_eV = sc.k / sc.e
extension = "OUT"
base_name_exciton = "EXCITON_BSE-singlet-TDA-BAR_SCR-full_OC"
DOUBLE_PASS = True
n_pass = 2.0 if DOUBLE_PASS else 1.0
E_sun, I_sun_E = get_sun_spectra()
P_in = np.trapezoid(I_sun_E, E_sun)
print(f"P_in = {P_in:.2f} W/m2")
direction = "11"
thicknesses = np.array([1, 5, 10, 50, 100, 500, 1000.0, 5000.0, 1e4])

fig, axes = plt.subplots(2, 3, figsize=(10, 6), sharex=True, sharey=True)
ax = axes.ravel()
print("fase | E_cutoff (eV) | E_g | E_g_da | f_r | largura (eV) | " + " | ".join(f"{t:g} nm" for t in thicknesses))
for i_phase, (phase, (bse, gs)) in enumerate(FASES.items()):
  filename = f"{bse}/EXCITON/{base_name_exciton}{direction}.{extension}"
  energy, oscillator_strength = np.loadtxt(filename, skiprows=14, usecols=(1, 3), max_rows=int(6e5), unpack=True)
  threshold = 1e-2 * np.max(oscillator_strength)
  idx = next(i for i, x in enumerate(oscillator_strength) if x > threshold)
  E_cutoff = energy[idx]
  E_bse, epsilon_real_average, epsilon_imag_average = get_dielectric_function(f"{bse}/EPSILON")
  E_g, E_g_da = obtain_gaps(f"{gs}/EIGVAL.OUT")
  f_r = np.exp((E_g - E_g_da) / (kB_eV * temperature))
  results = []
  for i_width, width in enumerate([0.05, 0.1, 0.2]):
    cutoff_function = smooth_cutoff(E_bse, E_cutoff, width=width)
    eps_im_filter = cutoff_function * epsilon_imag_average
    eps_re_filter = kkr_epsilon1(E_bse, eps_im_filter)
    alpha_nm = get_absorption_coefficient(E_bse, eps_re_filter, eps_im_filter)
    efficiencies = np.zeros_like(thicknesses, dtype=float)
    for i, thickness in enumerate(thicknesses):
      A_bse = 1.0 - np.exp(-n_pass * alpha_nm * thickness)
      A_of_E = interp1d(E_bse, A_bse, kind="linear", bounds_error=False, fill_value=0.0)
      E_min, E_max = E_bse.min(), E_bse.max()
      mask = (E_sun >= E_min) & (E_sun <= E_max)
      E_int = E_sun[mask]
      A_int = A_of_E(E_int)
      I_sun_int = I_sun_E[mask]
      J_sc = get_short_circuit_current(E_int, A_int, I_sun_int)
      J0_rad = get_radiative_reverse_saturation_current(E_bse, A_bse, temperature, 100)
      J_0 = J0_rad / f_r
      V_oc_approx = kB_eV * temperature * np.log(J_sc / J_0 + 1.0)
      res = minimize_scalar(minus_power, bounds=(1e-6, V_oc_approx), method="bounded",
                            args=(J_sc, J_0, temperature, kB_eV))
      efficiencies[i] = 100 * -res.fun / P_in
    print(f"{phase} | {E_cutoff:.4f} | {E_g:.4f} | {E_g_da:.4f} | {f_r:.3g} | {width} | "
          + " | ".join(f"{e:.2f}" for e in efficiencies))
    ls = '-' if i_width == 1 else ':' if i_width == 2 else '--'
    color = plt.get_cmap('tab10')(i_phase)
    ax[i_phase].plot(thicknesses, efficiencies, ls, label=f"w = {width} eV", color=color)
    results.append(efficiencies)
  ax[i_phase].fill_between(thicknesses, results[0], results[-1], alpha=0.2, color=color)
  ax[i_phase].set_xscale('log')
  ax[i_phase].set_xlim(1, 5e3)
  ax[i_phase].set_ylim(0, 40)
  ax[i_phase].legend(loc='upper left', title=phase, handlelength=1.5, fontsize=8)
for a in ax[len(FASES):]:
  a.set_visible(False)
for a in axes[-1]:
  a.set_xlabel("Espessura (nm)")
for a in ax[:len(FASES)]:
  a.xaxis.set_tick_params(labelbottom=True)
if len(FASES) <= 5:
  ax[2].set_xlabel("Espessura (nm)")
for a in axes[:, 0]:
  a.set_ylabel("Eficiência máxima (%)")
fig.tight_layout()
saida = DADOS / "figuras"
saida.mkdir(exist_ok=True)
fig.savefig(saida / "eficiencia-espessura.png", dpi=200)
