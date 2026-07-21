.PHONY: setup up up-d down logs migrate test test-local typecheck lint shell-api shell-db generate-secret

generate-secret:
	@echo ""
	@echo "Add this line to your .env file:"
	@echo ""
	@printf "SECRET_KEY=%s\n" "$$(openssl rand -hex 32)"
	@echo ""

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

typecheck:
	cd web && npm run typecheck

lint:
	docker compose exec api ruff check /app/ || ruff check api/

shell-api:
	docker compose exec api /bin/bash

shell-db:
	docker compose exec db psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}
