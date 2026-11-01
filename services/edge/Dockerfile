# Servicio de borde: sirve la interfaz y es el unico expuesto a internet.
# Construccion en dos etapas para que la imagen final no cargue con pip.
FROM python:3.14-slim AS build

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.14-slim

# El contenedor no corre como root. Control de minimo privilegio aplicado a
# la infraestructura, y el enunciado lo revisa explicitamente.
RUN groupadd --system --gid 10001 verdeazul \
 && useradd --system --uid 10001 --gid verdeazul --no-create-home verdeazul

COPY --from=build /install /usr/local
WORKDIR /app
COPY app ./app
COPY templates ./templates
COPY static ./static

USER 10001:10001

ENV PORT=8081
EXPOSE 8081

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
