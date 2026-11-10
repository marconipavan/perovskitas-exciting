# Acesso ao Lise (NHR@ZIB) — passo a passo

Do zero até o primeiro login e o levantamento do ambiente. Tudo sai da página *User
access* do [manual do NHR@ZIB](https://user.nhr.zib.de); o que funciona no Lise depois do login está em
[lise.md](lise.md).

**Antes de começar:** a conta NHR tem de estar aprovada, e você precisa do **nome de
usuário** e da **senha do portal**. Todos os comandos rodam **no seu computador**, salvo
onde estiver escrito "no Lise".

São duas senhas diferentes, e é fácil confundir:

| | serve para | onde é digitada |
|---|---|---|
| **senha do portal** | entrar em portal.nhr.zib.de | só no navegador |
| **passphrase da chave** | destravar a chave SSH | no terminal, a cada `ssh`/`scp` |

---

## 1. Gerar o par de chaves

A chave é **só para o Lise**, e a passphrase é obrigatória.

```bash
ssh-keygen -t rsa -b 4096 -C "Lise - meu computador" -f ~/.ssh/id_rsa_nhr
```

Escolha uma passphrase forte e **diferente da senha do portal**. O comando cria dois
arquivos:

| arquivo | o que é | para onde vai |
|---|---|---|
| `~/.ssh/id_rsa_nhr` | chave **privada** | **nunca sai do seu computador** |
| `~/.ssh/id_rsa_nhr.pub` | chave **pública** | portal do NHR (passo 3) |

## 2. Conferir que a passphrase ficou

```bash
ssh-keygen -y -f ~/.ssh/id_rsa_nhr
```

**Tem de pedir a passphrase.** Se imprimir a chave direto, sem pedir, crie uma agora:

```bash
ssh-keygen -p -f ~/.ssh/id_rsa_nhr
```

## 3. Enviar a chave pública pelo portal

Pôr a chave à mão no `authorized_keys` do Lise **não funciona**: o envio é só pelo portal.

1. Abra https://portal.nhr.zib.de e clique em **SSH Keys**.
2. Entre com o usuário e a **senha do portal**.
3. Clique em **Request upload of a new key** e confirme as regras de segurança.
4. Chega um e-mail com um **link de uso único**. Abra o link.
5. Selecione **`~/.ssh/id_rsa_nhr.pub`**, o arquivo que termina em `.pub`. **Nunca o
   outro.** A pasta `.ssh` é oculta: no seletor de arquivos, Ctrl+H mostra os ocultos.
6. Clique em **Upload**.

Cada conta tem 7 vagas de chave. Se um dia for acessar de outro computador, gere outra
chave nele e envie também; não copie a privada de uma máquina para a outra.

## 4. Configurar os atalhos

São dois nós de login, cada um com o software da sua arquitetura:

| atalho | endereço | serve para |
|---|---|---|
| `genoa-login` | `genoa-login.nhr.zib.de` | partições `cpu-genoa` — o exemplo do manual |
| `blogin` | `blogin.nhr.zib.de` | partições `cpu-clx` — **onde vamos rodar** |

Troque `SEU_USUARIO` (nos dois lugares) e cole:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
cat >> ~/.ssh/config <<'EOF'

Host genoa-login
    Hostname genoa-login.nhr.zib.de
    User SEU_USUARIO
    IdentityFile ~/.ssh/id_rsa_nhr
    IdentitiesOnly yes

Host blogin
    Hostname blogin.nhr.zib.de
    User SEU_USUARIO
    IdentityFile ~/.ssh/id_rsa_nhr
    IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
```

- `IdentitiesOnly yes` não está no manual. Faz o ssh oferecer só esta chave, o que evita o
  erro *"Too many authentication failures"* quando há outras chaves carregadas.
- O manual só traz o nome curto `blogin`; o endereço completo é `blogin.nhr.zib.de`.

## 5. Primeiro login

```bash
ssh genoa-login
```

Na primeira vez aparece *"The authenticity of host … can't be established"* e uma
impressão digital (*fingerprint*). **Compare letra por letra** com a tabela oficial do
manual:

| nó | tipo | SHA256 |
|---|---|---|
| **genoa-login** | ED25519 | `8/hSIv0HfMDEy1gUQjVmb0cUMDztgacNfXSBUzcgCFM` |
| | ECDSA | `rusM3G/8eG7ZFLNJtvymL/wNHFGgkOFTMYCBk3yLiL8` |
| | RSA | `WulefLWFPRPPobUI6/+4bJpttV9SlQhZ0prEo8ELp1k` |
| **blogin** | ED25519 | `53WD36v+IjHObgS3DbjIi+zShcQ/MCAIqJNgJOlfR08` |
| | ECDSA | `pNGlm//LyjJZi6tX0mz5SPSs4IBkuyJI/iWI10JbhgE` |
| | RSA | `mrwKbHEz3pJCmvU7ZEXoIKxVRz0E9/4GDp3k41x4Q8g` |

- **Bateu:** digite `yes`. A impressão fica guardada em `~/.ssh/known_hosts` e não é
  perguntada de novo.
- **Não bateu:** **não digite `yes`.** Pode ser um ataque de intermediário. Pare e avise.

Depois ele pede a **passphrase da chave** (não a senha do portal), e você está no Lise.
Saia com `exit` e repita com o outro nó:

```bash
ssh blogin
```

### Conexão compartilhada: a passphrase uma vez por sessão

As tasks do Lise abrem várias conexões seguidas (enviar, conferir, submeter, consultar).
Sem isto, cada uma pede a passphrase. Acrescente ao `~/.ssh/config`:

```bash
cat >> ~/.ssh/config <<'EOF'

Host blogin genoa-login
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 4h
    ServerAliveInterval 60
    ServerAliveCountMax 3
EOF
```

- A **primeira** conexão (por exemplo, a aba "Lise (blogin)") pede a passphrase e abre um
  canal. As seguintes — tasks, `rsync`, `scp` — passam por ele sem pedir nada.
- O canal fica aberto por **4 h depois do último uso**, mesmo com a aba fechada.
- Para fechá-lo antes: `ssh -O exit blogin`.
- `ServerAlive*`: o ssh testa a conexão a cada minuto e fecha o canal em cerca de 3 min se
  o Lise não responder. Sem isso, um canal morto (notebook que dormiu ou trocou de rede)
  fica preso e **trava todas as conexões novas** — aconteceu em 01/10.
- Qualquer programa rodando com o seu usuário local pode usar o canal enquanto ele está
  aberto. Num computador pessoal isso é aceitável; num compartilhado, use um
  `ControlPersist` curto.

Alternativa sem canal compartilhado: `ssh-add ~/.ssh/id_rsa_nhr` no início da sessão
carrega a chave no agente, e as conexões deixam de pedir a passphrase enquanto o agente
estiver rodando.

## 6. Levantar o ambiente (no Lise)

Faça isto **nos dois nós**, porque o software de cada um é diferente. O bloco só lê
informações, não roda cálculo, e grava tudo num arquivo com o nome do nó
(`~/lise-ambiente-<nó>.txt`):

```bash
{
echo "== host";      hostname; whoami
echo "== HOME/WORK"; echo "HOME=$HOME"; echo "WORK=${WORK:-<nao definido>}"
echo "== cotas";     show-quota
echo "== grupos";    groups
echo "== particoes"; sinfo -s
echo "== contas";    sacctmgr -nP show assoc user=$USER format=account,partition,qos | head -20
echo "== modulos";   module -t avail 2>&1 | head -300
echo "== exciting?"; module -t avail 2>&1 | grep -iE 'exciting|elk'
} 2>&1 | tee ~/lise-ambiente-$(hostname -s).txt
```

O que cada parte responde:

| bloco | pergunta do checklist |
|---|---|
| `HOME/WORK`, `cotas` | HOME × WORK, e o espaço de cada um |
| `grupos`, `contas` | conta pessoal × projeto |
| `particoes` | partições e o **tempo máximo** de cada uma (coluna `TIMELIMIT`) |
| `modulos`, `exciting?` | programas instalados; se o exciting já existe |

## 7. Trazer os arquivos para o repositório

De volta ao seu computador (`exit`). Os dois nós enxergam o **mesmo HOME**, então um
`scp` só traz os dois arquivos, e de quebra testa a transferência:

```bash
scp 'blogin:lise-ambiente-*.txt' .
```

---

## Problemas comuns

Para qualquer falha de conexão, o diagnóstico começa por:

```bash
ssh -v genoa-login
```

| mensagem | causa provável | o que fazer |
|---|---|---|
| `Permission denied (publickey)` | a chave não foi enviada ainda, foi enviado o arquivo errado, ou o usuário está errado | conferir o passo 3 (tem de ser o `.pub`) e o `User` no `~/.ssh/config` |
| `Too many authentication failures` | o ssh ofereceu outras chaves antes | conferir `IdentitiesOnly yes` no `~/.ssh/config` |
| `WARNING: UNPROTECTED PRIVATE KEY FILE!` | permissões abertas demais na chave | `chmod 600 ~/.ssh/id_rsa_nhr` |
| `Bad owner or permissions on ~/.ssh/config` | idem, no arquivo de configuração | `chmod 600 ~/.ssh/config` |
| `REMOTE HOST IDENTIFICATION HAS CHANGED!` | a chave do servidor mudou, ou há interceptação | **não contornar.** Comparar com a tabela do passo 5 e avisar |
| pede **senha** em vez de passphrase | a chave não está sendo oferecida | conferir `IdentityFile` e rodar `ssh -v` |
| `ssh blogin` (ou uma task) **fica parado**, sem pedir nada | o canal compartilhado morreu, mas o processo mestre continua vivo | `ssh -O exit blogin`; se travar, `pgrep -af '\[mux\]'`, `kill <pid>` e apagar o `~/.ssh/cm-*`. Prevenção: `ServerAlive*` no `~/.ssh/config` |

## Regras de segurança do ZIB

- A chave é **dedicada ao Lise**: não use para outros servidores.
- A chave privada **tem passphrase** e **nunca** é enviada: nem ao Lise, nem ao portal,
  nem por e-mail.
- Uma chave por computador. Se perder um computador, remova a chave dele pelo portal
  (ou peça ao suporte, support@nhr.zib.de).
- Chaves de hardware (YubiKey, Nitrokey) são recomendadas, mas não obrigatórias.
