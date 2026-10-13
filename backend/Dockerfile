# Layered for fast rebuilds: deps first, sources last.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/backend

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Build args let you turn heavy tiers off (paired with SEMANTIC_ENABLED=false):
#   docker compose build --build-arg INSTALL_ML=0
ARG INSTALL_NLP=1
ARG INSTALL_ML=1

COPY requirements.txt requirements-nlp.txt requirements-ml.txt requirements-dev.txt ./
RUN pip install -r requirements.txt -r requirements-dev.txt
RUN if [ "$INSTALL_NLP" = "1" ]; then \
        pip install -r requirements-nlp.txt && python -m spacy download en_core_web_sm; \
    fi
RUN if [ "$INSTALL_ML" = "1" ]; then pip install -r requirements-ml.txt; fi

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
