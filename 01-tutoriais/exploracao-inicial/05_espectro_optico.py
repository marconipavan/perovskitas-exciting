"""Espectro optico de perovskitas em diferentes niveis de teoria (DFT, GW, BSE)."""

import numpy as np
import matplotlib.pyplot as plt
from scipy.ndimage import gaussian_filter1d

Eg_DFT   = 1.10
Eg_GW    = 1.67
Eg_exp   = 1.60
Eb_exciton = 0.045

E = np.linspace(0.5, 3.5, 5000)
dE = E[1] - E[0]


def lorentziana(E, E0, gamma, A=1.0):
    return A * (gamma/2)**2 / ((E - E0)**2 + (gamma/2)**2)


def degrau_suave(E, E0, largura=0.04):
    return 0.5 * (1 + np.tanh((E - E0) / largura))


def raiz_suave(E, E0, escala=1.0):
    return escala * np.sqrt(np.maximum(E - E0, 0))


spec_DFT = degrau_suave(E, Eg_DFT, 0.05) + raiz_suave(E, Eg_DFT, 0.8)
spec_DFT = gaussian_filter1d(spec_DFT, sigma=8)

spec_GW = degrau_suave(E, Eg_GW, 0.05) + raiz_suave(E, Eg_GW, 0.8)
spec_GW = gaussian_filter1d(spec_GW, sigma=8)

spec_BSE = degrau_suave(E, Eg_GW, 0.05) + raiz_suave(E, Eg_GW, 0.6)
ns   = [1,    2,    3,    4]
amps = [1.8,  0.45, 0.15, 0.06]
gams = [0.02, 0.025, 0.03, 0.035]
for n, A, g in zip(ns, amps, gams):
    E_ex = Eg_GW - Eb_exciton / n**2
    spec_BSE += lorentziana(E, E_ex, g, A)
spec_BSE = gaussian_filter1d(spec_BSE, sigma=3)

spec_exp = degrau_suave(E, Eg_exp, 0.06) + raiz_suave(E, Eg_exp, 0.55)
spec_exp += lorentziana(E, Eg_exp - Eb_exciton, 0.025, 1.5)
spec_exp += lorentziana(E, Eg_exp - Eb_exciton/4, 0.030, 0.35)
spec_exp = gaussian_filter1d(spec_exp, sigma=4)
np.random.seed(42)
spec_exp += np.random.normal(0, 0.03, len(E))
spec_exp = gaussian_filter1d(spec_exp, sigma=5)

norm = spec_BSE.max()
spec_DFT /= norm; spec_GW /= norm
spec_BSE /= norm; spec_exp /= norm


fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle('Espectro óptico de MAPbI₃ - impacto do método de cálculo',
             fontsize=13, fontweight='bold')


def marca_gap(ax, E0, cor, label):
    ax.axvline(E0, color=cor, lw=1.5, ls='--', alpha=0.7)
    ax.text(E0+0.03, 0.05, label, color=cor, fontsize=8,
            rotation=90, va='bottom')


ax = axes[0, 0]
ax.fill_between(E, spec_DFT, alpha=0.3, color='#E63946')
ax.plot(E, spec_DFT, '#E63946', lw=2, label='DFT (LDA)')
marca_gap(ax, Eg_DFT, '#E63946', f'Gap DFT = {Eg_DFT:.2f} eV')
marca_gap(ax, Eg_exp, 'black',   f'Gap exp. = {Eg_exp:.2f} eV')
ax.set_title('1. DFT padrão\n(gap subestimado, sem éxcitons)', fontsize=10)
ax.legend(fontsize=9); ax.grid(alpha=0.2)
ax.set_ylabel('ε₂(ω) - absorção (u.a.)', fontsize=9)
ax.set_xlim(0.7, 3.0); ax.set_ylim(-0.05, 1.5)
ax.annotate('Gap errado!\n(subestimado ~0.5 eV)', xy=(Eg_DFT, 0.8),
            xytext=(0.3, 1.1), fontsize=8, color='#E63946',
            arrowprops=dict(arrowstyle='->', color='#E63946'))

