# MPI no exciting — como funciona e como usar

> Nos exemplos abaixo, `$IC` é a raiz deste repositório. Defina uma vez por terminal:
> `export IC=~/Documentos/IC` (ou o caminho onde você clonou).


Guia da paralelização do exciting **nesta instalação específica** (container Apptainer +
binário `exciting_mpismp` compilado no host). Escrito a partir de medições feitas na
própria máquina, não de recomendações genéricas.

> **Resumo executivo (se você só ler uma coisa, leia isto)**
>
> 1. O comando que você vinha usando (`run-exciting.sh`, sem definir `OMP_NUM_THREADS`)
>    está rodando com **12 threads OpenMP** e é **~25× mais lento** que o ótimo nesta máquina.
>    Medido: **299,7 s** contra **12,0 s**.
> 2. Nesta máquina, **OpenMP não acelera nada** — só atrapalha. O eixo que funciona é **MPI**.
> 3. Use: `$IC/bin/run-exciting-mpi.sh -n 2 -t 1` (ou `-n 4 -t 1`).
> 4. O comando MPI documentado na seção 5 do `docs/02-uso-diario.md` **está quebrado**
>    (erro `libIDieL.so: cannot open shared object file`). Veja a seção 7 aqui.

---

## 1. Como o exciting paraleliza

O exciting tem **dois níveis de paralelismo**, e eles fazem coisas diferentes:

| Nível | Mecanismo | O que divide | Memória |
|---|---|---|---|
| **MPI** | processos separados (`mpirun -np N`) | o **laço sobre pontos k** | cada rank tem a sua própria cópia |
| **OpenMP** | threads dentro de um processo | laços internos + BLAS/FFT | memória compartilhada |

### 1.1 MPI = paralelização em pontos k

Este é o ponto central. No ciclo SCF, o trabalho pesado é: para cada ponto **k** da malha
irredutível, montar e diagonalizar o Hamiltoniano. Esses pontos k são **independentes entre si**
dentro de uma iteração SCF — só no fim é que as densidades parciais são somadas.

