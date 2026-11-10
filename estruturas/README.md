# Estruturas de partida

Os arquivos de geometria que **entram** nos cálculos, na forma em que foram
recebidos: os `POSCAR` do VASP que o professor forneceu para as fases das perovskitas.

Ficam aqui, e não em `runs/`, por um motivo prático: o `.gitignore` ignora `runs/**`
e só reabilita alguns nomes (`input.xml`, `INFO.OUT`, `*.png`…). Um arquivo chamado
`POSCAR` não casa com nenhum deles e seria ignorado **sem aviso** — a geometria
original sumiria do repositório. Aqui ela é versionada.

`runs/` é volátil e refazível; `estruturas/` é fonte, como `registros/`.

## Convenção

Uma pasta por material, um arquivo por fase:

```
estruturas/
└── CsSnBr3/
    ├── POSCAR.pm3m     cúbica Pm-3m
    ├── POSCAR.p4mbm    tetragonal P4/mbm
    ├── POSCAR.i4mcm    tetragonal I4/mcm
    ├── POSCAR.gamma    ortorrômbica γ-Pnma
    ├── POSCAR.delta    ortorrômbica δ-Pnma (fase amarela, não perovskita)
    ├── POSCAR.r3c      romboédrica R-3c
    └── POSCAR.r3m      romboédrica R3m
```

A pasta do material existe porque o `CsSnI₃` entra em 03/2027 com os mesmos nomes de
fase — sem ela, `POSCAR.pm3m` colidiria.

Converter para o formato do exciting:

```bash
bin/poscar2xml.py estruturas/CsSnBr3/POSCAR.pm3m --sem-rmt -o geometry.xml
bin/poscar2xml.py estruturas/CsSnBr3/POSCAR.pm3m --rmt Cs=2.2,Sn=2.0,Br=2.0
```

`--sem-rmt` omite o atributo, e o exciting usa o raio do arquivo de espécie (Cs 2,2 ·
Sn 2,0 · Br 2,0 bohr) — é o que basta para o PBE. Sem nenhuma das duas opções, cada
espécie sai com `rmt="defineHere<Especie>"`, um marcador proposital que o exciting
rejeita.

**Atenção ao `rgkmax`:** ele é definido em relação ao **menor** raio de muffin-tin.
Mudar os `rmt` muda o tamanho da base sem que o `rgkmax` mude de número — o que
importa na hora de comparar com os valores de referência.

## Procedência

Sem procedência, uma geometria não vale nada: não dá para citar num artigo nem para
outra pessoa refazer o cálculo. Preencha ao receber cada arquivo.

| material | fase | recebido de | quando | fonte original (artigo, ICSD, Materials Project) |
|---|---|---|---|---|
| CsSnBr₃ | as sete | professor | 03/09/2026 | <!-- a preencher: provavelmente as geometrias relaxadas do artigo 10.1021/acs.jpcc.5c03168 — confirmar --> |

### As sete fases, conferidas

| fase | átomos | fórmula | a, b, c (Å) | volume (Å³) | volume por fórmula |
|---|---:|---|---|---:|---:|
| pm3m | 5 | CsSnBr₃ | 5,889 · 5,889 · 5,889 | 204,3 | 204,3 |
| p4mbm | 10 | Cs₂Sn₂Br₆ | 8,272 · 8,272 · 5,928 | 405,6 | 202,8 |
| i4mcm | 20 | Cs₄Sn₄Br₁₂ | 8,296 · 8,296 · 11,831 | 814,2 | 203,5 |
| gamma | 20 | Cs₄Sn₄Br₁₂ | 8,334 · 8,202 · 11,774 | 804,9 | 201,2 |
| delta | 20 | Cs₄Sn₄Br₁₂ | 4,586 · 10,092 · 17,013 | 787,4 | 196,9 |
| r3c | 10 | Cs₂Sn₂Br₆ | 8,270 · 8,270 · 8,270 | 400,7 | 200,4 |
| **r3m** | 15 | Cs₃Sn₃Br₉ | 8,807 · 8,807 · 11,224 | 753,9 | **251,3** ⚠️ |

A estequiometria fecha nas sete. Seis das sete têm volume por fórmula entre 197 e 204
Å³ — uma dispersão de 3,5 %. A **r3m** está em 251 Å³, **25 % acima** das irmãs. É
também o único arquivo escrito em outro estilo (título `CsSnBr_rombo`, sem o ₃;
`direct` em minúscula; sem os espaços de alinhamento das outras), o que sugere que foi
produzido separadamente. Vale conferir com o professor antes de gastar cálculo nela —
não afeta a fase Pm-3m desta semana.

## O que não vem no POSCAR

O POSCAR traz rede e posições atômicas, e nada mais. Ainda faltam, por fase:

- os **raios de muffin-tin** de cada espécie (`rmt`);
- os **parâmetros de pontos-k** — o professor ficou de fornecer, por fase.

Os dois entram no `input.xml`, e os valores convergidos vão para
[`registros/parametros-convergidos.conf`](../registros/parametros-convergidos.conf).
