FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY mirror_sync ./mirror_sync
COPY sync.py ./
COPY README.md ./README.md

USER app

ENTRYPOINT ["python", "sync.py"]
