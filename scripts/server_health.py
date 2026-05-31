"""Verifica se o servidor Asteroids Multiplayer esta no ar.

Abre uma conexao WebSocket, manda um HELLO com token invalido de
proposito e confirma que o servidor responde com REJECT. Isso prova
que o *servidor do jogo* esta vivo e processando o protocolo, e nao
apenas que a porta TCP esta aberta.

Nao precisa de token valido: e um health check seguro para o aluno
monitor rodar antes da aula, sem usar credencial de ninguem.

Saida: uma linha "SERVIDOR NO AR" ou "SERVIDOR FORA DO AR", e exit
code 0 (vivo) / 1 (fora), para uso em scripts ou cron.

So depende de ``websockets`` (ja instalado pelo requirements.txt).

Uso:
    python scripts/server_health.py
    python scripts/server_health.py --host 191.252.102.250 --port 8765
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from websockets.sync.client import connect

DEFAULT_HOST = "191.252.102.250"
DEFAULT_PORT = 8765
TIMEOUT = 8.0


def check(host: str, port: int) -> bool:
    """Retorna True se o servidor Asteroids responder o handshake."""
    url = f"ws://{host}:{port}"
    hello = json.dumps(
        {
            "type": "hello",
            "tick": 0,
            "seq": 0,
            "data": {"token": "healthcheck"},
        }
    )
    t0 = time.perf_counter()
    try:
        with connect(url, open_timeout=TIMEOUT) as ws:
            ws.send(hello)
            reply = json.loads(ws.recv())
    except TimeoutError:
        print(
            f"SERVIDOR FORA DO AR -- {url} nao respondeu em "
            f"{TIMEOUT:.0f}s (porta filtrada ou servidor caido)."
        )
        return False
    except ConnectionRefusedError:
        print(
            f"SERVIDOR FORA DO AR -- {url} recusou a conexao "
            "(porta fechada; servidor provavelmente parado)."
        )
        return False
    except OSError as exc:
        print(f"SERVIDOR FORA DO AR -- nao cheguei em {url}: {exc}")
        return False

    rtt = (time.perf_counter() - t0) * 1000
    if reply.get("type") == "reject":
        print(f"SERVIDOR NO AR -- {url} respondeu em {rtt:.0f} ms.")
        return True

    print(f"RESPOSTA INESPERADA de {url}: {reply!r}")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Testa se o servidor Asteroids Multiplayer esta no ar."
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    sys.exit(0 if check(args.host, args.port) else 1)


if __name__ == "__main__":
    main()