O código faz exatamente isso. Em [scf_cycle.f90:70-71](../exciting/src/scf_cycle.f90#L70-L71):

```fortran
first_k = firstofset(rank, nkpt)
last_k  = lastofset(rank, nkpt)
```

Cada rank MPI recebe uma fatia contígua dos `nkpt` pontos k, processa só a sua fatia, e no
fim há uma redução coletiva. O mesmo padrão aparece em `bandstructure.f90`, `fermisurf.f90`,
`spintext.f90`, `core_overlap.f90`, `polarization.f90`.

**Consequências práticas:**

- O speedup máximo teórico é limitado por `nkpt`. Com 4 pontos k, mais de 4 ranks não ajuda
  em nada — os ranks extras ficam ociosos.
- Se `nkpt` não for divisível pelo número de ranks, há **desbalanceamento**. Com 145 pontos k
  e 8 ranks, uns ficam com 19 e outros com 18 — irrelevante. Com 10 pontos k e 8 ranks,
  uns ficam com 2 e outros com 1 — o rank mais lento dita o tempo total, e a eficiência cai pela metade.
- Cálculos **sem muitos pontos k** (moléculas em supercélula, `ngridk="1 1 1"`) **não ganham
  nada com MPI**. Não adianta insistir.

### 1.2 O que esta build **não** tem: ScaLAPACK

Verificado no cache do CMake ([build-farm/build-sodium/CMakeCache.txt](evidencias/CMakeCache-sodium.txt)):

```
MPI:BOOL=ON
OMP:BOOL=ON
SCALAPACK:BOOL=OFF      ← ausente
MKL:BOOL=OFF
```

Sem ScaLAPACK, a **diagonalização de cada k não é distribuída** entre processos. Cada rank
diagonaliza a matriz inteira do seu k sozinho. Isso significa:

- **Não dá para reduzir o consumo de memória por rank** adicionando processos. Pelo contrário:
  N ranks ≈ N × a memória de um rank. Isto é decisivo nesta máquina (5,5 GB de RAM).
- Sistemas com base gigante (muitos átomos, `rgkmax` alto) não ficam viáveis via MPI aqui —
  o gargalo é a matriz de um único k, e MPI não a divide.
- Para o futuro (GW/BSE, que o professor mencionou), ScaLAPACK passaria a importar bastante.
  Recompilar com `-DSCALAPACK=ON` é possível — a imagem do container já traz ScaLAPACK.

### 1.3 OpenMP

Threads dentro de cada rank, atuando em laços internos e principalmente dentro do
**OpenBLAS** (álgebra linear) e do **FFTW3**. Compartilham memória, então não multiplicam
o consumo de RAM.

Em teoria é complementar ao MPI (o modelo "híbrido": N ranks × M threads). Na prática,
nesta máquina, **não funciona** — ver seção 3.

---

## 2. Como o container entra nisso

O binário `exciting_mpismp` foi compilado **através** do container mas mora **no host**, em
`build-farm/install-sodium/bin/`. Ele depende de bibliotecas que só existem **dentro** da
imagem `.sif`: `libmpi.so.40` (OpenMPI 5.0.7), `libopenblas.so.0`, `libfftw3.so.3`.

Existem dois modelos de rodar MPI com container. **Só um funciona aqui:**

```
┌─ Modelo A: "container inteiro"  ← É ESTE que usamos ────────────┐
│                                                                 │
│   host:  apptainer exec toolchain.sif                           │
│            └─ container:  mpirun -np 4                          │
│                             ├─ rank 0: exciting_mpismp          │
│                             ├─ rank 1: exciting_mpismp          │
│                             ├─ rank 2: exciting_mpismp          │
│                             └─ rank 3: exciting_mpismp          │
│                                                                 │
│   O mpirun roda DENTRO do container. Um único nó. Simples.      │
└─────────────────────────────────────────────────────────────────┘

┌─ Modelo B: "MPI híbrido host/container"  ← NÃO usamos ──────────┐
│                                                                 │
│   host:  mpirun -np 4 apptainer exec toolchain.sif exciting...  │
│                                                                 │
│   Exige OpenMPI instalado NO HOST e compatível em ABI com o     │
│   do container (PMI/PMIx). Sua máquina não tem OpenMPI no host.  │
│   É o modelo que se usa em clusters com Slurm.                  │
└─────────────────────────────────────────────────────────────────┘
```

Como tudo roda em **uma máquina só**, o Modelo A é o correto e o mais simples. Você só
precisaria do Modelo B se um dia rodar em um cluster com vários nós.

### 2.1 A armadilha do `libIDieL.so`

O `libexcitingLib.so` foi gerado com um **RUNPATH defeituoso** — o caminho ficou gravado como
`.../libL` em vez de `.../lib`. Resultado: o binário não encontra `libIDieL.so` sozinho.

```bash
$ apptainer exec exciting-toolchain.sif mpirun -np 2 .../exciting_mpismp
exciting_mpismp: error while loading shared libraries: libIDieL.so: cannot open shared object file
```

O `run-exciting.sh` já contorna isso injetando `LD_LIBRARY_PATH`. O
**`run-exciting-mpi.sh` (novo) faz o mesmo** — por isso use o wrapper em vez de montar o
comando na mão.

---

## 3. Medições reais nesta máquina

**Sistema de teste:** Ag FCC, 1 átomo, `ngridk="16 16 16"` → **145 pontos k irredutíveis**,
GGA_PBE_SOL, SCF até convergência (9 iterações).
**Máquina:** Intel i5-13420H — 8 núcleos físicos (4 P-cores com HT @4,6 GHz + 4 E-cores @3,4 GHz),
12 threads lógicas, 5,5 GB de RAM.

### 3.1 Escalabilidade MPI pura (1 thread OpenMP por rank)

| ranks MPI | tempo (s) | speedup | eficiência |
|---:|---:|---:|---:|
| 1 | 16,94 | 1,00 | 100 % |
| 2 | **12,01** | **1,41** | 70 % |
| 4 | **10,19** | **1,66** | 42 % |
| 8 | 18,73 | 0,90 | 11 % |

O ganho satura em ~1,7× e **regride com 8 ranks**. As causas nesta máquina:

- **Largura de banda de memória.** O gargalo do exciting é acesso a memória, não aritmética.
  Um laptop tem 2 canais de DDR; 4 ranks já saturam o barramento. Isso é exatamente o que
  o professor comentou sobre "velocidade de memória no desempenho do código".
- **Núcleos heterogêneos.** Os ranks 5-8 caem nos **E-cores** (2,5 GHz efetivos vs 3,7 GHz dos
  P-cores). Como MPI é síncrono a cada iteração SCF, **o rank mais lento segura todos os outros**.
- **RAM.** Sem ScaLAPACK, 8 ranks ≈ 8× a memória. Com 5,5 GB e a máquina já usando ~3,5 GB,
  isso empurra para swap.

### 3.2 OpenMP puro (sem `mpirun`) — o problema

| threads OpenMP | tempo (s) | vs. 1 thread |
|---:|---:|---:|
| 1 | 16,52 | 1,00× |
| 2 | 15,13 | 1,09× |
| 4 | 18,84 | 0,88× (mais lento) |
| 8 | 142,23 | **0,12×** |
| **12 (padrão, sem definir a variável)** | **299,72** | **0,06×** |

Aquela última linha é o que o `run-exciting.sh` faz **hoje, por omissão**: se
`OMP_NUM_THREADS` não estiver definida, o OpenMP usa todas as 12 threads lógicas e o cálculo
fica **18× mais lento que serial** e **25× mais lento que `-n 2 -t 1`**.

> **Isto muito provavelmente explica por que suas simulações não terminavam a tempo.**
> Não era o tamanho do problema — era a configuração de threads.

Por que degrada tanto: OpenBLAS e o OpenMP do exciting criam threads que competem pelas
mesmas 12 threads lógicas (sobre-inscrição), com HyperThreading e E-cores no meio, tudo
disputando a mesma largura de banda de memória. Em código memória-limitado, mais threads =
mais contenção, não mais trabalho.

### 3.3 Híbrido MPI × OpenMP

| ranks × threads | carga total | tempo (s) |
|---|---:|---:|
| 1 × 1 | 1 | 16,94 |
| **2 × 1** | 2 | **12,01** ← melhor |
| 2 × 2 | 4 | 12,62 |
| 4 × 1 | 4 | 10,19 |
| 1 × 4 | 4 | 17,35 |
| 4 × 2 | 8 | 29,14 |
| 2 × 4 | 8 | 44,70 |
| 1 × 8 | 8 | 92,58 |

**Padrão claro:** para uma mesma carga total, **mais MPI e menos OpenMP é sempre melhor**.
E carga total acima de ~4 degrada tudo.

### 3.4 Conclusão operacional

```
   Use:  -n 2 -t 1   (seguro, ~1,4× e baixo uso de RAM)
    ou:  -n 4 -t 1   (mais rápido em casos com muitos k, mais RAM)

  Evite: qualquer coisa com -t > 1
  Evite: -n 8 nesta máquina
  Nunca: run-exciting.sh sem OMP_NUM_THREADS definido
```

> **Ressalva honesta sobre os números:** o benchmark rodou com a máquina já ocupada
> (~3,5 GB de RAM em uso e swap ativo). Os tempos absolutos e o ponto exato de saturação
> podem melhorar com a máquina ociosa. O padrão qualitativo — MPI ajuda pouco e satura cedo,
> OpenMP prejudica — é robusto, porque aparece em todas as três tabelas de forma consistente.
> **Vale refazer o benchmark com a máquina limpa** (seção 5) antes de reportar ao professor.

---

## 4. Como usar — o wrapper `run-exciting-mpi.sh`

Criado em [run-exciting-mpi.sh](../bin/run-exciting-mpi.sh). Ele monta o comando correto,
injeta o `LD_LIBRARY_PATH` que contorna o bug do RUNPATH, e fixa o binding de CPU.

### 4.1 Uso básico

```bash
cd $IC/runs/meu-calculo     # pasta com input.xml + species .xml

$IC/bin/run-exciting-mpi.sh -n 2 -t 1     # recomendado
$IC/bin/run-exciting-mpi.sh -n 4 -t 1     # se tiver muitos pontos k
```

| flag | significado | padrão |
|---|---|---|
| `-n N` | número de processos MPI | 4 |
| `-t M` | threads OpenMP por rank | 8/N (mas **use sempre `-t 1`**) |

### 4.2 Confirmando que o MPI está mesmo ativo

O cabeçalho do `INFO.OUT` reporta o número de ranks:

```bash
grep "processor(s)" INFO.OUT
```
```
MPI version using      4 processor(s)
```

Se aparecer `1 processor(s)` quando você pediu 4, o `mpirun` não pegou — reveja o comando.

### 4.3 Escolhendo `-n` pelo número de pontos k

```bash
grep "Total number of k-points" INFO.OUT
```

Regra: `-n` deve **dividir** `nkpt` o mais exatamente possível, e nunca excedê-lo.

| pontos k | `-n` sugerido |
|---:|---|
| 1 – 3 | 1 (MPI não ajuda) |
| 4 – 15 | 2 |
| 16 – 100 | 2 ou 4 |
| > 100 | 4 |

### 4.4 Acompanhando enquanto roda

```bash
tail -f INFO.OUT                    # progresso do SCF
watch -n 2 free -h                  # RAM — se 'available' zerar, reduza -n
htop                                # deve mostrar N processos exciting_mpismp
```

---

## 5. O script de escalabilidade (o que o professor pediu)

[bench-exciting-mpi.sh](../bin/bench-exciting-mpi.sh) roda o mesmo `input.xml` com números
crescentes de ranks e gera uma tabela de speedup/eficiência.

```bash
mkdir -p $IC/runs/bench && cd $IC/runs/bench
cp <seu input.xml> .
cp $IC/exciting/species/Ag.xml .        # ajuste ao seu elemento

$IC/bin/bench-exciting-mpi.sh -t 1 -l "1 2 4 8"
```

Ele cria uma subpasta `np1/`, `np2/`, … por configuração (cada cálculo isolado, como manda
a regra de ouro) e escreve `scaling.dat`:

```
# nproc nthreads tempo_s speedup eficiencia
    1        1    16.94    1.000    100.0
    2        1    12.01    1.410     70.5
    4        1    10.19    1.661     41.5
    8        1    18.73    0.904     11.3
```

**Para reportar ao professor**, feche o navegador e tudo o mais antes de rodar, e plote:

```bash
gnuplot -p -e "set xlabel 'processos MPI'; set ylabel 'speedup'; set key left top; \
  plot 'scaling.dat' u 1:4 w lp pt 7 t 'medido', x w l dt 2 t 'ideal'"
```

O desvio da reta ideal é justamente o assunto que ele levantou (largura de banda de
memória, sincronização) — o gráfico é o material da conversa.

---

## 6. Como isso afeta os tutoriais Jupyter

Os notebooks chamam `excitingscripts`, que executa `$EXCITINGROOT/bin/exciting_smp` — o
**shim** que delega para `run-exciting.sh`. Ou seja: **os tutoriais rodam sem MPI e com
12 threads OpenMP** — a pior configuração possível (seção 3.2).

Duas correções, da menos para a mais invasiva:

**(a) Limitar as threads antes de abrir o Jupyter** — resolve o pior do problema, sem mexer
em script nenhum:

```bash
source $IC/bin/env/tutoriais.sh
export APPTAINERENV_OMP_NUM_THREADS=1
export APPTAINERENV_OPENBLAS_NUM_THREADS=1
cd $IC/exciting/tutorials && jupyter-notebook
```

Ganho esperado nos tutoriais: da ordem de **18×** (299,7 s → 16,5 s no caso de teste).
O prefixo `APPTAINERENV_` é necessário porque a variável precisa atravessar para dentro
do container.

**(b) Corrigir o `run-exciting.sh` de vez** — ✅ **aplicado em 17/08/2026.** O wrapper
[bin/run-exciting.sh](../bin/run-exciting.sh) agora fixa o padrão em 1 thread quando
ninguém definiu nada:

```bash
export APPTAINERENV_OMP_NUM_THREADS="${APPTAINERENV_OMP_NUM_THREADS:-${OMP_NUM_THREADS:-1}}"
export APPTAINERENV_OPENBLAS_NUM_THREADS="${APPTAINERENV_OPENBLAS_NUM_THREADS:-${OMP_NUM_THREADS:-1}}"
```

A precedência importa: um `APPTAINERENV_*` já definido (é o caso quando
`run-exciting-task.sh` recebe `-t N`) vence, depois `OMP_NUM_THREADS` do ambiente, e só
então o padrão 1. Isso beneficia tutoriais e trabalho próprio de uma vez — a alternativa
(a) acima deixou de ser necessária, embora continue funcionando.

Fazer os notebooks usarem MPI de fato exigiria trocar o shim para chamar
`run-exciting-mpi.sh`. Funciona, mas os tutoriais são pequenos e o ganho de MPI ali é
modesto; a correção de threads é onde está o ganho real.

---

## 7. Correção do `docs/02-uso-diario.md`

O comando MPI documentado na seção 5 daquele guia **não funciona** — falta o
`LD_LIBRARY_PATH`:

```bash
# ✗ ERRADO (o que está documentado lá) — falha com libIDieL.so not found
apptainer exec $IC/exciting-toolchain.sif \
    mpirun -np 4 $IC/build-farm/install-sodium/bin/exciting_mpismp

# ✓ CERTO
$IC/bin/run-exciting-mpi.sh -n 4 -t 1
```

E se algum dia precisar do comando cru, sem o wrapper:

```bash
APPTAINERENV_LD_LIBRARY_PATH="$HOME/Documentos/IC/build-farm/install-sodium/lib:/opt/openblas/lib:/usr/local/lib:/opt/openmpi/lib" \
apptainer exec $IC/exciting-toolchain.sif \
    mpirun -np 4 -x OMP_NUM_THREADS=1 \
    $IC/build-farm/install-sodium/bin/exciting_mpismp
```

---

## 8. Problemas comuns

### `error while loading shared libraries: libIDieL.so`
Faltou o `LD_LIBRARY_PATH`. Use `run-exciting-mpi.sh` (seção 4) — ele já injeta.

### `There are not enough slots available in the system`
Você pediu mais ranks que núcleos físicos. O wrapper adiciona `--oversubscribe`
automaticamente acima de 8, mas **oversubscription é sempre mais lento** — reduza o `-n`.

### `MPI version using 1 processor(s)` quando pedi 4
O `mpirun` não foi aplicado. Verifique se está usando `run-exciting-mpi.sh` e não
`run-exciting.sh`.

### A máquina trava / OOM killer
Sem ScaLAPACK, cada rank replica a memória. Reduza `-n`, reduza `ngridk`, e monitore com
`watch -n 2 free -h` em outro terminal. Fechar navegador antes de cálculos grandes faz
diferença real com 5,5 GB de RAM.

### Speedup ruim mesmo com `-t 1`
Confira `nkpt` (seção 4.3). Poucos pontos k = pouco paralelismo disponível. E lembre que
o teto medido nesta máquina é ~1,7× — isso é o esperado aqui, não um erro seu.

### Resultados diferentes entre `-n 1` e `-n 4`
Não deveriam ser diferentes além do ruído numérico (últimos dígitos), porque as reduções
mudam a ordem das somas em ponto flutuante. Diferença na 5ª casa ou além: normal.
Diferença no 3º dígito da energia total: aí há algo errado — reporte.

---

## 9. Referência rápida

| Ação | Comando |
|---|---|
| Rodar com MPI (recomendado) | `$IC/bin/run-exciting-mpi.sh -n 2 -t 1` |
| Rodar com MPI (muitos k) | `$IC/bin/run-exciting-mpi.sh -n 4 -t 1` |
| Benchmark de escalabilidade | `$IC/bin/bench-exciting-mpi.sh -t 1 -l "1 2 4 8"` |
| Conferir ranks ativos | `grep "processor(s)" INFO.OUT` |
| Conferir pontos k | `grep "Total number of k-points" INFO.OUT` |
| Tutoriais Jupyter rápidos | `export APPTAINERENV_OMP_NUM_THREADS=1` antes do `jupyter-notebook` |
| Monitorar RAM | `watch -n 2 free -h` |
| Ver opções do container MPI | `apptainer exec exciting-toolchain.sif mpirun --version` |

**Arquivos relacionados:** [docs/02-uso-diario.md](02-uso-diario.md) ·
[run-exciting.sh](../bin/run-exciting.sh) · [run-exciting-mpi.sh](../bin/run-exciting-mpi.sh) ·
[bench-exciting-mpi.sh](../bin/bench-exciting-mpi.sh) · [build-exciting.sh](../bin/build-exciting.sh)
