.PHONY: test build auth up logs
test:
	pytest -q
build:
	docker compose build
auth:
	docker compose run --rm telegram-uploader python -m app.auth
up:
	docker compose up -d
logs:
	docker compose logs -f telegram-uploader

