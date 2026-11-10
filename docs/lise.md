# Lise (NHR@ZIB) — o que precisa saber para rodar o exciting lá

Resumo do [manual do NHR@ZIB](https://user.nhr.zib.de), organizado pelo checklist que o
professor passou. Cada item diz de qual página do manual veio.

> **Em uma frase:** rodar na partição **`cpu-clx`**, submetendo pelo **`blogin`**, com os
> arquivos no **WORK**, debitando da conta pessoal (75 mil core-h por trimestre). Um nó
> CLX custa 96 core-h por hora, use ele todo ou não.

---

## 1. Partições e filas

O escalonador é o **Slurm**. As partições de CPU (*Cluster overview* e *Compute time*):

| partição | nó | cobrança | alocação | tempo máximo |
|---|---|---:|---|---|
| **`cpu-clx`** (padrão) | Intel CLX, 96 cores, 384 GiB | **96 core-h por nó-hora** | exclusiva | 12 h |
| `cpu-clx:test` | idem | 96 por nó-hora | exclusiva | **1 h** |
| `cpu-clx:ssd` | idem, com SSD local | 96 por nó-hora | exclusiva | 12 h |
| `cpu-clx:large` | CLX com mais memória | 144 por nó-hora × fração | **compartilhável** | 48 h |
| `cpu-clx:huge` | CLX com muito mais memória | 192 por nó-hora × fração | **compartilhável** | 48 h |
| `cpu-genoa` | AMD Genoa, 192 cores, 1536 GiB | **192 por nó-hora** | exclusiva | 12 h |
| `cpu-genoa:test` | idem | 192 por nó-hora | exclusiva | 1 h |

- **Tempo máximo:** conferido com `sinfo -s` em 01/10. As partições de teste têm **1 h**;
  as compartilháveis, 2 dias.
- **Tamanho:** a `cpu-clx` tem 772 nós (185 livres no momento do levantamento); a
  `cpu-clx:test`, 32. Dá para pedir 24 h por e-mail ao suporte, como último recurso.
- **Cada arquitetura tem seu nó de login e seu software** (*Cluster overview*). Os
  exemplos com `cpu-clx:test` são submetidos do **`blogin`**; o `genoa-login` é o da
  Genoa.

### Por que CLX e não Genoa

O MPI do exciting divide **pontos k** entre os ranks, e ranks a mais que pontos k ficam
ociosos:

| fase | malha | pontos k |
|---|---|---:|
| `r3m` | 5×5×4 | 28 |
| `pm3m` | 8×8×8 | 35 |
| `p4mbm` | 6×6×8 | 50 |
| `r3c` | 6×6×6 | 126 |

Com 28 a 126 pontos k, um nó CLX (96 cores) já sobra. A Genoa tem o dobro de cores e
custa o dobro por hora: só valeria se rodasse duas vezes mais rápido, e os pontos k não
dão trabalho para tantos cores.

## 2. Programas instalados e o sistema de módulos

*Software stack.*

```bash
module avail                     # tudo o que existe, em CATEGORIAS
module load <pacote>/<versão>    # torna o programa visível (PATH etc.)
module list                      # o que está carregado
module show <pacote>/<versão>    # quais variáveis o módulo mexe
module unload <pacote>/<versão>
```

- Os `module load` vão **dentro do job script**. No `.bashrc` o manual diz para não pôr.
- O exemplo do manual usa `module load impi` (Intel MPI) com `mpirun`.
- `module load use.own` habilita módulos próprios em `$HOME/privatemodules`.

### O exciting já está instalado

No `blogin`, em `CHEMISTRY`:

| módulo | observação |
|---|---|
| `exciting/011-sodium-alpha` | **a versão a usar**: a série *sodium*, a mesma da build local |
| `exciting/010-neon-21` | versão anterior (*neon*) |
| `exciting/010-neon-21-binary-skl` | *neon*, binário para Skylake |

A build local é a `sodium-230` (é o que o `INFO.OUT` imprime como *version hash id*).
"Sodium-alpha" e "sodium-230" não são necessariamente o mesmo código, por isso:

- O módulo exige o `impi/2021.15` carregado antes (`module show`), e o binário é o
  `exciting_mpismp`, o mesmo nome da build local.
- Os arquivos de espécie do módulo (`$EXCITING_SPECIES`) **não são usados**: os inputs têm
  `speciespath="./"` e levam as espécies da pasta, as mesmas da máquina local.
- ✅ Validado em 01/10 contra a build local, em PBE e PBE-1/2 (seção 6 e ordem dos testes).

Também disponíveis na CLX: compiladores `intel/2024.2` a `2025.3` e `gcc/13.3.0`; MPI
`impi/2021.13` a `2021.18` e `openmpi/gcc/5.0.3`; `fftw3`; `cmake`.

> O **VASP também está instalado** (`vasp/5.4.4.p1`, `6.4.3`, `6.5.1`). Em geral o uso
> depende de licença do grupo; isso é assunto para o professor, por causa do item "revisar
> a R3m contra o VASP" da reunião de 18/09.

## 3. Job script

*Job scheduling.* As linhas `#SBATCH` vêm logo depois do `#!/bin/bash`; o Slurm para de
procurá-las na primeira linha que não é comentário.

| o quê | flag |
|---|---|
| nós | `-N <n>` |
| ranks MPI no total | `-n <n>` |
| ranks MPI por nó | `--tasks-per-node <n>` (o padrão difere entre `mpirun` e `srun`) |
| **cores por rank (threads OpenMP)** | **`-c <n>`** |
| partição | `-p <nome>` |
| tempo máximo | `-t hh:mm:ss` — estimativa realista ajuda a fila |
| conta a debitar | `-A <id>` — sem isso, a conta pessoal |
| aviso por e-mail | `--mail-type=ALL` |

Esqueleto para o exciting num nó CLX.

```bash
#!/bin/bash
#SBATCH -p cpu-clx
#SBATCH -N 1
#SBATCH --tasks-per-node 28        # ranks MPI: até o número de pontos k
#SBATCH -c 3                       # threads OpenMP por rank: 28 × 3 = 84 de 96 cores
#SBATCH -t 04:00:00
#SBATCH -J r3m-pbe

module load impi/2021.15
module load exciting/011-sodium-alpha
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
cd $WORK/runs/CsSnBr3-r3m-pbe
mpirun -np $SLURM_NTASKS exciting_mpismp
```

### Comandos do dia a dia

```bash
sbatch job.slurm                 # submete; devolve o ID do job
squeue --me                      # meus jobs (squeue -l --me: formato longo)
squeue --start -j <id>           # previsão de início
scontrol show job <id>           # tudo sobre o job, mesmo depois de terminar
scancel <id>                     # cancela
sinfo                            # partições e limites
```

Sessão interativa, útil para os primeiros testes:

```bash
salloc -t 00:30:00 -p cpu-clx:test -N 1    # reserva um nó
srun --pty --interactive --preserve-env $SHELL   # entra nele
```

### ⚠️ Nada de muitos jobs curtos

O manual pede **pelo menos 1 h por job** e avisa que muitos jobs que terminam (ou quebram)
rápido sobrecarregam a contabilidade, e **a conta pode ser suspensa**. Um job curto de vez
em quando não tem problema. **Testes de ranks × threads vão num único job**, que roda as
combinações em sequência. Para muitos cálculos parecidos, use *job arrays*
(`sbatch -a 0-N`) ou *job chains* (`--dependency=afterok:<id>`).

## 4. HOME e WORK

*Data management.*

| | HOME | WORK |
|---|---|---|
| caminho | `/home/$USER` (`$HOME`) | `/scratch/usr/$USER` (`$WORK`) |
| para quê | configuração, código-fonte, executáveis | I/O dos jobs em produção |
| cota de usuário (soft / hard) | 40 / 100 GiB | 3 / 30 TiB, e 250 mil / 1,5 milhão de arquivos |
| backup | **snapshots diários** em `/home/.snapshots/` | **nenhum** |

- **Os cálculos rodam no WORK.** Um `EVECFV.OUT` da `r3m` tem 363 MB.
- **O WORK não tem backup.** Resultado que importa volta para a máquina local.
- **Os nós de cálculo não acessam a rede:** a cópia de arquivos é feita do login ou da
  máquina local, nunca de dentro do job.
- `show-quota` mostra uso e limites. No limite *soft* começa uma carência de 2 semanas.
- `$LOCAL_TMPDIR`: disco local do nó, apagado ao fim do job.
- PERM (`/perm/$USER`): fita, só pelo login, para dados inativos.

## 5. Conta pessoal e conta de projeto

*Compute time* e *User access.*

**Custo de um job:** `c = nós × horas × taxa × fração`. Nas partições exclusivas a fração
é sempre 1: **o nó inteiro é cobrado**, use 4 cores ou 96. Ex.: 1 nó `cpu-clx` por 4 h =
1 × 4 × 96 = **384 core-h**.

| | conta pessoal (*Test Project*) | projeto (*Compute Project*) |
|---|---|---|
| core-hours | **75 mil por trimestre**, até 300 mil sob pedido | 300 mil a 5 milhões por trimestre, com proposta revisada |
| sobra do trimestre | **perde** | passa para o seguinte |
| duração | 3 trimestres (prorrogável informalmente) | 4 trimestres |
| HOME / WORK | 40 GiB / 3 TiB | 40 GiB / 12 TiB em `/home/projects/<id>` e `/scratch/projects/<id>` |
| nome da conta no Slurm | **o próprio nome de usuário** | o ID do projeto, via `-A <id>` |

- Sem `-A`, o job debita a conta padrão, que é a pessoal. Dá para mudar o padrão no
  portal.
- Conta sem saldo: o job fica parado com `(AccountOutOfComputeTime)` no `squeue`.
- Disco não é cobrado; só tem cota.
- **Abaixo de 300 mil core-h por trimestre não é preciso projeto.** A conta pessoal basta.

**A sua conta hoje** (levantamento de 01/10): a única conta de cobrança no Slurm é
`<usuario>` (QoS `normal`), e os grupos são só `<usuario>` e `hlrnuser`. Ou seja, **ainda não
há projeto**: tudo debita a conta pessoal. HOME e WORK estão vazios (0 B de 40 GiB e de
3 TiB).

**Para o nosso trabalho:** 75 mil core-h dão **781 horas de nó CLX por trimestre**. A
matriz inteira (7 fases × 4 níveis = 28 cálculos), mesmo a 4 h cada, gasta cerca de
11 mil. O trimestre começou em 01/10, então o saldo está cheio, e o que não for usado até
31/12 se perde.

---

## 6. Fluxo de um cálculo

Convenção: aqui, `runs/` é organizada por semana (`runs/semana-NN/<pasta>`). No Lise o
espelho é **plano**, só pelo nome: `$WORK/runs/<pasta>` (`/scratch/usr/<usuario>/runs/<pasta>`).
O nome identifica a pasta, então ele não pode se repetir entre semanas (o envio recusa), e
jobs submetidos antes da reorganização continuam no mesmo lugar. A configuração (host, caminho, partição e tempo
padrão, e-mails, módulos) fica num lugar só: [`bin/lise/lise.conf`](../bin/lise/lise.conf).

### Com as tasks do VS Code

Com o `input.xml` da pasta aberto no editor:

| task | o que faz | fala com o Lise? |
|---|---|---|
| **Lise: abrir terminal (blogin)** | sessão interativa no login da CLX. Há também o perfil "Lise (blogin)" no menu ⌄ do terminal | sim |
| **Lise: criar job.slurm** | escreve o `job.slurm` na pasta, versionado: partição, ranks, threads, tempo, e-mail e custo máximo | **não** |
| **Lise: enviar e submeter** | envia input, espécies e `job.slurm` (e o restart, se `do="skip"`); confere se o job do Lise é o mesmo da pasta local; mostra o resumo e o custo máximo; **só submete com "s"** | sim |
| **Lise: estado dos jobs** | a fila e, para cada job registrado ainda não trazido, situação, tempo gasto e iteração do SCF | sim |
| **Lise: trazer resultado** | traz tudo menos `EVEC*`, os arquivos de entrada e, se não for pedido, o `STATE.OUT` (77–94% do volume; fica no Lise, só serve para continuar um cálculo); mostra o custo real; gera figuras, índice e resultado. Pode rodar várias vezes ao mesmo tempo, cada uma no seu terminal | sim |
| **Lise: trazer todos os terminados (em paralelo)** | pergunta ao Slurm quais jobs registrados já terminaram e traz todos, até 4 ao mesmo tempo (`bin/lise/trazer-terminados.sh`), com a mesma pergunta sobre o `STATE.OUT`; logs em `.lise/trazer/<job>.log` e resumo no fim | sim |

O ciclo de um cálculo: **criar job.slurm → enviar e submeter → (e-mail ao terminar) →
trazer resultado**.

- **Lote:** uma pasta-mãe **sem** `input.xml`, com subpastas que têm. O `criar-job.py` gera
  um job que roda as subpastas em sequência, imprimindo o gap de cada uma; enviar, estado e
  trazer tratam a árvore inteira. É o jeito de rodar vários cálculos curtos sem violar a
  regra dos jobs curtos. Nas tasks, deixe em foco um arquivo **da pasta-mãe** (o
  `job.slurm`), não o `input.xml` de uma subpasta.

- **Ranks `auto`:** se a pasta já rodou (`KPOINTS.OUT`), um rank por ponto k, até o
  limite do nó; senão, o nó inteiro.
- **Registro dos jobs:** `.lise/jobs.tsv` (fora do git), com data, ID, pasta, partição e
  situação. É de lá que o estado e o trazer tiram o ID.
- **E-mail:** `--mail-type=END,FAIL` para **um** endereço, o do `lise.conf`. Testado em
  01/10: uma lista separada por vírgulas não entrega nada; um endereço só (o Gmail) recebeu
  o aviso de início e o de fim. Para receber em mais de uma caixa, encaminhe a partir do
  Gmail.

### Quem dispara

Os scripts que falam com o Lise (`enviar`, `submeter`, `estado`, `trazer`, `trazer-terminados`, `limpar`) rodam disparados
por você, numa task do VS Code ou num terminal. Se existir um arquivo `.lise/trava.sh`, o
[`comum.sh`](../bin/lise/comum.sh) o carrega antes de qualquer conexão: é o lugar para verificações locais que devem
impedir o envio (o script para ali se a verificação falhar).

O `criar-job.py` não fala com o Lise: preparar a pasta não envolve o supercomputador.

O `limpar.sh <pasta>` apaga no Lise só o `SCCLI` e o `EXCLI` de um BSE terminado. Ele recusa se faltar aqui o `EPSILON`
ou o `EXCITON` das três direções, se a etapa 04 não tiver terminado bem, ou se houver job da pasta na fila. Sem esses
arquivos, repetir a etapa 04 exige refazer a 03. `--lista` só mostra o que seria apagado.

### À mão, sem as tasks

**Enviar** (seu computador; exemplo com a `pm3m`):

```bash
ssh blogin mkdir -p /scratch/usr/<usuario>/runs/CsSnBr3-pm3m-pbe
rsync -av input.xml job.slurm Cs.xml Sn.xml Br.xml blogin:/scratch/usr/<usuario>/runs/CsSnBr3-pm3m-pbe/
```

**Submeter e acompanhar** (no `blogin`):

```bash
cd $WORK/runs/CsSnBr3-pm3m-pbe
sbatch job.slurm                  # responde "Submitted batch job <id>"
squeue --me                       # PD = na fila, R = rodando; some da lista ao terminar
```

**Trazer de volta** (seu computador):

```bash
rsync -av --exclude='EVEC*' blogin:/scratch/usr/<usuario>/runs/CsSnBr3-pm3m-pbe/ runs/semana-04/CsSnBr3-pm3m-pbe/
```

## Ordem dos testes antes de submeter as fases

1. ✅ **Acesso:** login no `genoa-login` e no `blogin` em 01/10, e o levantamento do
   ambiente — passo a passo em [lise-acesso.md](lise-acesso.md).
2. ✅ **Programa:** existe como módulo (`exciting/011-sodium-alpha`). Falta o
   `module show` para saber o binário e as dependências.
3. ✅ **Validação** (01/10): a `pm3m` deu **0,6447 eV** (PBE) e **1,8261 eV** (PBE-1/2),
   iguais aos locais até 10⁻⁸ Ha. O DFT-1/2 funciona no `sodiumalpha`.
4. **Ranks × threads:** a mesma `pm3m` com várias combinações, **num único job**, para
   escolher o padrão antes das fases caras.
5. Só então a `r3m` e as fases de 20 átomos (`i4mcm`, `gamma`, `delta`).
