.PHONY: run bot logs down

run bot:
	$(MAKE) -C apps/telegram_assignment_bot run

logs:
	$(MAKE) -C apps/telegram_assignment_bot logs

down:
	$(MAKE) -C apps/telegram_assignment_bot down
