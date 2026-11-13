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

## Pruebas

```bash
cd services/transmisor
python -m pip install -r requirements.txt pytest httpx
python -m pytest -v
```

Van aparte de las de la raíz porque el transmisor y el backend se llaman los
dos `app`. Ninguna toca una base: la bandeja y la bitácora son cursores falsos
que anotan en orden lo que se les pide. Corren en el CI, en el job
«Transmisor».

`tests/test_eslabon.py` tiene un **vector fijo**: un evento, una llave de
prueba y el eslabón que tienen que dar. Si alguien cambia la forma canónica,
la hora o el espacio de ids, esa prueba falla, y tiene que fallar: los eventos
que ya están en la bitácora dejarían de verificar. El valor se puede comprobar
por fuera, sin Python:

```bash
printf '\n%s' '<el JSON canónico de la prueba>' | openssl dgst -sha256 -mac HMAC -macopt hexkey:000102…1f
```

## Cómo funciona `transmitir`

Está en `app/tareas/transmitir.py`, y el eslabón en `app/eslabon.py`, que
`cadena` tiene que reusar tal cual. Responde, por ejemplo:

```json
{"tarea": "transmitir", "transmitidos": 37, "primero": 1, "ultimo": 37, "quedan_mas": false}
```

**El eslabón**, exactamente:

```
eslabon = hex(HMAC-SHA256(llave, anterior + "\n" + canonico(evento)))
```

- `llave`: `LLAVE_CADENA_BITACORA` decodificada de base64 url (32 bytes).
- `anterior`: `""` para el primer evento, o el eslabón del anterior.
- `canonico`: JSON con `sort_keys` y sin espacios de los campos `id` (el uuid
  de la bitácora), `momento` (UTC, ISO con microsegundos), `accion`, `sujeto`,
  `objeto`, `resultado`, `motivo` y `detalle`. Son todas columnas de `eventos`,
  así que `cadena` lo recalcula leyendo solo la bitácora, en orden de
  `secuencia`.
- El uuid es `uuid5(ESPACIO_IDS, str(id_de_la_bandeja))`.

**Dos cambios respecto al plan de abajo**, los dos por lo mismo: el id y el
`momento` de la bandeja se asignan cuando *empieza* la transacción de la
operación, no cuando se confirma. Una operación lenta puede confirmar el
evento 10 después de que el 11 ya se transmitió.

- **El punto de partida** se busca con `ORDER BY enviado_en DESC, id DESC`,
  no solo por id. `enviado_en` es el mismo para todo un lote y crece de un lote
  al siguiente, así que ese es el orden en que se encadenó. Con solo `id`, el
  evento 10 tardío dejaría como "último" al 11 y la cadena se partiría.
- **Un margen** (`MARGEN_TRANSMISION_SEGUNDOS`, 120 por omisión): solo se
  transmiten eventos con más de dos minutos. Así el lote sale casi siempre en
  orden de id, y un reintento ve el mismo lote que la corrida que falló. Para
  la presentación eso significa que un evento aparece en la bitácora en la
  primera corrida que pase dos minutos después de la acción.

`ON CONFLICT DO NOTHING` va sin columna de destino: con destino, PostgreSQL
pide SELECT sobre esa columna, y `log_writer` no lee.

**Códigos:** 200 si corrió (aunque no hubiera nada que enviar), 503 si falta
una cadena de conexión o la llave, 500 si falló a la mitad. El detalle va a
Cloud Logging, nunca en la respuesta. Un 5xx deja la corrida en rojo en Cloud
Scheduler.

## El plan original de `transmitir`

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

## `cadena`: comprobar que nadie alteró la bitácora

`app/tareas/cadena.py`. Relee la bitácora entera con `log_reader`
(`bd.lectura()`, cadena `VERDEAZUL_BITACORA_LECTURA_URL`) en orden de
`secuencia` y recalcula cada eslabón con `app/eslabon.py`, la misma función
de `transmitir`.

| Qué detecta | Cómo |
|---|---|
| Un evento modificado | Su eslabón no cuadra con su contenido |
| Un evento borrado del medio | El eslabón del siguiente no cuadra |
| Eventos borrados del final | La «cola»: cuántos eventos dice la bandeja que se enviaron y con qué último eslabón, contra lo que tiene la bitácora |

Después de un eslabón roto sigue con el eslabón guardado como anterior, así
que marca solo los eventos afectados y no todo lo que viene después. Los
huecos de `secuencia` no cuentan.

Toma el mismo candado que `transmitir`, así que nunca compara mientras se
agregan eventos. Deja su propio evento en la bandeja, `CADENA_VERIFICADA` o
`CADENA_ROTA` (LG-07: la integridad se comprueba y queda constancia).
Responde **409** si la cadena está rota, para que la corrida salga en rojo en
Cloud Scheduler.

```json
{"tarea": "cadena", "intacta": true, "eventos": 230, "enviados_segun_bandeja": 230,
 "rotos": 0, "primer_roto": null, "cola_completa": true}
```

## `vencer`: revocar lo vencido

`app/tareas/vencer.py`. Marca `revocada_en` en las asignaciones técnico–zona
con `vence < hoy` y `revocado_en` en los consentimientos con `vence <= hoy`
(las mismas fronteras que C1 y C9). Anota un evento por cada una,
`ASIGNACION_VENCIDA` o `CONSENTIMIENTO_VENCIDO`, con sujeto `SISTEMA`.

El motor ya niega lo vencido por fecha, así que esta tarea no es la que corta
el acceso: lo deja asentado en la tabla y en la bitácora. Correrla dos veces
no hace nada la segunda.

## Los permisos que necesitan

**Migración 014** (`db/migrations/014_transmisor_vencer.sql`), para `vencer`
y para que las dos tareas anoten sus eventos. Le da a `outbox_rw`, columna
por columna: leer y marcar la fecha de revocación de `asignaciones_zona` y
`consentimientos`, e insertar eventos en la bandeja. Nada más: no puede
cambiar una zona ni extender un vencimiento. La aplica quien tenga
`app_migrate`:

```bash
python db/migrar.py app
```

**El secreto de lectura**, para `cadena`. El transmisor recibe además
`VERDEAZUL_BITACORA_LECTURA_URL` desde `verdeazul-bitacora-lectura-url`, el
mismo que ya usa el backend. Su cuenta de servicio necesita poder leerlo
**antes** de desplegar, o la revisión nueva no arranca y Cloud Run sigue con
la anterior:

```bash
gcloud secrets add-iam-policy-binding verdeazul-bitacora-lectura-url --project=verdeazul-g4 --member=serviceAccount:verdeazul-transmisor@verdeazul-g4.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor
```

En local, el `.env` lleva además:

```
VERDEAZUL_BITACORA_LECTURA_URL=  (secreto verdeazul-bitacora-lectura-url)
```

## `volcado`

**`volcado`** es el respaldo con retención bloqueada que D-03 y D-07 prometen
como compensación: la copia separada de BI-03 y la retención de diez años de
BI-04. Si no da el tiempo se puede recortar, pero entonces hay que corregir esas
dos desviaciones, que hoy lo dan por hecho.

D-11 nombra además el reporte semanal de HBAC-02, que no está entre estas
tareas. Está en las decisiones abiertas de las desviaciones.
