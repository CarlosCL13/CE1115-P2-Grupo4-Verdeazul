# Contrato 1: esquema de base de datos

**Estado: implementado y aplicado.** El SQL está en
[`db/migrations/`](../db/migrations/) y [`db/bitacora/`](../db/bitacora/).

Este documento dice qué existe y por qué. Si algo de aquí contradice al SQL,
manda el SQL y hay que corregir este archivo.

## Dos bases separadas

| Base | Proyecto Neon | Qué guarda | Quién escribe |
|---|---|---|---|
| Principal | `verdeazul-app` | O1 a O10 | `app_rw` |
| Bitácora | `verdeazul-bitacora` | O11 | `log_writer`, solo INSERT |

Instancias separadas a propósito: así se implementa la frontera **F6**. Quien
comprometa la aplicación no puede borrar el rastro.

## Roles

Son **cinco**, ninguno dueño de nada. La aplicación nunca se conecta como
`neondb_owner`: esa cuenta se usa una sola vez, para crear las demás.

| Rol | Base | Permisos |
|---|---|---|
| `app_migrate` | app | crear y alterar tablas. Solo las migraciones |
| `app_rw` | app | SELECT, INSERT, UPDATE. **Sin DELETE, sin DDL** |
| `outbox_rw` | app | `eventos_pendientes` y nada más, y de ella solo `enviado_en` |
| `log_writer` | bitácora | INSERT en `eventos`. **Sin SELECT** |
| `log_reader` | bitácora | SELECT en `eventos` |

`app_rw` sin DELETE no es exceso de celo: ninguna de las 88 celdas concede el
permiso E. Y está puesto como privilegio por omisión, así que toda tabla nueva
nace igual sin que ninguna migración tenga que acordarse.

`log_writer` sin SELECT porque el transmisor no necesita releer lo que
escribió. El eslabón anterior de la cadena lo lleva él en la bandeja de
salida, y no darle lectura significa que comprometerlo no entrega el
historial.

`log_reader` existe porque la matriz da `L` sobre O11 a Dirección General,
Dirección de Certificación, Personal Administrativo y Auditor Externo.

## Dieciséis tablas para once objetos

Los once objetos de la matriz no son once tablas. Cinco existen porque sin
ellas una condición no se puede evaluar o un control no se puede imponer.

| Tabla | Objeto | Para qué |
|---|---|---|
| `zonas` | apoyo | catálogo, para que C1 tenga llave foránea |
| `fincas` | O1 | `zona` (C1), `propietario` (C8), `poligono` (C6) |
| `periodos_medicion` | O2 | `estado` (C2, C11) |
| `mediciones` | O3 | `autor` (C3, C6), `estado` (C6) |
| `enmiendas` | O4 | `solicitante`, `revisor`, `cerrada_por` (C4, C5) |
| `certificados` | O5 | `poligono` y `estado` (C6), firma y llave pública |
| `datos_personales` | O6 | cédula y teléfono cifrados, más HMAC de búsqueda |
| `consentimientos` | O7 | `tercero`, `vence` (C9) |
| `asignaciones_zona` | O8 | `sujeto`, `zona`, `vence` (C1) |
| `cuentas` | O9 | `rol`, uno solo por cuenta |
| `credenciales` | O10 | hash Argon2id y secreto TOTP |
| `sesiones` | apoyo | sesión en la base, para invalidarla al instante |
| `ventanas_auditoria` | **ninguno** | sin ella C7 no se puede evaluar |
| `solicitudes_rol` | **ninguno** | sin ella C10 no se puede evaluar |
| `eventos_pendientes` | apoyo | la bandeja de salida del patrón outbox |
| `eventos` | O11 | otra base, solo anexar, con cadena HMAC |

Dos merecen explicación porque no estaban en la lista original de once.

**`ventanas_auditoria`** guarda `auditor`, `inicio` y `fin`. C7 dice
`hoy ∈ [inicio, fin]` y gobierna **doce celdas** del auditor externo. Sin esa
tabla, esas doce quedan sin implementar, y §7.1 descuenta proporcionalmente.

**`solicitudes_rol`** guarda quién pide un cambio de rol y quién lo aprueba.
C10 exige aprobación previa de Dirección General con `aprobador ≠ solicitante`.
Son dos identidades y un estado, y la fila tiene que existir **antes** de que
la cuenta cambie, así que no cabe como columna en `cuentas`.

