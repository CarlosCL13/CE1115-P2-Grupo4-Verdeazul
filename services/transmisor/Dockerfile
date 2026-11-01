# Transmisor y trabajos programados (D-11). Lo invoca Cloud Scheduler.
FROM python:3.15-slim AS build

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.15-slim

RUN groupadd --system --gid 10001 verdeazul \
 && useradd --system --uid 10001 --gid verdeazul --no-create-home verdeazul

COPY --from=build /install /usr/local
WORKDIR /app
COPY app ./app

USER 10001:10001

ENV PORT=8082
EXPOSE 8082

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
