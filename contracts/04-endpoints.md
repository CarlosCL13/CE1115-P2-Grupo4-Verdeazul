# Contrato 04 — Endpoints

Cada endpoint es una casilla de la matriz. Las operaciones se traducen siempre
igual, así que nadie tiene que inventar nombres:

```
L  → GET                    C  → POST                 M  → PATCH
A, D, Ab, Cr, Em, An, X  →  POST /recurso/{id}/accion
```

Son 57 endpoints. Solo dos responden sin sesión: `/salud` y la verificación
pública de certificados. Todos los demás exigen sesión válida y llaman a
`servicio_consulta_autorizacion()` (contrato 02) antes de hacer cualquier cosa.

## Lo que cubre todo endpoint, sin repetirlo en cada fila

| | |
|---|---|
| Matriz de acceso y arquitectura | 25 pts — el servidor rechaza lo no autorizado |
| Control 2.3.2 | el control vive en el servidor, no en la interfaz |
| Control 2.3.5 | consultas parametrizadas, nunca concatenar |
| Control 2.3.4 | TLS: lo da Cloud Run, pero hay que forzar HTTPS |

La columna **Cubre** de las tablas anota solo lo que ese endpoint agrega además
de esto. Y §7.1 descuenta proporcionalmente por cada permiso de la matriz sin
implementar, así que la cuenta de endpoints es la cuenta de puntos.

## Reparto

| | Módulos | Endpoints | Hechos al 12 de noviembre |
|---|---|---|---|
| Persona 1 | plataforma, O7, O8, **O4** | 16 | 1: `/salud` |
| Persona 2 | autenticación, O6, O9, O10 | 13 | 13 |
| Persona 3 | el motor que llaman los otros 56 | 1 | 0 |
| Persona 4 | O1, O2, O3 | 15 (con `POST /periodos`, D-17) | 15 |
| Persona 5 | O5, O11, transmisor | 12 | 0 |

**Van 29 de 57.** Lo que falta todavía no tiene dueño: está en orden de
prioridad en [README.md](README.md), sección «Dónde estamos». La última
columna de cada tabla de abajo dice si el endpoint ya existe.

**O4 enmiendas pasó de la persona 4 a la persona 1.** La 4 tenía 21 endpoints y
la 1 tenía nueve. Enmiendas es lo más separable del flujo porque va al final: no
hay nada después que dependa de ella. O4 depende de `periodos_medicion` (C11) y
`mediciones` (C5), y las dos ya están aplicadas.

---

# Persona 1 — Plataforma, O7, O8, O4

## Plataforma

**Dónde:** `services/api/app/main.py`, `config.py`, `bd.py`

| Endpoint | Para qué sirve | Necesita | Cubre | Estado |
|---|---|---|---|---|
| `GET /salud` | Comprobar de punta a punta que Secret Manager entrega la cadena, que Cloud Run la recibe y que Neon responde | nada | Despliegue 16, Secretos 12 | Hecho |

Es el único endpoint que se escribe antes que todo lo demás, porque es el que
prueba que el despliegue existe. Ya está escrito.

## O7 Consentimientos y autorizaciones

**Dónde:** `services/api/app/concesiones/rutas.py`
**Pantallas:** `services/edge/templates/concesiones/`
**Migración:** `db/migrations/007_atributos.sql`

| Endpoint | Para qué sirve | Necesita | Cubre | Estado |
|---|---|---|---|---|
| `GET /consentimientos` | La Dirección General y el personal administrativo ven qué autorizaciones existen | tabla `consentimientos` | — | **Pendiente** |
| `GET /consentimientos/{id}` | El dueño de finca consulta lo que él mismo autorizó | C8 en el motor | — | **Pendiente** |
| `POST /consentimientos` | El dueño autoriza a un tercero a ver sus certificados; el administrativo lo registra por él | C8, evento de bitácora | Correspondencia P1 7 | **Pendiente** |
| `PATCH /consentimientos/{id}` | El dueño revoca o cambia el alcance de lo que autorizó | C8, evento de bitácora | — | **Pendiente** |

