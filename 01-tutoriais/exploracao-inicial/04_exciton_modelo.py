"""Modelo de Wannier-Mott para excitons em perovskitas."""

import numpy as np
import matplotlib.pyplot as plt
from scipy.special import genlaguerre, factorial

e    = 1.602e-19
eps0 = 8.854e-12
hbar = 1.055e-34
m0   = 9.109e-31
eV   = 1.602e-19


def energia_ligacao(eps_r, mu_r):
    Ry = 13.6
    return Ry * mu_r / eps_r**2


def raio_bohr_exciton(eps_r, mu_r):
    a0 = 0.0529
    return a0 * eps_r / mu_r


def niveis_energia(Eb, n_max=5):
    ns = np.arange(1, n_max + 1)
    return ns, -Eb / ns**2


def funcao_onda_1s(r, a_X):
    return 2 / a_X**1.5 * np.exp(-r / a_X)


def funcao_onda_2s(r, a_X):
    return (1 / (2*np.sqrt(2))) * (2*a_X)**(-1.5) * (2 - r/a_X) * np.exp(-r/(2*a_X))


def funcao_onda_2p(r, a_X):
    return (1 / (2*np.sqrt(6))) * (2*a_X)**(-1.5) * (r/a_X) * np.exp(-r/(2*a_X))


materiais = {
    'MAPbI₃':  {'eps_r': 25.0, 'mu_r': 0.15, 'Eg': 1.60},
    'CsPbBr₃': {'eps_r': 7.3,  'mu_r': 0.12, 'Eg': 2.25},
    'CsPbCl₃': {'eps_r': 5.5,  'mu_r': 0.18, 'Eg': 3.00},
    'GaAs\n(ref)': {'eps_r': 12.9, 'mu_r': 0.058, 'Eg': 1.42},
}


fig = plt.figure(figsize=(16, 10))
fig.suptitle('Modelo de Wannier-Mott para éxcitons em perovskitas',
             fontsize=13, fontweight='bold')

gs = fig.add_gridspec(2, 3, hspace=0.38, wspace=0.35)
ax1 = fig.add_subplot(gs[0, 0])
ax2 = fig.add_subplot(gs[0, 1])
ax3 = fig.add_subplot(gs[0, 2])
ax4 = fig.add_subplot(gs[1, :])

cores = ['#E63946', '#457B9D', '#2A9D8F', '#F4A261']

ax1.set_title('Níveis excitônicos (análogo H)', fontsize=10)

for idx, (nome, params) in enumerate(materiais.items()):
    Eb = energia_ligacao(params['eps_r'], params['mu_r'])
    Eg = params['Eg']
    ns, En = niveis_energia(Eb, n_max=4)

    x_off = idx * 0.8
    cor = cores[idx]

    ax1.axhline(Eg, xmin=x_off/3.5, xmax=(x_off+0.6)/3.5,
                color=cor, lw=2, alpha=0.5)

    for n, e_n in zip(ns, En):
        e_abs = Eg + e_n
        ax1.plot([x_off, x_off+0.6], [e_abs, e_abs],
                 color=cor, lw=1.5, alpha=0.9)
        if n <= 3:
            ax1.text(x_off+0.62, e_abs, f'n={n}', fontsize=6.5,
                     va='center', color=cor)

    ax1.text(x_off+0.3, Eg-0.25, nome.replace('\n(ref)', '\n(ref.)'),
             ha='center', fontsize=7.5, color=cor, fontweight='bold')
    ax1.text(x_off+0.3, Eg+0.08,
             f'Eb={Eb*1000:.0f} meV', ha='center', fontsize=6.5, color=cor)

ax1.set_ylabel('Energia (eV)', fontsize=10)
ax1.set_xlim(-0.2, 3.5)
ax1.set_xticks([])
ax1.grid(axis='y', alpha=0.2)
ax1.set_ylim(1.0, 3.5)

ax2.set_title('Funções de onda radiais (CsPbBr₃)', fontsize=10)

params_ex = materiais['CsPbBr₃']
Eb_ex = energia_ligacao(params_ex['eps_r'], params_ex['mu_r'])
aX = raio_bohr_exciton(params_ex['eps_r'], params_ex['mu_r'])

r = np.linspace(0, 15*aX, 500)
psi_1s = funcao_onda_1s(r, aX)
psi_2s = funcao_onda_2s(r, aX)
psi_2p = funcao_onda_2p(r, aX)

ax2.plot(r/aX, r**2 * psi_1s**2, '#E63946', lw=2, label='1s')
ax2.plot(r/aX, r**2 * psi_2s**2, '#457B9D', lw=2, label='2s')
ax2.plot(r/aX, r**2 * psi_2p**2, '#2A9D8F', lw=2, label='2p')
ax2.axvline(1, color='gray', ls=':', lw=1, alpha=0.7, label=f'r = aₓ = {aX:.1f} nm')

ax2.set_xlabel('r / aₓ (raios de Bohr excitônicos)', fontsize=9)
ax2.set_ylabel('r²|ψ(r)|² (densidade radial)', fontsize=9)
ax2.legend(fontsize=8)
ax2.grid(alpha=0.2)
ax2.set_xlim(0, 10)

