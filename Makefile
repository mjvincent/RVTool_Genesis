.PHONY: setup up up-d down logs migrate test test-local shell-api shell-db

setup:
	./setup.sh

up:
	docker compose up --build

up-d:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	docker compose exec api alembic upgrade head

test:
	docker compose exec api pytest /tests/ -v

test-local:
	BASE_URL=http://localhost:8001 python -m pytest tests/ -v

shell-api:
	docker compose exec api /bin/bash

shell-db:
	docker compose exec db psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}