Este objeto es el que hace que O5 `L·C9` funcione: el tercero autorizado puede
ver un certificado **porque existe un consentimiento vigente aquí**. Sin O7, la
casilla del tercero no tiene de dónde leer.

## O8 Asignaciones técnico–zona

**Dónde:** `services/api/app/concesiones/rutas.py`
**Migración:** la misma de O7

| Endpoint | Para qué sirve | Necesita | Cubre | Estado |
|---|---|---|---|---|
| `GET /asignaciones` | Ver qué técnico atiende qué zona | tabla `asignaciones_zona` | — | Hecho, con «solo vigentes» |
| `GET /asignaciones/{id}` | El técnico y el verificador ven su propia asignación | C1 en el motor | — | Hecho |
| `POST /asignaciones` | La Dirección de Certificación asigna un técnico a una zona, con fecha de vencimiento | evento de bitácora | — | Hecho, con reautenticación y fin obligatorio (máx. 3 años) |
| `PATCH /asignaciones/{id}` | Cambiar la zona o extender el vencimiento | evento de bitácora | — | Hecho. También revoca (`{"revocar": true}`): el acceso se pierde en la siguiente petición |

Este objeto alimenta C1, que es la condición más usada del sistema: aparece en
O1, O3, O4 y O8. Si `asignacion` está mal modelada, cuatro módulos fallan a la
vez. El vencimiento lo revisa `POST /tareas/vencer` de la persona 5 (HBAC-03).

## O4 Enmiendas

**Dónde:** `services/api/app/enmiendas/rutas.py`, `estados.py`
**Pantallas:** `services/edge/templates/enmiendas/`
**Migración:** `db/migrations/008_enmiendas.sql`

| Endpoint | Para qué sirve | Necesita | Cubre | Estado |
|---|---|---|---|---|
| `GET /enmiendas` | La dirección y el verificador ven las enmiendas pendientes | tabla `enmiendas` | — | Hecho, con filtro por estado |
| `GET /enmiendas/{id}` | Técnico (su zona), auditor y dueño ven una enmienda | C1, C7, C8 | — | Hecho |
| `POST /enmiendas` | El técnico pide corregir una medición suya | **C11**: solo con el período cerrado | — | Hecho. Una sola abierta por medición (409) |
| `POST /enmiendas/{id}/aprobar` | El verificador acepta la corrección | C4, reautenticación, bitácora | — | Hecho |
| `POST /enmiendas/{id}/devolver` | El verificador la rechaza con observaciones | C4, bitácora | — | Hecho. El motivo queda en el evento |
| `POST /enmiendas/{id}/cerrar` | La Dirección de Certificación la cierra definitivamente | **C5**, bitácora | Matriz: separación de deberes | Hecho, con reautenticación |
| `GET /enmiendas/exportar` | El auditor externo se lleva las enmiendas de su alcance | C7, formato acordado | Informe 10 | Hecho |

`estados.py` es donde vive la máquina
`SOLICITADA → REVISADA → CERRADA | DEVUELTA`. Nada que no esté REVISADA se puede
cerrar, y eso se verifica en el servidor, no en el formulario.

---

# Persona 2 — Autenticación, O6, O9, O10

## Autenticación

**Estado:** implementado, con pruebas en `tests/identidad/`. Cómo usar la sesión
desde los demás endpoints está en [05-sesion.md](05-sesion.md).

**Dónde:** `services/api/app/auth/rutas.py`, `contrasenas.py`, `sesiones.py`, `totp.py`
**Pantallas:** `services/edge/templates/auth/`
**Migración:** `db/migrations/003_cuentas.sql`, `004_identidad.sql` y `011_identidad_ajustes.sql`

