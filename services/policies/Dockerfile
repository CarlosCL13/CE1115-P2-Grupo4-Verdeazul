
# Imagen oficial de OPA en DockerHub
FROM openpolicyagent/opa:1.4.2-static

# Se copia las políticas de OPA al contenedor (se ignoran los tests)
COPY rego /politicas

# Comando para ejecutar OPA con las políticas copiadas (la imagen ya trae un entrypoint que ejecuta OPA)
CMD ["run", "--server", "--addr=127.0.0.1:8181", "/politicas"]
