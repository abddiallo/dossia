FROM python:3.12-slim

# LibreOffice (conversion PDF), poppler (aperçus), polices métriquement compatibles
# avec Calibri / Cambria (Carlito, Caladea) et Arial / Times (Liberation) pour une mise en page fidèle.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer-nogui poppler-utils \
        fonts-crosextra-carlito fonts-crosextra-caladea fonts-liberation2 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV DATA_DIR=/data PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
