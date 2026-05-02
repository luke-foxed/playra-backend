FROM python:3.11-slim

WORKDIR /app

# system deps
RUN apt-get update && apt-get install -y build-essential

# install dependencies first for caching
COPY pyproject.toml setup.py* /app/

RUN pip install --upgrade pip setuptools wheel
RUN pip install -e .

# 👇 add dev tooling (safe addition)
RUN pip install ruff mypy

# IMPORTANT: do NOT COPY full code here for dev
# (we mount it via volume instead)

EXPOSE 6543

CMD ["pserve", "development.ini", "--reload"]