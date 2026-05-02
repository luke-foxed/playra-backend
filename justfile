# Build production image
build:
    docker build -t playra-backend .

# Run dev container (hot reload enabled)
dev:
    docker run --rm \
        -p 6543:6543 \
        --env-file .env \
        -v $(pwd):/app \
        playra-backend

# Same as dev but rebuild first
dev-rebuild:
    docker build -t playra-backend .
    docker run --rm \
        -p 6543:6543 \
        --env-file .env \
        -v $(pwd):/app \
        playra-backend

# Clean run (no volume, like production test)
run:
    docker run --rm \
        -p 6543:6543 \
        --env-file .env \
        playra-backend

# Shell into container
shell:
    docker run --rm -it \
        --env-file .env \
        -v $(pwd):/app \
        playra-backend bash

# ruff lint (inside container)
lint:
    docker run --rm \
      -v $(pwd):/app \
      playra-backend ruff check .

# fix lint issues
lint-fix:
    docker run --rm \
      -v $(pwd):/app \
      playra-backend ruff check . --fix

# type check (mypy)
typecheck:
    docker run --rm \
      -v $(pwd):/app \
      playra-backend mypy .

# Stop all running containers of this image
stop:
    docker ps -q --filter ancestor=playra-backend | xargs -r docker stop