Estos cinco no son casillas de la matriz: no deciden qué puede hacer alguien,
deciden **quién es**. Pero son los que más puntos protegen.

| Endpoint | Para qué sirve | Necesita | Cubre | Estado |
|---|---|---|---|---|
| `POST /auth/entrar` | Verificar la contraseña contra el hash y abrir sesión | Argon2id, lista de prohibidas, bloqueo por intentos | **2.3.1** — sin esto se pierde la mitad de los 25 | Hecho |
| `POST /auth/salir` | Cerrar sesión e invalidar la cookie | — | — | Hecho |
| `POST /auth/totp/activar` | Dar de alta el segundo factor con un código QR | tabla `credenciales` | Correspondencia P1 7 | Hecho |
| `POST /auth/totp/verificar` | Pedir el código de seis dígitos a quien aprueba, emite o cambia permisos | reloj con tolerancia | Correspondencia P1 7 | Hecho |
| `POST /auth/reautenticar` | Volver a pedir la contraseña antes de una acción grave | — | Correspondencia P1 7 | Hecho |

`POST /auth/entrar` es el endpoint más delicado del proyecto: §7.1 dice que
contraseñas sin hash o con hash rápido cuestan la mitad del criterio de control
de acceso, que son doce puntos y medio.

## O6 Datos personales de dueños

**Dónde:** `services/api/app/personas/rutas.py`, `cedula.py`
**Pantallas:** `services/edge/templates/personas/`

| Endpoint | Para qué sirve | Necesita | Cubre | Estado |
|---|---|---|---|---|
| `GET /personas` | El administrativo busca un dueño por cédula | valor derivado de la cédula | — | Hecho |
| `GET /personas/{id}` | El dueño consulta sus propios datos | C8 | — | Hecho |
| `POST /personas` | Registrar un dueño nuevo | bitácora | — | Hecho |
| `PATCH /personas/{id}` | Corregir datos de contacto | bitácora | — | Hecho |

Ojo con la matriz aquí: la Dirección de Certificación **no** tiene acceso a O6.
Es la casilla que más gente implementa mal, porque suena raro que una dirección
no vea datos de clientes. Es a propósito: no los necesita para certificar.

La búsqueda por cédula quedó resuelta con HMAC con llave (`cedula.py`): se busca
sin descifrar y un volcado de la base, solo, no permite recorrer las cédulas.

## O9 Cuentas, roles y permisos

**Dónde:** `services/api/app/cuentas/rutas.py`
**Pantallas:** `services/edge/templates/cuentas/`

| Endpoint | Para qué sirve | Necesita | Cubre | Estado |
|---|---|---|---|---|
| `GET /cuentas` | El administrativo ve las cuentas y sus roles | C10 | — | Hecho |
| `POST /cuentas` | Crear una cuenta y asignarle rol | **C10**: aprobación previa de DG | Matriz: separación de deberes | Hecho |
| `PATCH /cuentas/{id}` | Cambiar el rol o desactivar una cuenta | C10, bitácora | Matriz: separación de deberes | Hecho |

C10 es la condición que impide que el personal administrativo se dé permisos a sí
mismo. La aprobación previa vive en la tabla `solicitudes_rol`, y para eso
existen cuatro rutas más que no son casillas de la matriz:

| Endpoint | Para qué sirve | Quién | Estado |
|---|---|---|---|
| `GET /solicitudes-rol` | Ver las solicitudes y su estado | PA, DG | Hecho |
| `POST /solicitudes-rol` | Pedir un alta, un cambio de rol o una baja | PA | Hecho |
| `POST /solicitudes-rol/{id}/aprobar` | Aprobar, con reautenticación | DG | Hecho |
| `POST /solicitudes-rol/{id}/rechazar` | Rechazar con motivo | DG | Hecho |

Más `GET /auth/sesion`, que le dice al borde quién es la persona y qué le
falta (segundo factor, cambiar la clave temporal).

## O10 Credenciales propias

