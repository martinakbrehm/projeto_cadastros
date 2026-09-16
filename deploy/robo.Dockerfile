# Imagem do ROBO (Selenium + Chromium) para rodar como Cron no Railway.
# Aponte o Dockerfile Path deste servico para: deploy/robo.Dockerfile
FROM python:3.12-slim

# Chromium + driver do sistema (versoes casadas; evita download em runtime).
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium chromium-driver \
        fonts-liberation ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Ambiente do robo na nuvem: oculto e usando o Chromium do sistema.
ENV HEADLESS=1 \
    CHROME_BINARY=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/

# Processa a fila nos DOIS portais e encerra (cada um checa a fila antes de
# abrir o Chrome). Ideal para um Cron Job do Railway.
CMD ["python", "src/robo.py", "--portal", "ambos"]
