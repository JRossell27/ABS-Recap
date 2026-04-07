FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python -m py_compile app.py abs_service.py

EXPOSE 8080

CMD ["sh", "-c", "gunicorn -w ${WEB_CONCURRENCY:-1} -k gthread --threads ${GUNICORN_THREADS:-4} -b 0.0.0.0:${PORT:-8080} app:app"]
