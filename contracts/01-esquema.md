# Contrato 1: esquema de base de datos

**Estado: BORRADOR. Todavía no implementado en `db/migrations/`.**

Este documento dice qué tiene que existir y por qué. El SQL que lo implementa
es el siguiente paso.

## Dos bases separadas

| Base | Proyecto Neon | Qué guarda | Quién escribe |
|---|---|---|---|
| Principal | `verdeazul-app` | O1 a O10 | `app_rw` |
| Bitácora | `verdeazul-bitacora` | O11 | `log_writer`, solo INSERT |

Están en instancias separadas a propósito: así se implementa la frontera **F6**
del diseño. Quien comprometa la aplicación no puede borrar el rastro.

## Roles de base de datos

Ninguno es `neondb_owner`. La aplicación nunca se conecta como dueño de las
tablas.

| Rol | Permisos | Para qué |
|---|---|---|
| `app_rw` | SELECT, INSERT, UPDATE sobre las tablas de datos. **Sin DELETE, sin DDL** | La aplicación en ejecución |
| `app_migrate` | DDL | Solo las migraciones, nunca la aplicación |
| `log_writer` | INSERT sobre la bitácora, nada más | El transmisor |

Hay que revocar lo que `PUBLIC` trae por defecto. Verificado en Neon: un rol
creado por SQL queda con `rolsuper = false` y `rolbypassrls = false`.

Sin DELETE para `app_rw` no es un olvido: ningún rol de la matriz tiene el
permiso E, así que la aplicación no debería poder borrar ni por error de código.

## Los once objetos

Cada tabla tiene que exponer los atributos que el motor de autorización
consulta. Esa columna es la que no se puede negociar: si falta un atributo, la
condición que depende de él no se puede evaluar.

| Objeto | Tabla | Atributos que el motor necesita |
|---|---|---|
| O1 Catálogo de fincas | `fincas` | `zona`, `propietario` |
| O2 Períodos de medición | `periodos` | `estado` (ABIERTO / CERRADO) |
| O3 Mediciones de biomasa | `mediciones` | `autor`, `finca`, `periodo`, `estado` |
| O4 Enmiendas | `enmiendas` | `solicitante`, `revisor`, `estado` |
| O5 Certificados de carbono | `certificados` | `estado`, `poligono` (PostGIS) |
| O6 Datos personales de dueños | `datos_personales` | cédula y teléfono **cifrados**, más un valor derivado para buscar |
| O7 Consentimientos y autorizaciones | `autorizaciones` | `tercero`, `vence` |
| O8 Asignaciones técnico–zona | `asignaciones` | `sujeto`, `zona`, `vence` |
| O9 Cuentas, roles y permisos | `cuentas`, `roles_asignados` | `rol`, y la aprobación previa de DG que exige C10 |
| O10 Credenciales propias | `credenciales` | hash Argon2id, nunca la contraseña |
| O11 Bitácora de auditoría | `eventos` (otra base) | append-only, con cadena HMAC |

## Estados, porque de ellos dependen cuatro condiciones

```
periodo:    ABIERTO -> CERRADO
medicion:   REGISTRADA -> APROBADA | DEVUELTA
enmienda:   SOLICITADA -> REVISADA -> CERRADA | DEVUELTA
certificado: VIGENTE -> ANULADO
```

C2 y C11 miran `periodo.estado`. C5 mira `enmienda.estado`. C6 mira
`medicion.estado`. Si estos nombres cambian, cambian las políticas en Rego.

## Lo que exige PostGIS

C6 pide que ningún certificado vigente tenga un polígono que se superponga con
el de la medición. Eso necesita:

- La columna `poligono` como `geometry(Polygon, 4326)`
- Un índice GiST sobre ella
- `ST_Intersects` para detectar el traslape
- `pg_advisory_xact_lock` para revalidar dentro de la transacción de emisión,
  o dos verificadores emitiendo a la vez pueden colarse

PostGIS 3.6 con GEOS y PROJ ya está verificado en Neon. Las cuatro cosas
funcionan.

## Preguntas abiertas

Hay que resolverlas antes de escribir el SQL:

1. ¿`zona` es una tabla o un valor de texto? C1 compara `finca.zona` contra
   `sujeto.zonas`, en plural, así que un sujeto tiene varias.
2. La aprobación previa de DG que exige C10 — ¿tabla propia de solicitudes de
   cambio, o una columna en `roles_asignados`?
3. El valor derivado para buscar por cédula: ¿HMAC con llave, o hash simple?
   Hash simple es vulnerable a un diccionario, porque las cédulas de Costa Rica
   tienen formato conocido y el espacio es pequeño.
