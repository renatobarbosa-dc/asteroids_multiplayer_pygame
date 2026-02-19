"""Entrypoint do jogo."""

from client.game import Game


def main() -> None:
    Game().run()


if __name__ == "__main__":
    main()
