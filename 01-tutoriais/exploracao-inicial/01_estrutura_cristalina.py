"""Visualiza a estrutura cristalina de uma perovskita ABX3 e a inclinacao dos octaedros."""

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

COLORS = {
    'A': '#E63946',
    'B': '#457B9D',
    'X': '#A8DADC',
    'octaedro': '#457B9D',
}
SIZES = {'A': 300, 'B': 200, 'X': 120}


def octaedro_vertices(centro, d, tilt_x=0, tilt_z=0):
    dirs = np.array([
        [1, 0, 0], [-1, 0, 0],
        [0, 1, 0], [0, -1, 0],
        [0, 0, 1], [0, 0, -1],
    ], dtype=float) * d

    tz = np.radians(tilt_z)
    Rz = np.array([[np.cos(tz), -np.sin(tz), 0],
                   [np.sin(tz),  np.cos(tz), 0],
                   [0,           0,          1]])

    tx = np.radians(tilt_x)
    Rx = np.array([[1, 0,           0          ],
                   [0, np.cos(tx), -np.sin(tx) ],
                   [0, np.sin(tx),  np.cos(tx) ]])

    dirs = (Rz @ Rx @ dirs.T).T
    return np.array(centro) + dirs


def desenha_octaedro(ax, vertices, alpha=0.15):
    pares = [(0,2),(0,3),(1,2),(1,3),(0,4),(0,5),(1,4),(1,5),
             (2,4),(2,5),(3,4),(3,5)]
    for i, j in pares:
        ax.plot(*zip(vertices[i], vertices[j]), color=COLORS['octaedro'],
                lw=1.2, alpha=0.7)

    faces = [(0,2,4),(0,2,5),(0,3,4),(0,3,5),
             (1,2,4),(1,2,5),(1,3,4),(1,3,5)]
    poly = Poly3DCollection([[vertices[f[0]], vertices[f[1]], vertices[f[2]]]
                              for f in faces],
                             alpha=alpha, facecolor=COLORS['octaedro'],
                             edgecolor='none')
    ax.add_collection3d(poly)


def plota_fase(ax, titulo, tilt_x=0, tilt_z=0):
    a = 1.0
    d = 0.45

    B_pos = [(i*a, j*a, 0) for i in range(2) for j in range(2)]

    sinais = [1, -1, -1, 1]

    for k, (pos, s) in enumerate(zip(B_pos, sinais)):
        verts = octaedro_vertices(pos, d, tilt_x=s*tilt_x, tilt_z=s*tilt_z)
        desenha_octaedro(ax, verts)
        ax.scatter(*pos, color=COLORS['B'], s=SIZES['B'], zorder=5,
                   depthshade=False)
        for v in verts:
            ax.scatter(*v, color=COLORS['X'], s=SIZES['X'], zorder=4,
                       depthshade=False)

    for i in [-0.5, 0.5, 1.5]:
        for j in [-0.5, 0.5, 1.5]:
            ax.scatter(i*a, j*a, 0, color=COLORS['A'], s=SIZES['A'],
                       zorder=3, depthshade=False)

    ax.set_title(titulo, fontsize=12, fontweight='bold', pad=8)
    ax.set_xlim(-0.7, 1.7); ax.set_ylim(-0.7, 1.7); ax.set_zlim(-0.6, 0.6)
    ax.set_xlabel('a'); ax.set_ylabel('b'); ax.set_zlabel('c')
    ax.set_box_aspect([2.4, 2.4, 1.2])
    ax.view_init(elev=20, azim=-50)
    ax.grid(False)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])


fig = plt.figure(figsize=(15, 5))
fig.suptitle('Estrutura cristalina de perovskitas ABX₃ - polimorfos',
             fontsize=14, fontweight='bold', y=1.01)

dados_fases = [
    ('Fase α - Cúbica\n(sem inclinação)', 0, 0),
    ('Fase β - Tetragonal\n(inclinação ~10°)', 10, 0),
    ('Fase γ - Ortorrômbica\n(inclinação ~20°)', 20, 15),
]

for idx, (titulo, tx, tz) in enumerate(dados_fases):
    ax = fig.add_subplot(1, 3, idx+1, projection='3d')
    plota_fase(ax, titulo, tilt_x=tx, tilt_z=tz)

from matplotlib.lines import Line2D
legenda = [
    Line2D([0],[0], marker='o', color='w', markerfacecolor=COLORS['A'],
           markersize=10, label='Cátion A (grande, ex: Cs⁺, MA⁺)'),
    Line2D([0],[0], marker='o', color='w', markerfacecolor=COLORS['B'],
           markersize=8,  label='Cátion B (pequeno, ex: Pb²⁺)'),
    Line2D([0],[0], marker='o', color='w', markerfacecolor=COLORS['X'],
           markersize=6,  label='Ânion X (ex: I⁻, Br⁻)'),
]
fig.legend(handles=legenda, loc='lower center', ncol=3,
           bbox_to_anchor=(0.5, -0.05), fontsize=10)

plt.tight_layout()
plt.savefig('01_estrutura_cristalina.png', dpi=150, bbox_inches='tight')
plt.show()
print("Figura salva: 01_estrutura_cristalina.png")
