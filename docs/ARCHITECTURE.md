# ARCHITECTURE

Projeto: `asteroids_single-player`

## 1. Objetivo

Este documento descreve a arquitetura atual real do projeto.

Escopo:
- Código Python em arquivos na raiz
- Documentação em `docs/`
- Assets em `assets/`

Este projeto ainda é single-player.

## 2. Estrutura Atual do Repositório

Estrutura existente hoje:

```text
asteroids_single-player/
├── assets/
│   └── sounds/
├── docs/
│   └── ARCHITECTURE.md
├── audio.py
├── commands.py
├── config.py
├── controls.py
├── game.py
├── main.py
├── sprites.py
├── systems.py
└── utils.py
```

Arquivos de áudio atuais em `assets/sounds/`:
- `asteroid_explosion.wav`
- `player_shoot.wav`
- `ship_explosion.wav`
- `thrust_loop.wav`
- `ufo_shoot.wav`
- `ufo_siren_big.wav`
- `ufo_siren_small.wav`

## 3. Responsabilidades por Arquivo

### `main.py`

Ponto de entrada.

Responsabilidades atuais:
- Importa `Game` de `game.py`
- Executa `Game().run()`

### `game.py`

Orquestra loop, cenas e integração com pygame.

Responsabilidades atuais:
- Inicialização do pygame e mixer
- Criação de janela, relógio e fontes
- Controle de cenas (`menu`, `play`, `game_over`)
- Leitura de eventos e encerramento do jogo
- Uso de `InputMapper` para converter input em comando
- Chamada de `World.update(dt, commands)`
- Desenho de menu, game over e mundo
- Execução de áudio a partir de `world.events`
- Controle de loops de áudio (thrust e sirene UFO)

### `systems.py`

Núcleo de regras do jogo (`World`).

Responsabilidades atuais:
- Estado do jogo: naves, tiros, asteroides, UFOs, score, vidas, wave
- Spawn de jogador, asteroides e UFO
- Aplicação de comandos por `player_id`
- Atualização da simulação por frame
- Tratamento de colisões
- Regras de pontuação, morte e game over
- Geração de eventos de domínio em `world.events`
- Draw do HUD e sprites do mundo

### `sprites.py`

Entidades do jogo baseadas em `pygame.sprite.Sprite`.

Responsabilidades atuais:
- Classes: `Ship`, `Asteroid`, `Bullet`, `UFO`
- Física e atualização local de cada entidade
- Regras de tiro de `Ship` e `UFO`
- Desenho de cada entidade (`draw`)
- Constante `UFO_BULLET_OWNER`

### `controls.py`

Mapeamento de input para comando do jogador.

Responsabilidades atuais:
- Classe `InputMapper`
- Captura de eventos `KEYDOWN` para `shoot` e `hyperspace`
- Leitura de teclas contínuas para rotação e thrust
- Construção de `PlayerCommand`

### `commands.py`

Contrato de intenção do jogador.

Responsabilidades atuais:
- `dataclass` imutável `PlayerCommand`
- Flags: `rotate_left`, `rotate_right`, `thrust`, `shoot`, `hyperspace`

### `audio.py`

Carregamento de efeitos sonoros.

Responsabilidades atuais:
- `SoundPack` com referências de `pygame.mixer.Sound`
- `load_sounds(base_path)` para carregar sons a partir de `config.py`

### `utils.py`

Utilitários matemáticos e de desenho.

Responsabilidades atuais:
- Alias `Vec` (`pygame.math.Vector2`)
- Helpers de vetor e geometria (`wrap_pos`, `angle_to_vec`, etc.)
- Helpers de desenho (`draw_poly`, `draw_circle`, `draw_text`)

### `config.py`

Configuração central do jogo.

Responsabilidades atuais:
- Constantes de tela, FPS e IDs
- Parâmetros de nave, tiro, asteroide e UFO
- Cores e caminhos de assets
- Nomes dos arquivos de som

### `docs/`

Documentação do projeto.

Estado atual:
- Contém este documento (`ARCHITECTURE.md`)

### `assets/`

Recursos estáticos do jogo.

Estado atual:
- Pasta `sounds/` com efeitos WAV usados pelo cliente pygame

## 4. Dependências Entre Módulos (Atual)

Fluxo principal de imports observado hoje:
- `main.py` -> `game.py`
- `game.py` -> `config.py`, `audio.py`, `controls.py`, `systems.py`,
  `utils.py`
- `systems.py` -> `config.py`, `commands.py`, `sprites.py`, `utils.py`
- `sprites.py` -> `config.py`, `commands.py`, `utils.py`
- `controls.py` -> `commands.py`
- `audio.py` -> `config.py`
- `utils.py` -> `config.py`

Regra de saúde arquitetural:
- Evitar imports circulares

## 5. Arquitetura Alvo (planejada)

Planejamento futuro (ainda não implementado neste repositório):
- `core/`: regras puras de jogo, sem pygame
- `client/`: input, render e áudio com pygame

Importante:
- As pastas `core/` e `client/` não existem hoje.
- A arquitetura em produção atual é a descrita nas seções 2 a 4.
