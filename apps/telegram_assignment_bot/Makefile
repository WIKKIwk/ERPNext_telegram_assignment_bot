COMPOSE = docker compose

.PHONY: run
run:
	$(COMPOSE) up --build

.PHONY: up
up: run

.PHONY: down
down:
	$(COMPOSE) down

.PHONY: logs
logs:
	$(COMPOSE) logs -f assignment_bot