## Los id

`integer GENERATED ALWAYS AS IDENTITY` en las quince. `zonas` es la única con
llave de texto, dos letras: `PN`, `PC`, `PS`, `CN`, `CS`, `VC`, `ZN`.

`IDENTITY` y no `serial` porque la secuencia pertenece a la columna, así que
el permiso de INSERT sobre la tabla alcanza y no hay que dar `GRANT USAGE`
sobre una secuencia aparte. `ALWAYS` significa que la aplicación no puede
fijar el id; los datos de prueba que necesiten ids fijos usan
`OVERRIDING SYSTEM VALUE`.

Que sean secuenciales deja contar cuántos certificados hay. Lo asumimos: el
control de acceso no depende de que el id sea impredecible, y probar
`/certificados/2` sin permiso es justo lo que hay que mostrar rechazado el 19
de noviembre.

Excepción: `eventos.secuencia` en la bitácora es `bigserial`, porque es la
única tabla donde las filas se acumulan de verdad, una por operación con diez
años de retención.

## Estados, como tipos enumerados

Siete `CREATE TYPE ... AS ENUM` en `002_catalogos.sql`, no `text` con `CHECK`.

```
rol_sujeto          los 8 roles de la matriz
estado_periodo      ABIERTO, CERRADO
estado_medicion     REGISTRADA, APROBADA, DEVUELTA
estado_enmienda     SOLICITADA, REVISADA, CERRADA, DEVUELTA
estado_certificado  VIGENTE, ANULADO
estado_solicitud    PENDIENTE, APROBADA, RECHAZADA, APLICADA
resultado_evento    PERMITIDO, DENEGADO
```

`rol_sujeto` es el que más gana: la lista de los ocho la usan `cuentas` y
`solicitudes_rol`, y antes estaba escrita dos veces. Esa lista **es** la
matriz: si cambia, cambian las 88 celdas, las políticas en Rego y las pruebas.

C2 y C11 leen `periodos_medicion.estado`. C6 lee `mediciones.estado` y
`certificados.estado`. C5 lee `enmiendas.estado`.

Cuidado al agregar un valor: `ALTER TYPE ... ADD VALUE` no deja usar el valor
nuevo en la misma transacción, y el runner corre cada archivo en una. Una
migración que agregue un estado y lo use va en dos archivos.

## Parte del control vive en la base

Cuatro condiciones quedaron escritas como `CHECK`, así que el motor las
rechaza aunque el código tenga un bug:

| Restricción | Tabla | Cubre |
|---|---|---|
| `revisor_distinto_del_autor` | `mediciones` | mitad de C3 |
| `revisor_distinto_del_solicitante` | `enmiendas` | C4 |
| `cierre_de_una_tercera_persona` | `enmiendas` | C5 |
| `aprobador_distinto_del_solicitante` | `solicitudes_rol` | mitad de C10 |

Las mitades que faltan de C3 y C10 miran otras filas o el rol de quien actúa,
y eso no cabe en un `CHECK`. Las comprueba el PDP.

Y un `GRANT` por columna que vale más que un `CHECK`:

```sql
REVOKE UPDATE ON mediciones FROM app_rw;
GRANT  UPDATE (estado, revisada_por, revisada_en, motivo_devolucion)
    ON mediciones TO app_rw;
```

Verificado contra Neon: `app_rw` tiene INSERT y SELECT sobre
`biomasa_toneladas` y **no tiene UPDATE**. «Ningún rol tiene M en O3» lo
impone el motor, no la disciplina.

## Lo que exige PostGIS

C6 pide que ningún certificado vigente tenga un polígono que se superponga con
el de la medición:

- `fincas.poligono` y `certificados.poligono` como `geometry(Polygon, 4326)`
- índice GiST en los dos, y en `certificados` **parcial**, solo los vigentes
- `CHECK (ST_IsValid(poligono))`, que es la validación geoespacial de F3
- `ST_Intersects` para detectar el traslape
- `pg_advisory_xact_lock` para revalidar dentro de la transacción de emisión

Lo último no está en el esquema, va en el código de emisión. El índice acelera
buscar traslapes pero no evita que dos verificadores emitan a la vez y los dos
vean «sin traslape» antes de que el otro confirme.

El polígono del certificado es **copia**, no referencia. Si alguien corrige el
polígono de una finca el año que viene, un certificado ya emitido no puede
cambiar: va firmado.

