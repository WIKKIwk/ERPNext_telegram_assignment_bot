from __future__ import annotations

from . import AssignmentBot, load_assignment_config


def main() -> None:
    config = load_assignment_config()
    bot = AssignmentBot(config)
    bot.application.run_polling()


if __name__ == "__main__":
    main()
