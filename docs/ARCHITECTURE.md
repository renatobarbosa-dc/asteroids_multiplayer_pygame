# ARCHITECTURE

Projeto: `asteroids_single-player`

## 1. Objetivo

Este documento descreve a arquitetura atual real do projeto.

Escopo:
- Código Python em `core/`, `client/` e `main.py`
- Documentação em `docs/`
- Assets em `assets/`

Este projeto ainda é single-player.

## 2. Estrutura Atual do Repositório

Estrutura existente hoje:

```text
asteroids_single-player/
├── assets/
│   └── sounds/
├── client/
│   ├── audio.py
│   ├── controls.py
│   ├── game.py
│   └── renderer.py
├── core/
│   ├── commands.py
│   ├── config.py
│   ├── entities.py
│   ├── utils.py
│   └── world.py
├── docs/
│   └── ARCHITECTURE.md
└── main.py
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
- Importa `Game` de `client.game`
- Executa `Game().run()`

### `client/game.py`

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

### `client/renderer.py`

Renderização do cliente.

Responsabilidades atuais:
- Limpeza da tela
- Desenho das cenas (`menu`, `game_over`)
- Desenho do mundo a partir dos sprites expostos por `World`
- Desenho do HUD

### `client/controls.py`

Mapeamento de input local para comando do jogador.

Responsabilidades atuais:
- Classe `InputMapper`
- Captura de eventos `KEYDOWN` para `shoot` e `hyperspace`
- Leitura de teclas contínuas para rotação e thrust
- Construção de `PlayerCommand`

### `client/audio.py`

Carregamento de efeitos sonoros.

Responsabilidades atuais:
- `SoundPack` com referências de `pygame.mixer.Sound`
- `load_sounds(base_path)` para carregar sons a partir de `core.config`

### `core/world.py`

Núcleo de regras do jogo (`World`).

Responsabilidades atuais:
- Estado do jogo: naves, tiros, asteroides, UFOs, score, vidas, wave
- Spawn de jogador, asteroides e UFO
- Aplicação de comandos por `player_id`
- Atualização da simulação por frame
- Tratamento de colisões
- Regras de pontuação, morte e game over
- Geração de eventos de domínio em `world.events`

### `core/entities.py`

Entidades do jogo baseadas em `pygame.sprite.Sprite`.

Responsabilidades atuais:
- Classes: `Ship`, `Asteroid`, `Bullet`, `UFO`
- Física e atualização local de cada entidade
- Regras de tiro de `Ship` e `UFO`
- Constante `UFO_BULLET_OWNER`

### `core/commands.py`

Contrato de intenção do jogador.

Responsabilidades atuais:
- `dataclass` imutável `PlayerCommand`
- Flags: `rotate_left`, `rotate_right`, `thrust`, `shoot`, `hyperspace`

### `core/utils.py`

Utilitários matemáticos.

Responsabilidades atuais:
- Alias `Vec` (`pygame.math.Vector2`)
- Helpers de vetor e geometria (`wrap_pos`, `angle_to_vec`, etc.)

### `core/config.py`

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
- `main.py` -> `client.game`
- `client.game` -> `client.audio`, `client.controls`, `client.renderer`,
  `core.config`, `core.world`
- `client.controls` -> `core.commands`
- `client.audio` -> `core.config`
- `client.renderer` -> `core.config`, `core.entities`
- `core.world` -> `core.config`, `core.commands`, `core.entities`,
  `core.utils`
- `core.entities` -> `core.config`, `core.commands`, `core.utils`
- `core.utils` -> `core.config`

Regra de saúde arquitetural:
- Evitar imports circulares

## 5. Observações Arquiteturais

A separação atual entre `core/` e `client/` já existe e está em uso.

Importante:
- `client/` concentra integração com pygame para input, render e áudio.
- `core/` concentra regras, estado do jogo e entidades.
- `core/` ainda depende de `pygame.sprite` e `pygame.math.Vector2`, então
  não é uma camada totalmente agnóstica de pygame.
- O fluxo de renderização atual passa por `client.renderer`; `World` não é
  responsável por desenhar HUD ou sprites.
