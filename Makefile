.PHONY: up down logs migrate test shell-api shell-db

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	docker compose exec api alembic upgrade head

test:
	docker compose exec api pytest

shell-api:
	docker compose exec api /bin/bash

shell-db:
	docker compose exec db psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}
