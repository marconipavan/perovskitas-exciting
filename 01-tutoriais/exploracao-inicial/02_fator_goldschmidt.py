"""Calcula o fator de tolerancia de Goldschmidt para perovskitas de haleto."""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

r_A = {
    'Cs⁺':  1.88,
    'FA⁺':  2.53,
    'MA⁺':  2.17,
    'Rb⁺':  1.72,
    'K⁺':   1.64,
}

r_B = {
    'Pb²⁺': 1.19,
    'Sn²⁺': 1.10,
    'Ge²⁺': 0.73,
    'Bi³⁺': 1.03,
}

r_X = {
    'I⁻':  2.20,
    'Br⁻': 1.96,
    'Cl⁻': 1.81,
}


def goldschmidt(rA, rB, rX):
    return (rA + rX) / (np.sqrt(2) * (rB + rX))


fig, axes = plt.subplots(1, 2, figsize=(14, 6))
fig.suptitle('Fator de Tolerância de Goldschmidt - Perovskitas de Haleto',
             fontsize=13, fontweight='bold')

ax = axes[0]
ax.set_title('B = Pb²⁺, variando A e X', fontsize=11)

cores_X = {'I⁻': '#E63946', 'Br⁻': '#2A9D8F', 'Cl⁻': '#F4A261'}
marcadores_A = {'Cs⁺': 'o', 'FA⁺': 's', 'MA⁺': '^', 'Rb⁺': 'D', 'K⁺': 'v'}

for nome_X, rX in r_X.items():
    ts = []
    labels = []
    for nome_A, rA in r_A.items():
        t = goldschmidt(rA, r_B['Pb²⁺'], rX)
        ts.append(t)
        labels.append(nome_A)
        ax.scatter(nome_A, t, color=cores_X[nome_X],
                   marker=marcadores_A[nome_A], s=120, zorder=3)
    ax.plot(list(r_A.keys()), ts, color=cores_X[nome_X],
            alpha=0.5, lw=1.5, label=f'X = {nome_X}')

ax.axhspan(0.9, 1.0, alpha=0.12, color='green', label='Cúbica ideal (0.9-1.0)')
ax.axhspan(0.71, 0.9, alpha=0.08, color='blue', label='Distorcida (0.71-0.9)')
ax.axhline(1.0, color='green', lw=1, ls='--', alpha=0.5)
ax.axhline(0.9, color='blue', lw=1, ls='--', alpha=0.5)
ax.axhline(0.71, color='red', lw=1, ls='--', alpha=0.5)

ax.set_ylabel('Fator de tolerância t', fontsize=11)
ax.set_xlabel('Cátion A', fontsize=11)
ax.set_ylim(0.6, 1.15)
ax.legend(fontsize=8, loc='upper right')
ax.grid(axis='y', alpha=0.3)

ax.annotate('Cúbica', xy=(0.02, 0.96), xycoords=('axes fraction', 'data'),
            fontsize=8, color='green', alpha=0.8)
ax.annotate('Distorcida', xy=(0.02, 0.80), xycoords=('axes fraction', 'data'),
            fontsize=8, color='blue', alpha=0.8)
ax.annotate('Instável', xy=(0.02, 0.68), xycoords=('axes fraction', 'data'),
            fontsize=8, color='red', alpha=0.8)

ax2 = axes[1]
ax2.set_title('Mapa de estabilidade: rA × rB (X = I⁻)', fontsize=11)

rA_vals = np.linspace(1.5, 2.8, 300)
rB_vals = np.linspace(0.6, 1.4, 300)
RA, RB = np.meshgrid(rA_vals, rB_vals)
T = goldschmidt(RA, RB, r_X['I⁻'])

niveis = [0.71, 0.9, 1.0, 1.1]
cores_mapa = ['#E63946', '#A8DADC', '#457B9D', '#1D3557']

cf = ax2.contourf(RA, RB, T, levels=[0, 0.71, 0.9, 1.0, 1.15],
                  colors=['#FFCCD5', '#A8DADC', '#457B9D', '#1D3557'],
                  alpha=0.6)
ax2.contour(RA, RB, T, levels=niveis, colors='white', linewidths=1.2, alpha=0.7)

materiais = {
    'CsPbI₃':  (r_A['Cs⁺'],  r_B['Pb²⁺']),
    'MAPbI₃':  (r_A['MA⁺'],  r_B['Pb²⁺']),
    'FAPbI₃':  (r_A['FA⁺'],  r_B['Pb²⁺']),
    'CsSnI₃':  (r_A['Cs⁺'],  r_B['Sn²⁺']),
    'MASnI₃':  (r_A['MA⁺'],  r_B['Sn²⁺']),
    'CsGeI₃':  (r_A['Cs⁺'],  r_B['Ge²⁺']),
}
for nome, (rA, rB) in materiais.items():
    ax2.scatter(rA, rB, s=80, color='white', edgecolor='black',
                zorder=5, linewidth=1.2)
    ax2.annotate(nome, (rA, rB), textcoords='offset points',
                 xytext=(5, 5), fontsize=7.5, color='white',
                 fontweight='bold')

ax2.set_xlabel('Raio iônico de A (Å)', fontsize=11)
ax2.set_ylabel('Raio iônico de B (Å)', fontsize=11)

patches = [
    mpatches.Patch(color='#FFCCD5', alpha=0.6, label='t < 0.71 - Instável'),
    mpatches.Patch(color='#A8DADC', alpha=0.6, label='0.71-0.9 - Distorcida'),
    mpatches.Patch(color='#457B9D', alpha=0.6, label='0.9-1.0 - Cúbica'),
    mpatches.Patch(color='#1D3557', alpha=0.6, label='t > 1.0 - Hexagonal'),
]
ax2.legend(handles=patches, fontsize=8, loc='upper left')

plt.tight_layout()
plt.savefig('02_fator_goldschmidt.png', dpi=150, bbox_inches='tight')
plt.show()
print("Figura salva: 02_fator_goldschmidt.png")