## Las preguntas abiertas, resueltas

**¿`zona` es tabla o texto?** Tabla, con llave de texto de dos letras. Con
texto suelto no hay llave foránea, y un error de dedo concede o niega permisos
en silencio.

**¿Dónde vive la aprobación previa de DG que exige C10?** En
`solicitudes_rol`, tabla propia, porque la aprobación precede al cambio.

**¿HMAC o hash simple para buscar por cédula?** HMAC con llave. Una cédula de
Costa Rica son nueve dígitos: un diccionario de todas se calcula en minutos.
Con HMAC la llave no está en la base, así que un volcado solo no sirve.

**¿Dónde vive el polígono?** En `fincas`, y la medición lo hereda por su
finca. `certificados` guarda una copia del momento de emisión.

### Lo que sigue abierto

La matriz **no dice quién crea una ventana de auditoría**, porque no es un
objeto y ninguna celda lo cubre. Decidimos Dirección General. Es decisión
nuestra, no heredada, y va a
[`docs/P2_Desviaciones_respecto_P1.md`](../docs/P2_Desviaciones_respecto_P1.md).

## Lo que agregó la 011

La autenticación necesitó columnas que la 004 no previó. Van en
`011_identidad_ajustes.sql`, porque un archivo aplicado no se edita.

| Tabla | Columnas nuevas | Para qué |
|---|---|---|
| `sesiones` | `ultimo_uso`, `reautenticada_en` | Cierre por inactividad por perfil y reautenticación antes de acciones graves |
| `credenciales` | `totp_ultimo_paso`, `codigos_recuperacion`, `debe_cambiar` | Un código TOTP no sirve dos veces, RC-02, y la clave temporal de una cuenta nueva |
| `cuentas` | `desactivada_en` | Desde cuándo está de baja (CU-13) |
| `solicitudes_rol` | `tipo`, `usuario_nuevo`, `nombre_nuevo`, `justificacion`, `aplicada_por`, `aplicada_en`, `rechazada_en`, `motivo_rechazo` | Que C10 cubra también el alta y la baja, no solo el cambio de rol |

Y tres restricciones más que llevan CU-03 y C10 a la base:
`nadie_pide_para_si`, `nadie_aprueba_para_si` y `aplica_otro_que_el_aprobador`.

## Lo que agregó la 012

Lo que necesitaban el transmisor y los certificados, en
`012_transmisor_y_certificados.sql`.

| Tabla | Cambio | Para qué |
|---|---|---|
| `eventos_pendientes` | Columna `eslabon`, que `outbox_rw` puede escribir | El transmisor guarda ahí el sello del último evento copiado, porque `log_writer` no puede leer la bitácora |
| `eventos_pendientes` | `enviado_lleva_eslabon` | Una fila se marca enviada junto con su eslabón, nunca a medias |
| `eventos_pendientes` | Sin UPDATE para `app_rw` | La aplicación anota eventos, no los cambia antes de que se sellen |
| `certificados` | `app_rw` solo modifica `estado`, `motivo_anulacion` y `anulado_en` | Lo firmado queda como se firmó, igual que `mediciones` |

Verificado contra Neon antes de aplicarla, dentro de una transacción
revertida: `app_rw` pierde UPDATE sobre la bandeja y sobre `firma`, y
`outbox_rw` puede cambiar `eslabon` pero no el texto de un evento.

Los certificados no llevan una serie aparte: la verificación pública recibe
el archivo y no consulta la base (D-09), así que el id secuencial no expone
nada que no se haya aceptado ya en `db/migrations/README.md`.

## Dos límites de la plataforma

Para el análisis de seguridad heredada que pide §5.2.

**El TLS lo termina Neon en su proxy.** `pg_stat_ssl` dice `ssl = false`
consultado desde dentro, y `PQsslInUse` dice verdadero desde el cliente. El
tramo cifrado es cliente a proxy, no proxy a PostgreSQL.

**`PUBLIC` lee `spatial_ref_sys` y no lo podemos impedir.** El permiso lo
otorgó `cloud_admin`, un rol interno de Neon, y en PostgreSQL solo se revoca
lo que uno otorgó: el `REVOKE` corre sin error y no cambia nada. Son
definiciones de sistemas de coordenadas EPSG, sin nada de Verdeazul, pero el
límite es real y va en «qué queda sin cubrir».
