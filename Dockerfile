FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/
RUN pip install --upgrade pip setuptools wheel && pip install -e .

COPY . /app/
RUN pip install -e .

EXPOSE 6543

CMD ["pserve", "production.ini"]