ax = axes[0, 1]
ax.fill_between(E, spec_GW, alpha=0.3, color='#F4A261')
ax.plot(E, spec_GW, '#F4A261', lw=2, label='GW')
ax.plot(E, spec_DFT, '#E63946', lw=1.5, ls='--', alpha=0.5, label='DFT (ref.)')
marca_gap(ax, Eg_GW, '#F4A261', f'Gap GW = {Eg_GW:.2f} eV')
marca_gap(ax, Eg_exp, 'black', f'Gap exp. = {Eg_exp:.2f} eV')
ax.set_title('2. Correção GW\n(gap correto, ainda sem éxcitons)', fontsize=10)
ax.legend(fontsize=9); ax.grid(alpha=0.2)
ax.set_xlim(0.7, 3.0); ax.set_ylim(-0.05, 1.5)
ax.annotate('Gap corrigido!\nMas sem picos excitônicos', xy=(Eg_GW+0.05, 0.6),
            xytext=(2.2, 1.1), fontsize=8, color='#F4A261',
            arrowprops=dict(arrowstyle='->', color='#F4A261'))

ax = axes[1, 0]
ax.fill_between(E, spec_BSE, alpha=0.3, color='#457B9D')
ax.plot(E, spec_BSE, '#457B9D', lw=2, label='GW + BSE')
ax.plot(E, spec_GW, '#F4A261', lw=1.5, ls='--', alpha=0.5, label='GW (ref.)')
marca_gap(ax, Eg_GW, '#F4A261', f'Gap GW = {Eg_GW:.2f} eV')
for n in [1, 2, 3]:
    E_ex = Eg_GW - Eb_exciton / n**2
    ax.axvline(E_ex, color='#2A9D8F', lw=1, ls=':', alpha=0.8)
    ax.text(E_ex-0.02, 1.3, f'n={n}', fontsize=8, ha='right', color='#2A9D8F')
ax.annotate(f'Éxciton 1s\nEb = {Eb_exciton*1000:.0f} meV',
            xy=(Eg_GW - Eb_exciton, 1.6),
            xytext=(0.9, 1.25), fontsize=8, color='#457B9D',
            arrowprops=dict(arrowstyle='->', color='#457B9D'))
ax.set_title('3. GW + BSE\n(gap correto + éxcitons)', fontsize=10)
ax.legend(fontsize=9); ax.grid(alpha=0.2)
ax.set_ylabel('ε₂(ω) - absorção (u.a.)', fontsize=9)
ax.set_xlabel('Energia (eV)', fontsize=10)
ax.set_xlim(0.7, 3.0); ax.set_ylim(-0.05, 1.8)

ax = axes[1, 1]
ax.plot(E, spec_exp,  'black',   lw=1.5, alpha=0.7,
        label='Experimental (esquemático)')
ax.plot(E, spec_BSE,  '#457B9D', lw=2.5,
        label='GW + BSE (calculado)')
ax.plot(E, spec_GW,   '#F4A261', lw=1.5, ls='--', alpha=0.6,
        label='GW (sem éxcitons)')
ax.plot(E, spec_DFT,  '#E63946', lw=1.5, ls=':',  alpha=0.5,
        label='DFT')
ax.set_title('4. Comparação: todos os métodos', fontsize=10)
ax.legend(fontsize=8.5); ax.grid(alpha=0.2)
ax.set_xlabel('Energia (eV)', fontsize=10)
ax.set_xlim(0.7, 3.0); ax.set_ylim(-0.1, 1.8)

resumo = (
    "Resumo da hierarquia de métodos:\n"
    "DFT  -> gap errado (~0.5 eV abaixo)\n"
    "GW   -> gap correto, sem éxcitons\n"
    "BSE  -> gap correto + picos excitônicos"
)
ax.text(0.97, 0.97, resumo, transform=ax.transAxes,
        fontsize=7.5, va='top', ha='right',
        bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

plt.tight_layout()
plt.savefig('05_espectro_optico.png', dpi=150, bbox_inches='tight')
plt.show()
print("Figura salva: 05_espectro_optico.png")
