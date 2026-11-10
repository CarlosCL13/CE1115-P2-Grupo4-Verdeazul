# Contrato 3: el evento de bitácora

Todo lo que pasa en el sistema genera un evento. El formato está congelado
porque los cinco frentes los emiten y uno solo los guarda.

## Cómo se emite

```python
from app.bitacora import registrar

registrar(
    accion="CERTIFICADO_EMITIDO",
    sujeto="u-42",
    objeto="O5:12",
    resultado="PERMITIDO",
    detalle={"medicion": "med-77", "huella_llave": "SHA256:abc..."},
)
```

Quien emite no sabe cómo se guarda. Eso es del transmisor (F5).

## Campos

| Campo | Tipo | Obligatorio | Qué lleva |
|---|---|---|---|
| `id` | uuid | sí | Lo pone la base |
| `momento` | timestamptz | sí | Lo pone la base, con `now()`. **Nunca la hora del cliente** |
| `accion` | str | sí | Verbo en mayúsculas: `SESION_INICIADA`, `MEDICION_APROBADA`, `CERTIFICADO_EMITIDO` |
| `sujeto` | str | sí | El `id` de quien actuó, o `ANONIMO` |
| `objeto` | str | sí | `O5:12`, el número de objeto y el id de la fila |
| `resultado` | str | sí | `PERMITIDO` o `DENEGADO` |
| `motivo` | str | si fue denegado | El `motivo` de la `Decision` que devolvió `servicio_consulta_autorizacion(...)` |
| `detalle` | jsonb | no | Contexto. **Sin datos personales ni secretos** |
| `eslabon` | str | sí | HMAC de este evento más el `eslabon` del anterior |

## El patrón de bandeja de salida

Los eventos no se escriben directo en la otra base. Se insertan en una tabla
`salida` de la base principal, **en la misma transacción que la operación**, y
el transmisor los copia después.

Por qué: si la bitácora está caída, la operación no debe fallar, pero el evento
tampoco debe perderse. Al estar en la misma transacción, es imposible que una
operación ocurra sin su evento — si la operación se confirma, el evento está.

Efecto de D-11: el transmisor y los demás trabajos periódicos cuelgan de un
solo punto de entrada. Si se atrasa, los eventos se acumulan sin perderse y el
retraso se puede medir.

## La cadena

Cada evento lleva el HMAC del anterior, así que alterar uno rompe la cadena
desde ahí hacia adelante y se detecta al recomputarla.

**Límite que hay que declarar en el informe (D-03):** la llave del HMAC vive en
el proceso del transmisor, no encerrada en un motor como habría hecho OpenBao.
Quien comprometa ese proceso puede reescribir la cadena completa. La garantía
baja de «nadie con acceso a la base puede falsificar el historial» a «nadie con
acceso a la base, pero sí quien controle el transmisor». Lo compensan la
instancia separada donde el transmisor solo inserta, y la copia periódica
externa que permite comparar.

## Lo que nunca entra

- Contraseñas, ni siquiera su hash
- Cédulas o teléfonos en claro (LG-05 exige cifrarlos)
- Cadenas de conexión, llaves, cookies de sesión
- El cuerpo completo de una petición

Un evento es lo que pasó, no una copia de los datos.

## Retención

BI-04 y LG-06 exigen diez años para lo ligado a un certificado. Neon en plan
gratuito da seis horas de restauración, así que **la retención no sale de
Neon**: sale de un volcado periódico a Cloud Storage con retención bloqueada
(D-07).
