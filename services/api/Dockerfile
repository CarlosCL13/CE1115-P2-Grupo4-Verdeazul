# Imagen del backend (PEP). Construccion en dos etapas para que la imagen
# final no cargue con el compilador ni la cache de pip.
FROM python:3.15-slim AS build

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.15-slim

# El contenedor no corre como root. Es un control de minimo privilegio
# aplicado a la infraestructura, y el enunciado lo revisa explicitamente.
RUN groupadd --system --gid 10001 verdeazul \
 && useradd --system --uid 10001 --gid verdeazul --no-create-home verdeazul

COPY --from=build /install /usr/local
WORKDIR /app
COPY app ./app

USER 10001:10001

# Cloud Run inyecta PORT. El valor por defecto solo sirve para correr local.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