**Dónde:** `services/api/app/auth/rutas.py`

| Endpoint | Para qué sirve | Necesita | Cubre | Estado |
|---|---|---|---|---|
| `PATCH /credenciales` | Cualquiera cambia su propia contraseña | reautenticación, Argon2id, bitácora | 2.3.1 | Hecho |

Un solo endpoint, y vale la pena explicar por qué: **de los ocho roles, los ocho
tienen M sobre O10 y ninguno tiene L.** Ni la Dirección General. Así que no
existe ningún `GET /credenciales`. No es un olvido del diseño: es la matriz
diciendo que las credenciales se cambian y no se consultan. Esa ausencia es
defendible en la presentación y conviene que la persona 2 la sepa explicar.

---

# Persona 3 — El motor

**Dónde:** `services/api/app/authz/__init__.py`, `cliente_opa.py`,
`services/policies/rego/autorizacion.rego`, `condiciones.rego`
**Pruebas:** `tests/matriz/test_celdas.py`

No escribe endpoints de negocio: escribe la función que los otros 56 llaman
antes de tocar la base de datos. Su entrega se mide en pruebas, no en rutas: 84
casillas concedidas que hoy están en `xfail` y 884 negaciones que ya pasan y no
se deben romper.

| Endpoint | Para qué sirve | Necesita | Cubre | Estado |
|---|---|---|---|---|
| `GET /authz/explicar` | Enseñar en vivo la decisión y el motivo: «no, porque C6 impide que quien registró la medición emita el certificado» | solo Dirección General, registrado en bitácora | Presentación 5 | Pendiente, opcional |

Este endpoint es opcional y es para la demostración del 19. Va restringido a un
rol y cada consulta queda en bitácora, porque un endpoint que responde preguntas
sobre permisos ajenos es una fuga de información si queda abierto. Si no da
tiempo, se quita sin consecuencias.

---

# Persona 4 — O1, O2, O3

**Implementado.** El módulo vive en `services/api/app/certificacion/` y sus
pruebas en `tests/certificacion/`. Todo id que va al motor viaja como texto.
`GET /mediciones/exportar` se declara antes que `GET /mediciones/{id}`, para
que "exportar" no se tome por un id. Una finca o medición que no existe
responde 403 y no 404 a quien no puede verlas todas, para que nadie averigüe
qué ids existen comparando respuestas.

## O1 Catálogo de fincas

**Dónde:** `services/api/app/certificacion/rutas.py`, `consultas.py`
**Pantallas:** `services/edge/templates/certificacion/`
**Migración:** `db/migrations/005_fincas_periodos.sql` y `006_mediciones.sql`

| Endpoint | Para qué sirve | Necesita | Cubre | Estado |
|---|---|---|---|---|
| `GET /fincas` | Listar las fincas registradas | tabla `fincas` con `geometry(Polygon, 4326)` | — | Hecho |
| `GET /fincas/{id}` | Técnico (su zona), auditor (su alcance) y dueño (la suya) ven una finca | C1, C7, C8 | — | Hecho |
| `POST /fincas` | El administrativo registra una finca con su polígono | índice GiST | Correspondencia P1 7 | Hecho |
| `PATCH /fincas/{id}` | Corregir linderos o datos de la finca | bitácora | — | Hecho |

La tabla `fincas` ya está aplicada en `005_fincas_periodos.sql`, con el
polígono y el índice GiST de los que depende C6 de la persona 5.

## O2 Períodos de medición

**Dónde:** `services/api/app/certificacion/rutas.py`, `estados.py`
**Migración:** `db/migrations/005_fincas_periodos.sql`

