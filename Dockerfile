FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p logs media

# Make start.sh executable
RUN chmod +x start.sh

ENV PYTHONUNBUFFERED=1

CMD ["./start.sh"]