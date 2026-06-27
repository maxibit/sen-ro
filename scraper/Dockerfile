FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scraper.py healthcheck.py ./

HEALTHCHECK --interval=60s --timeout=10s --start-period=90s --retries=3 \
  CMD python healthcheck.py

CMD ["python", "-u", "scraper.py"]
