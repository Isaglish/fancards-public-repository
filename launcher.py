import json
from logging import Formatter
from typing import Any

from bot import Fancards


def _load_config() -> dict[str, Any]:
    with open("source/json/config.json", "r") as f:
        config = json.load(f)

    return config


def main() -> None:
    bot = Fancards(
        config=_load_config(),
        cmd_prefix="fan?",
        dev_mode=False
    )
    bot.run(
        bot.config["discord_api_token_dev"] if bot.dev_mode else bot.config["discord_api_token"],
        log_formatter=Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', '%Y-%m-%d %H:%M:%S', style='{')
    )


if __name__ == '__main__':
    main()
