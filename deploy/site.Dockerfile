# Imagem do SITE (Flask + gunicorn). Sem Chrome — nao precisa das senhas dos portais.
# Aponte o Dockerfile Path deste servico para: deploy/site.Dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/

# Railway injeta a porta em $PORT. gunicorn NAO liga o debug (seguro em producao).
CMD ["sh", "-c", "gunicorn --chdir src app:app --bind 0.0.0.0:${PORT:-5000}"]