ax3.set_title('Eb × constante dielétrica', fontsize=10)

eps_range = np.linspace(3, 30, 200)
for mu_r, label, cor in [(0.10, 'μ* = 0.10 m₀', '#E63946'),
                          (0.15, 'μ* = 0.15 m₀', '#457B9D'),
                          (0.20, 'μ* = 0.20 m₀', '#2A9D8F')]:
    Eb_range = energia_ligacao(eps_range, mu_r) * 1000
    ax3.plot(eps_range, Eb_range, lw=2, color=cor, label=label)

for idx, (nome, params) in enumerate(materiais.items()):
    Eb = energia_ligacao(params['eps_r'], params['mu_r']) * 1000
    ax3.scatter(params['eps_r'], Eb, s=80, color=cores[idx],
                zorder=5, edgecolor='black', linewidth=0.8)
    ax3.annotate(nome.replace('\n(ref)', ''),
                 (params['eps_r'], Eb),
                 xytext=(5, 5), textcoords='offset points',
                 fontsize=7, color=cores[idx])

ax3.set_xlabel('Constante dielétrica εᵣ', fontsize=9)
ax3.set_ylabel('Energia de ligação Eb (meV)', fontsize=9)
ax3.legend(fontsize=7.5)
ax3.grid(alpha=0.2)
ax3.set_yscale('log')

ax4.set_title('Espectros de absorção esquemáticos - com e sem éxcitons', fontsize=11)

def espectro_com_excitons(E, Eg, Eb, broadening=0.02):
    spec = np.zeros_like(E)
    ns = [1, 2, 3, 4]
    forca_osc = [1.0, 0.25, 0.10, 0.05]
    for n, f in zip(ns, forca_osc):
        E_ex = Eg - Eb / n**2
        spec += f / n**3 * np.exp(-((E - E_ex)**2) / (2*broadening**2))
    spec += 0.3 * (1 + np.tanh((E - Eg) / broadening)) * (1 + 0.5*np.sqrt(np.maximum(E-Eg, 0)))
    return spec

def espectro_sem_excitons(E, Eg, broadening=0.02):
    spec = 0.5 * (1 + np.tanh((E - Eg) / broadening))
    spec += 0.5 * np.sqrt(np.maximum(E - Eg, 0))
    return spec

E = np.linspace(1.3, 2.6, 2000)

for idx, (nome, params) in enumerate(list(materiais.items())[:3]):
    Eb = energia_ligacao(params['eps_r'], params['mu_r'])
    Eg = params['Eg']
    cor = cores[idx]
    x_off = idx * 0.45

    spec_ex  = espectro_com_excitons(E, Eg, Eb)
    spec_no  = espectro_sem_excitons(E, Eg)

    norm = max(spec_ex.max(), spec_no.max())

    ax4.plot(E, spec_ex/norm  + x_off, color=cor, lw=2,
             label=f'{nome} (com éxcitons)')
    ax4.plot(E, spec_no/norm  + x_off, color=cor, lw=1.5,
             ls='--', alpha=0.5, label=f'{nome} (sem éxcitons)')

    ax4.axvline(Eg, color=cor, lw=0.8, ls=':', alpha=0.6)
    ax4.text(Eg+0.02, x_off+0.85, f'Eg={Eg:.2f}eV', fontsize=7.5, color=cor)

    E1 = Eg - Eb
    ax4.axvline(E1, color=cor, lw=0.8, ls='-.', alpha=0.4)
    ax4.text(E1-0.04, x_off+0.7, f'n=1\nEb={Eb*1000:.0f}meV',
             fontsize=6.5, ha='right', color=cor)

ax4.set_xlabel('Energia (eV)', fontsize=11)
ax4.set_ylabel('Absorção (u.a., deslocada)', fontsize=11)
ax4.legend(fontsize=7.5, ncol=2, loc='upper left')
ax4.grid(alpha=0.2)
ax4.set_xlim(1.3, 2.6)

from matplotlib.lines import Line2D
leg_extra = [
    Line2D([0],[0], color='black', lw=2,    label='Com éxcitons (BSE)'),
    Line2D([0],[0], color='black', lw=1.5, ls='--', alpha=0.5,
           label='Sem éxcitons (DFT/GW)'),
]
ax4.legend(handles=leg_extra, fontsize=9, loc='upper right')

plt.savefig('04_exciton_modelo.png', dpi=150, bbox_inches='tight')
plt.show()
print("Figura salva: 04_exciton_modelo.png")
print(f"\nTabela de propriedades excitônicas:")
print(f"{'Material':15} {'εᵣ':>6} {'μ*':>6} {'Eb (meV)':>10} {'aₓ (nm)':>10}")
print("-" * 52)
for nome, p in materiais.items():
    Eb = energia_ligacao(p['eps_r'], p['mu_r']) * 1000
    aX = raio_bohr_exciton(p['eps_r'], p['mu_r'])
    print(f"{nome:15} {p['eps_r']:>6.1f} {p['mu_r']:>6.3f} {Eb:>10.1f} {aX:>10.2f}")
