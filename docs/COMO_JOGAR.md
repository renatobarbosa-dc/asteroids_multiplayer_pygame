# Como jogar — Asteroids Multiplayer

Guia rápido para entrar no servidor da turma usando o **VS Code**.

**Você já precisa ter:** Python 3.10–3.13 e o VS Code com a extensão **Python** (da Microsoft).

**O professor te passa:** seu **token** e sua **sala** (um número de 0 a 7).

| Dado | Valor |
|---|---|
| Servidor (host) | `191.252.102.250` |
| Porta | `8765` |
| Token | _(o professor te dá — ex.: `Zk3pQ9mXr2T`)_ |
| Sala | _(o professor te dá: 0 a 7)_ |

## 1. Baixar o projeto

Escolha uma das formas:

- **Clonar pelo VS Code:** `Ctrl+Shift+P` → digite **Git: Clone** → cole `https://github.com/jucimarjr/asteroids_multiplayer` → escolha uma pasta → **Open**.
- **Ou baixar o ZIP:** no GitHub, botão verde **Code → Download ZIP**, extraia, e no VS Code use **File → Open Folder** na pasta extraída.

**Já baixou em uma aula anterior?** Atualize antes de jogar para pegar as últimas melhorias: o controle da nave ficou bem mais responsivo, e as outras naves se movem mais suaves, mesmo com o servidor distante. No VS Code: **Source Control** (`Ctrl+Shift+G`) → menu **⋯** → **Pull**. No terminal: `git pull`. Quem usou o ZIP precisa baixar o ZIP de novo.

## 2. Criar o ambiente e instalar as dependências

Deixe o VS Code cuidar disso:

1. `Ctrl+Shift+P` → **Python: Create Environment**
2. Escolha **Venv**
3. Escolha um **Python 3.10–3.13**
4. Marque **`requirements.txt`** para instalar

Ele cria a pasta `.venv`, seleciona como interpretador e instala o `pygame` e o `websockets`. Espere terminar.

### (Alternativa) Pelo terminal integrado

Abra o terminal com `Ctrl` + crase (`` ` ``) e rode:

| Passo | Windows | macOS / Linux |
|---|---|---|
| Criar | `py -m venv .venv` | `python3 -m venv .venv` |
| Ativar | `.venv\Scripts\Activate.ps1` | `source .venv/bin/activate` |
| Instalar | `pip install -r requirements.txt` | `pip install -r requirements.txt` |

No Windows, se o PowerShell recusar o `Activate.ps1`, use o **Prompt de Comando** (`.venv\Scripts\activate.bat`) ou simplesmente o método do VS Code acima.

## 3. Entrar no jogo

No terminal integrado (`Ctrl` + crase) — com o `.venv` já ativo — rode, **trocando** token, sala e nome:

```
python -m multiplayer.player --host 191.252.102.250 --port 8765 --token SEU_TOKEN --room SUA_SALA --name SEU_NOME
```

Exemplo:

```
python -m multiplayer.player --host 191.252.102.250 --port 8765 --token Zk3pQ9mXr2T --room 0 --name Ana
```

Abre a janela do jogo. **A partida começa quando 2 jogadores entram na mesma sala.** Use um nome de uma palavra (sem espaços).

## Controles

| Tecla | Ação |
|---|---|
| ← → | Girar |
| ↑ | Acelerar |
| ↓ | Escudo |
| Espaço | Atirar |
| Shift esquerdo | Hiperespaço |
| Shift direito | Liga/desliga o som |
| Enter | Reiniciar (na tela de fim de partida) |
| Esc ou Q | Sair |

## O servidor está no ar?

Antes de achar que o problema é com você, dá para checar o servidor em um comando. No terminal integrado (com o `.venv` ativo):

```
python scripts/server_health.py
```

- **No ar:** `SERVIDOR NO AR -- ws://191.252.102.250:8765 respondeu em 730 ms.`
- **Fora do ar:** `SERVIDOR FORA DO AR -- ...` (porta fechada ou servidor desligado fora do horário da aula).

Não precisa de token: é seguro rodar a qualquer momento. Se der **no ar** mas você ainda não entra, o problema é o seu token, sua sala ou seu nome — veja a tabela abaixo.

## Deu problema?

| Mensagem / sintoma | O que fazer |
|---|---|
| `unauthorized` | Token errado — confira com o professor |
| `room_full` | Sua sala já tem 8 jogadores — confirme seu número de sala |
| `invalid_room` | Sala fora do intervalo 0–7 |
| `connection refused` / trava ao conectar | Rode `python scripts/server_health.py` (acima) para saber se o servidor está no ar; confira também o IP e a porta |
| `pygame` não instala | Confirme `python --version` entre 3.10 e 3.13 (evite 3.14+) |
| A janela não abre | Rode numa máquina com tela (não por acesso remoto/SSH) |
