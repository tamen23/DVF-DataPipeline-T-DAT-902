.PHONY: help up build down restart ps logs clean

help:           ## show available commands
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

up:             ## boot the whole platform (build images on first run)
	docker compose up -d --build

build:          ## rebuild all images
	docker compose build

down:           ## stop everything (data volumes are kept)
	docker compose down

restart: down up ## stop then boot again

ps:             ## show service status
	docker compose ps

logs:           ## tail all logs (Ctrl+C to quit)
	docker compose logs -f --tail=100

clean:          ## stop everything AND DELETE all data volumes
	docker compose down -v
