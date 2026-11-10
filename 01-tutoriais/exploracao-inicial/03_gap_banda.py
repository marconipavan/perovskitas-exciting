"""Mostra o gap de CsPbX3 em funcao do haleto X."""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from scipy.interpolate import CubicSpline

gaps_puros = {
    'CsPbI₃':  1.73,
    'CsPbBr₃': 2.25,
    'CsPbCl₃': 3.00,
}

x_exp = np.array([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
gap_exp = np.array([1.73, 1.82, 1.95, 2.08, 2.17, 2.25])

cs = CubicSpline(x_exp, gap_exp)
x_cont = np.linspace(0, 1, 300)
gap_cont = cs(x_cont)

y_exp = np.array([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
gap_exp2 = np.array([2.25, 2.42, 2.58, 2.73, 2.87, 3.00])
cs2 = CubicSpline(y_exp, gap_exp2)
y_cont = np.linspace(0, 1, 300)
gap_cont2 = cs2(y_cont)

def eV_para_nm(eV):
    return 1240 / eV

def cor_de_comprimento(nm):
    if nm < 380: return (0.5, 0, 0.5)
    elif nm < 450: return (0.3, 0, 0.7)
    elif nm < 495: return (0, 0, 1.0)
    elif nm < 570: return (0, 0.8, 0)
    elif nm < 590: return (1.0, 1.0, 0)
    elif nm < 620: return (1.0, 0.5, 0)
    elif nm < 750: return (1.0, 0, 0)
    else: return (0.4, 0, 0)


fig, axes = plt.subplots(1, 2, figsize=(14, 6))
fig.suptitle('Gap de banda em perovskitas de haleto CsPbX₃',
             fontsize=13, fontweight='bold')

ax = axes[0]
ax.set_title('Compostos puros CsPbX₃', fontsize=11)

compostos = list(gaps_puros.items())
for i, (nome, gap) in enumerate(compostos):
    nm = eV_para_nm(gap)
    cor = cor_de_comprimento(nm)

    largura = 0.4
    ax.barh(i, 3.5, left=gap, height=largura, color='#457B9D',
            alpha=0.7, label='Banda de condução' if i == 0 else '')
    ax.barh(i, gap, left=0, height=largura, color='#A8DADC',
            alpha=0.7, label='Banda de valência' if i == 0 else '')
    ax.barh(i, 0, height=largura)

    ax.annotate('', xy=(gap, i), xytext=(0, i),
                arrowprops=dict(arrowstyle='<->', color='black', lw=1.5))
    ax.text(gap/2, i + 0.25, f'{gap:.2f} eV\n({nm:.0f} nm)',
            ha='center', va='bottom', fontsize=9, fontweight='bold')

    ax.scatter(gap/2, i - 0.32, s=500, color=cor, zorder=5,
               edgecolor='black', linewidth=0.8)

ax.set_yticks(range(len(compostos)))
ax.set_yticklabels([c[0] for c in compostos], fontsize=11)
ax.set_xlabel('Energia (eV)', fontsize=11)
ax.set_xlim(0, 4)
ax.axvline(0, color='black', lw=1)
ax.legend(fontsize=9, loc='lower right')
ax.grid(axis='x', alpha=0.3)

nm_range = np.linspace(380, 780, 400)
eV_range = 1240 / nm_range
cores_spec = [cor_de_comprimento(nm) for nm in nm_range]
grad = np.array(cores_spec).reshape(1, -1, 3)
ax_spec = ax.inset_axes([0, 1.04, 1, 0.06])
ax_spec.imshow(grad, aspect='auto', extent=[380/1000*3.26, 780/1000*3.26, 0, 1])
ax_spec.set_xlim(0, 4)
ax_spec.axis('off')
ax_spec.set_title('Espectro visível', fontsize=8, pad=2)

ax2 = axes[1]
ax2.set_title('Tunabilidade do gap por composição mista', fontsize=11)

for xi, gi in zip(x_cont, gap_cont):
    nm = eV_para_nm(gi)
    cor = cor_de_comprimento(nm)
    ax2.axvline(xi, color=cor, alpha=0.25, lw=2)

ax2.plot(x_cont, gap_cont, 'k-', lw=2.5,
         label='CsPb(I₁₋ₓBrₓ)₃')
ax2.scatter(x_exp, gap_exp, s=80, color='black', zorder=5)

x_cont2_plot = x_cont + 1
for xi, gi in zip(x_cont2_plot, gap_cont2):
    nm = eV_para_nm(gi)
    cor = cor_de_comprimento(nm)
    ax2.axvline(xi, color=cor, alpha=0.25, lw=2)

ax2.plot(x_cont2_plot, gap_cont2, 'k--', lw=2.5,
         label='CsPb(Br₁₋ᵧClᵧ)₃')
ax2.scatter(y_exp + 1, gap_exp2, s=80, color='black', zorder=5)

ax2.set_xticks([0, 0.5, 1.0, 1.5, 2.0])
ax2.set_xticklabels(['CsPbI₃', '50% I/Br', 'CsPbBr₃', '50% Br/Cl', 'CsPbCl₃'],
                    fontsize=8, rotation=15)
ax2.set_ylabel('Gap de banda (eV)', fontsize=11)
ax2.set_xlabel('Composição', fontsize=11)
ax2.set_ylim(1.4, 3.3)

ax2b = ax2.twinx()
ax2b.set_ylim(1.4, 3.3)
ticks_eV = [1.73, 2.0, 2.25, 2.5, 2.75, 3.00]
ax2b.set_yticks(ticks_eV)
ax2b.set_yticklabels([f'{eV_para_nm(e):.0f} nm' for e in ticks_eV], fontsize=8)
ax2b.set_ylabel('Comprimento de onda (nm)', fontsize=10)

ax2.legend(fontsize=9)
ax2.grid(alpha=0.3)

plt.tight_layout()
plt.savefig('03_gap_banda.png', dpi=150, bbox_inches='tight')
plt.show()
print("Figura salva: 03_gap_banda.png")
