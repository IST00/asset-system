FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=UTC

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.lock .
RUN python -m pip install --no-cache-dir pip==25.2 \
    && python -m pip install --no-cache-dir --require-hashes -r requirements.lock

COPY . .

RUN chmod +x docker-entrypoint.sh

EXPOSE 8080 8081

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
