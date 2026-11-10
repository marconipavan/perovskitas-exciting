# Perovskitas de haleto com o exciting: DFT, DFT-1/2, SOC, BSE e eficiência

Guia e scripts para calcular o gap e as propriedades ópticas de perovskitas de haleto (o exemplo é o CsSnBr₃, em 7
polimorfos) com o código [exciting](https://www.exciting-code.org/), rodando no supercomputador Lise (NHR@ZIB).

O caminho é o de uma iniciação científica: tutoriais do exciting, depois DFT, DFT-1/2, acoplamento spin-órbita (SOC),
equação de Bethe-Salpeter (BSE) e, por fim, a eficiência máxima de uma célula solar. Siga as etapas na ordem.

## Antes de começar

- **Python 3** com `numpy`, `scipy` e `matplotlib`. Para a eficiência, também o `pvlib`; use um ambiente separado:
  ```bash
  python3 -m venv .venv
  .venv/bin/pip install numpy scipy matplotlib pvlib
  ```
- **Conta no Lise:** peça ao orientador a entrada no projeto do grupo e siga [`docs/lise-acesso.md`](docs/lise-acesso.md).
- **exciting local (opcional):** para os tutoriais, há um container em [`container/`](container/) e os scripts
  `bin/build-exciting.sh` e `bin/run-exciting.sh`.

## Organização das pastas

Os scripts esperam esta estrutura, que você cria no seu próprio repositório de trabalho:

| pasta | o que é |
|---|---|
| `runs/semana-NN/<material>-<fase>-<nível>/` | os cálculos, um por pasta (`input.xml`, `job.slurm`, saídas) |
| `estruturas/<material>/POSCAR.<fase>` | as geometrias de partida |
| `registros/semana-NN/` | o registro de cada semana; modelo em [`registros/_template/`](registros/_template/) |
| `bin/` | os scripts |

## As etapas

### 1. Tutoriais do exciting

Faça os tutoriais oficiais em https://www.exciting-code.org/, nesta ordem. Em [`01-tutoriais/`](01-tutoriais/) estão as
entradas que usei em cada um, sem as saídas.

| pasta | assunto |
|---|---|
| `diamond`, `nacl`, `exercicios` | primeiro cálculo: estado fundamental |
| `diamante-conv` | convergência em `ngridk` e `rgkmax` |
| `Al-via-excitingscripts` | metal, bandas e densidade de estados |
| `XC-functionals` | funcionais de troca e correlação (LDA, PBEsol) |
| `spin-tutorial` | magnetismo (Fe bcc) |
| `lda-1-2` | DFT-1/2: escolha do raio de corte (Si, GaN) |
| `LiF-BSE-tutorial` | BSE no LiF |
| `exploracao-inicial` | scripts de Python para conceitos básicos (estrutura, gap, éxciton) |

Na pasta `01-tutoriais`, troque `CAMINHO/DO/exciting/species` pelo caminho das espécies na sua instalação.

### 2. O Lise

- Acesso e chave SSH: [`docs/lise-acesso.md`](docs/lise-acesso.md).
- Como o Lise funciona (partições, custo, disco): [`docs/lise.md`](docs/lise.md).
- Scripts em [`bin/lise/`](bin/lise/): `enviar.sh`, `submeter.sh`, `estado.sh`, `trazer.sh`, `trazer-terminados.sh` e
  `limpar.sh`. Copie `bin/lise/lise.conf.exemplo` para `bin/lise/lise.conf` e preencha usuário, conta e e-mail.
- O `job.slurm` de cada pasta sai do `bin/lise/criar-job.py`.
- Em [`.vscode/tasks.json`](.vscode/tasks.json), há tasks do VS Code para enviar, submeter e trazer.

### 3. DFT (PBE)

- Converta o POSCAR no bloco `<structure>`: `bin/poscar2xml.py`. Nunca escreva a estrutura à mão.
- Monte a pasta de cada fase: `bin/montar-fase.py`. Confira com `bin/conferir-estrutura.py` e `bin/simetria-poscar.py`.
- Convergência de parâmetros: `bin/convergir.py`, com `bin/plot-convergencia.py`. Guarde os valores com `bin/parametros.py`.
- Leia o resultado: `bin/resultado.py`. Bandas e DOS: `bin/montar-bandas.py` e `bin/plot-bandas.py`.

### 4. DFT-1/2

- Correção no halogênio, com ionização 0,5. O raio de corte (`r_cut`) ótimo é o que maximiza o gap: faça uma varredura
  grossa e depois um refino, uma por fase.
- No build do grupo (`dft05`), os parâmetros vão no `<shell>`:
  ```xml
  <dfthalfparam>
    <shell number="0" ionization="0.5" cut="3.3" ampl="1" exponent="8"/>
  </dfthalfparam>
  ```
  Na sintaxe antiga (módulo padrão do Lise e tutorial), `cut`, `ampl` e `exponent` ficam no `<dfthalfparam>`.

### 5. SOC

- Espécies para o SOC (`svlo`): `bin/gerar-especies-soc.py`.
- PBE-1/2 e PBE-1/2+SOC de uma fase, no build do grupo: `bin/montar-pbe12-soc.py`.

### 6. BSE

- Em 4 etapas encadeadas (`--dependency=afterok`): `bin/montar-bse.py`.
- `--desde`, `--ate`, `--paralelo` e `--tempo` permitem refazer só algumas etapas e mudar o número de nós.
- Fases grandes: aumentar os nós da etapa 03 (`scrcoulint`) e da 04 (`bse`) reduz bem o tempo.
- Confira os limites do `nstlbse` no `EIGVAL.OUT`: `vi` cerca de 0,15 Ha abaixo do topo da valência e o último índice da
  condução cerca de 0,2 Ha acima.
- Depois de trazer os resultados, apague no Lise os arquivos gigantes (`SCCLI`, `EXCLI`): `bin/lise/limpar.sh`.
- Análise: `bin/otica.py`, `bin/tabela-bse.py`, `bin/plot-exciton-weights.py` e `bin/exciton-raio.py`.

### 7. Eficiência máxima (SLME)

- Equações: Yu & Zunger, *PRL* 108, 068701 (2012).
- Programa em [`eficiencia/`](eficiencia/): `eficiencia_funcoes.py` e `eficiencia_principal.py`. O
  `eficiencia_espessura.py` é a adaptação para a estrutura de pastas acima e gera o gráfico de eficiência × espessura:
  ```bash
  .venv/bin/python eficiencia/eficiencia_espessura.py
  ```
  Ajuste os caminhos das fases no começo do arquivo.