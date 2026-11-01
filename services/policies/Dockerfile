# Motor de politicas (PDP). Va como contenedor adjunto del backend, escuchando
# en la interfaz local: ver D-06 en docs/P2_Desviaciones_respecto_P1.md.
#
# La imagen oficial de OPA ya corre sin root.
FROM openpolicyagent/opa:1.4.2-static

COPY rego /politicas

# --addr se fija a loopback a proposito: el motor no debe ser alcanzable desde
# fuera de la instancia. La frontera F4 pasa de ser de red a ser de proceso.
CMD ["run", "--server", "--addr=127.0.0.1:8181", "/politicas"]