| Endpoint | Para qué sirve | Necesita | Cubre | Estado |
|---|---|---|---|---|
| `GET /periodos` | Ver los períodos y su estado. Seis de los ocho roles pueden (la matriz da `—` al administrativo y al tercero) | tabla `periodos_medicion` | — | Hecho |
| `GET /periodos/{id}` | Ver un período concreto | — | — | Hecho |
| `POST /periodos` | La Dirección de Certificación abre un período nuevo. Nace ABIERTO. Reautenticación, bitácora | Ab | D-17 | Hecho |
| `POST /periodos/{id}/abrir` | Reabrir un período cerrado. Reautenticación, bitácora | Ab | D-17 | Hecho |
| `POST /periodos/{id}/cerrar` | Cerrarlo cuando no quedan mediciones sin aprobar | bitácora | — | Hecho |

`periodo.estado` es lo que miran C2 y C11. Si cambia de nombre, cambian las
políticas en Rego de la persona 3 y los endpoints de O4 de la persona 1.

## O3 Mediciones de biomasa

**Dónde:** `services/api/app/certificacion/rutas.py`, `estados.py`
**Migración:** `db/migrations/006_mediciones.sql`

| Endpoint | Para qué sirve | Necesita | Cubre | Estado |
|---|---|---|---|---|
| `GET /mediciones` | Ver las mediciones de un período | tabla `mediciones` | — | Hecho |
| `GET /mediciones/{id}` | Técnico, auditor y dueño ven una medición | C1, C7, C8 | — | Hecho |
| `POST /mediciones` | El técnico (y el verificador) registra cuánta biomasa midió | **C2**: período abierto. El técnico además en su zona (D-18) | — | Hecho |
| `POST /mediciones/{id}/aprobar` | El verificador la acepta | **C3**: no puede ser quien la registró. Reautenticación, bitácora | Matriz: separación de deberes | Hecho |
| `POST /mediciones/{id}/devolver` | El verificador la rechaza con observaciones | C3, bitácora | — | Hecho |
| `GET /mediciones/exportar` | El auditor externo se lleva las mediciones en CSV (`id, finca, periodo, autor, biomasa_toneladas, estado, registrada_en`) | C7 | Informe 10 | Hecho |

C3 es la separación de deberes central del sistema: impide que una sola persona
registre y apruebe su propia medición. Es la casilla que hay que saber defender.

---

# Persona 5 — O5, O11, transmisor

## O5 Certificados de carbono

**Dónde:** `services/api/app/certificados/rutas.py`, `firma.py`, `verificacion.py`
**Pantallas:** `services/edge/templates/certificados/` y el inicio público
**Migración:** `db/migrations/009_certificados.sql`

| Endpoint | Para qué sirve | Necesita | Cubre | Estado |
|---|---|---|---|---|
| `GET /certificados` | Ver los certificados emitidos | tabla `certificados` | — | **Pendiente** |
| `GET /certificados/{id}` | El dueño ve los suyos; el tercero ve los que le autorizaron | C8, **C9** (lee O7) | — | **Pendiente** |
| `POST /certificados/{id}/emitir` | El verificador emite y **firma** el certificado | **C6**: `ST_Intersects` más `pg_advisory_xact_lock`. Clave privada en Secret Manager. Reautenticación | **Certificados 15, 2.3.6** | **Pendiente** |
| `POST /certificados/{id}/anular` | La Dirección de Certificación anula uno emitido | bitácora | — | **Pendiente** |
| `GET /certificados/exportar` | El auditor se lleva los certificados de su alcance | C7 | Informe 10 | **Pendiente** |
| `POST /publico/verificar` | **Sin sesión.** Cualquiera sube el archivo del certificado y se comprueba la firma con la clave pública que viaja en él, comparando su huella con la publicada de Verdeazul (D-10) | nada: no toca la base (D-09). Límite de tasa y tamaño máximo del archivo | **Certificados 15** — «que un tercero pueda confiar sin acceso al sistema» | **Pendiente** |

Estos dos últimos valen quince puntos entre los dos. `emitir` es además el más
complicado del proyecto: C6 exige revalidar el traslape de polígonos dentro de la
transacción, porque dos verificadores emitiendo a la vez se pueden colar.

