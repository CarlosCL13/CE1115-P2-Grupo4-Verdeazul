# Transmisor

Copia los eventos de auditoría desde la bandeja de salida de `verdeazul-app`
hasta la base separada `verdeazul-bitacora`, y les pone el sello de la cadena.
Lo invoca Cloud Scheduler. Por qué existe y cómo encaja está en el contrato 03.

## Lo que ya está listo

**Conexiones.** `app/bd.py` da dos, y el transmisor no tiene otras:

| | Base | Rol | Puede |
|---|---|---|---|
| `bd.bandeja()` | verdeazul-app | `outbox_rw` | Leer `eventos_pendientes` y cambiar solo `enviado_en` y `eslabon` |
| `bd.bitacora()` | verdeazul-bitacora | `log_writer` | Insertar en `eventos`. Ni leer ni modificar |

Cada `with` es una transacción: se confirma si termina bien y se revierte si
algo lanza.

**Configuración.** `app/config.py` lee las dos cadenas, la llave de la cadena
(`config.LLAVE_CADENA`) y el tope de eventos por corrida
(`config.EVENTOS_POR_CORRIDA`, 500). En la nube, si falta algo, el contenedor
no arranca.

**Despliegue.** El job `transmisor` de `.github/workflows/desplegar.yml` lo
publica cerrado a internet, con su propia cuenta de servicio, **una sola
instancia y una petición a la vez**. Se despliega solo al mergear a `develop`.

**Planificador.** Cloud Scheduler lo llama cada 30 minutos. Está en pausa hasta
que `transmitir` funcione; Carlos lo activa. P1 pedía avisar si el retraso
pasaba de cinco minutos; con media hora es una desviación, D-19, por las horas
de cómputo de Neon.

**`GET /salud`** dice si las dos conexiones responden. Úsala a mano, no en un
bucle: cada llamada despierta las dos bases de Neon.

## Correr en local

En el `.env` de la raíz van tres valores, todos copiados de Secret Manager:

```
VERDEAZUL_OUTBOX_URL=          (secreto verdeazul-outbox-url)
VERDEAZUL_BITACORA_URL=        (secreto verdeazul-bitacora-escritura-url)
LLAVE_CADENA_BITACORA=         (secreto llave-cadena-bitacora)
```

```bash
.venv/Scripts/python.exe -m pip install -r services/transmisor/requirements.txt
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir services/transmisor --port 8082
```

**Cuidado: hay una sola bitácora.** Lo que transmitas desde tu máquina queda en
la de verdad, y no se puede borrar: `log_writer` no tiene DELETE, a propósito.
Por eso la llave tiene que ser la misma de Secret Manager, y conviene probar el
cálculo del eslabón con pruebas que no toquen la base antes de transmitir nada.

## Cómo debería funcionar `transmitir`

Son dos bases, así que no hay una transacción que cubra las dos. Lo que sigue
es lo que hace que eso no importe.

1. **Un candado.** Lo primero, dentro de `bd.bandeja()`:
   `SELECT pg_advisory_xact_lock(42)`. Una sola instancia ya lo evita, pero si
   dos corridas se cruzaran, la cadena se partiría en dos.
2. **El punto de partida.** El eslabón del último evento enviado:
   `SELECT eslabon FROM eventos_pendientes WHERE enviado_en IS NOT NULL ORDER BY id DESC LIMIT 1`.
   Si no hay ninguno, la cadena empieza desde un valor fijo, por ejemplo `""`.
3. **El lote, en orden.** `WHERE enviado_en IS NULL ORDER BY id LIMIT` el tope.
   Se procesa ese lote y se termina; los que falten van en la corrida
   siguiente. Nada de repetir hasta vaciar la bandeja (§3.1).
4. **El eslabón.** `HMAC-SHA256(llave, eslabón anterior + el evento)`, con el
   evento escrito siempre igual: los mismos campos, en el mismo orden (por
   ejemplo `json.dumps(..., sort_keys=True, separators=(",", ":"))`). Va en
   una función propia, porque la tarea `cadena` tiene que recalcularlo
   exactamente igual.
5. **El id en la bitácora sale del id de la bandeja.** `eventos.id` es un
   `uuid` único. Si se deriva del id de la bandeja (por ejemplo con
   `uuid.uuid5`), reintentar un evento da el mismo id, y
   `INSERT ... ON CONFLICT DO NOTHING` lo salta en vez de duplicarlo.
6. **Primero la bitácora, después la bandeja.** Se insertan los eventos y se
   confirma. Después se marcan en la bandeja `enviado_en` y `eslabon`, y se
   confirma. Si algo falla entre los dos pasos, la corrida siguiente vuelve a
   intentar esos eventos: el 5 evita los duplicados, y como el eslabón se
   calcula siempre igual, sale el mismo.
7. **La hora.** Se copia `eventos_pendientes.momento`, que es la hora de la
   operación. Si no se manda, la bitácora pone la de la transmisión, que puede
   ser media hora después de lo que pasó. D-19 da por hecho que se copia.

Huecos en `eventos.secuencia` son normales: un insert que falla igual gasta un
número. La cadena demuestra que nada se alteró, no que los números sean
seguidos; quien escriba `cadena` no debe tomarlos como borrados.

## Las otras tres tareas

**`cadena`** necesita leer toda la bitácora, y `log_writer` no lee. Cuando se
escriba, Carlos le da al transmisor el rol `log_reader`, que ya existe.

**`vencer`** necesita poder marcar asignaciones y consentimientos como
revocados, y `outbox_rw` no puede. Cuando se escriba, Carlos agrega la
migración con ese permiso.

**`volcado`** es el respaldo con retención bloqueada que D-03 y D-07 prometen
como compensación: la copia separada de BI-03 y la retención de diez años de
BI-04. Si no da el tiempo se puede recortar, pero entonces hay que corregir esas
dos desviaciones, que hoy lo dan por hecho.

D-11 nombra además el reporte semanal de HBAC-02, que no está entre estas
tareas. Está en las decisiones abiertas de las desviaciones.
