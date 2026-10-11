FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends ngspice \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 sim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY tests ./tests
USER sim
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --retries=20 CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