`POST /publico/verificar` tiene un límite que hay que declarar en el
informe (D-10): la clave pública en el documento prueba que el contenido no cambió, pero
no prueba quién firmó. Para eso hace falta publicar la huella de la clave de
Verdeazul por un canal aparte.

## O11 Bitácora de auditoría

**Dónde:** `services/api/app/bitacora/registrar.py`, `cadena.py`, `rutas.py`
**Migración:** `db/bitacora/001_bitacora.sql` y `db/migrations/010_salida.sql`

| Endpoint | Para qué sirve | Necesita | Cubre | Estado |
|---|---|---|---|---|
| `GET /bitacora` | DG, Dirección de Certificación y administrativo consultan el registro | base de bitácora | Informe 10 | Hecho. Filtros por fecha, acción, sujeto, objeto y resultado; páginas de 100 |
| `GET /bitacora/exportar` | El auditor externo se lleva el registro de su alcance | C7, cadena verificable | Informe 10 | Hecho. CSV en el orden de la cadena, con eslabón; tope de 5000 filas |

Lo más importante de la persona 5 no es un endpoint: es `registrar.py`, la
función que los otros cuatro llaman desde el día uno. Tiene que existir con
cuerpo vacío en la semana 1, o los demás escriben código que después hay que
reescribir.

## El transmisor

**Dónde:** `services/transmisor/app/tareas/`
**Despliegue:** Cloud Run privado, invocado solo por Cloud Scheduler

| Endpoint | Para qué sirve | Necesita | Cubre | Estado |
|---|---|---|---|---|
| `POST /tareas/transmitir` | Copia los eventos de la bandeja de salida a la base de bitácora | **cuarto rol de BD**: leer la bandeja y marcar enviado | Despliegue 16, Correspondencia P1 7 | Hecho, con pruebas sin base. Falta activar el Scheduler |
| `POST /tareas/vencer` | Desactiva asignaciones y autorizaciones vencidas (HBAC-03) | tablas de O7 y O8 | Correspondencia P1 7 | **Pendiente** |
| `POST /tareas/cadena` | Comprueba que la cadena HMAC cuadra de punta a punta | — | Informe 10 | **Pendiente** |
| `POST /tareas/volcado` | `pg_dump` a Cloud Storage para la retención de diez años | bucket con bloqueo | Correspondencia P1 7 | **Pendiente**: D-03 y D-07 lo citan como compensación |

Este servicio es el único que no expone nada al navegador. Y es la prueba viva de
que la arquitectura de P1 se implementó: los cuatro procesos periódicos del
diseño existen de verdad, lo que cuenta para los 7 puntos de correspondencia.

---

# Lo que hay que acordar antes de escribir ninguno

**El formato de exportación.** Cuatro endpoints terminan en `/exportar`: O3,
O4, O5 y O11. El primero ya existe y fija el formato: `GET /mediciones/exportar`
devuelve un CSV con una fila por registro, y solo responde si el auditor está
dentro de su ventana de auditoría (C7). Los otros tres hacen lo mismo, para que
el auditor reciba cuatro archivos que se leen igual.

**Dónde vive C8.** Aparece en seis objetos de cuatro personas, siempre con el
mismo significado: «el dueño solo ve lo suyo». La resuelve la persona 3 una vez,
en el motor. Si cuatro personas la escriben por aparte van a salir cuatro
versiones y alguna va a estar mal.

**El nombre de los estados.** C2 y C11 miran `periodo.estado`, C3 y C6 miran
`medicion.estado`, C5 mira `enmienda.estado`. Esos tres nombres los decide la
persona 4 en su migración y los usan las personas 1, 3 y 5. Se acuerdan una vez y
no se cambian.

**Una línea por persona en `main.py`.** Cada módulo expone una variable `router` y
en `main.py` se agrega una sola línea. Un conflicto de una línea se resuelve en
diez segundos; uno de treinta, no.
