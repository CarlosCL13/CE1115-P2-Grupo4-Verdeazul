# Motor de autorización (F3)

Acá vive el cliente del punto de decisión: el lado Python que le pregunta al
motor de políticas si un sujeto puede hacer algo. Las políticas en Rego están en
[`services/policies/rego/`](../../../policies/rego/), no acá.

| Archivo | Qué hace |
|---|---|
| `Modelos_opa.py` | `Sujeto`, `Objeto` y `Decision`, las tres piezas de la pregunta |
| `Servicio_opa.py` | `servicio_consulta_autorizacion()`: arma la pregunta, agrega `contexto.hoy` y traduce la respuesta |
| `Cliente_opa.py` | Habla con OPA en `127.0.0.1:8181`. Si no responde, la respuesta es no |

Cómo se pregunta y qué atributos manda cada condición está en el
[contrato 02](../../../../contracts/02-autorizacion.md).

Los endpoints no llaman a `servicio_consulta_autorizacion()` directo, sino a
`autorizar()` y `consultar()` de
[`app/auth/dependencias.py`](../auth/dependencias.py). `autorizar()` convierte a
texto todo id que se mande al motor, registra la denegación en la bitácora y
responde 403; `consultar()` solo pregunta, para filtrar listados fila por fila.

La matriz completa, 84 permisos que se conceden y 884 que se niegan, se prueba
en [`tests/matriz/`](../../../../tests/matriz/) en cada pull request.
