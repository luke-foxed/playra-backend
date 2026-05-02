FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential

COPY . /app

RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -e .

EXPOSE 6543

CMD ["pserve", "development.ini", "--reload"]