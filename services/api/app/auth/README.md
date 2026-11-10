# Identidad (persona 2)

Acá vive quién es el que pregunta. Contraseñas, sesiones, segundo factor y el
`Sujeto` que le llega al motor de políticas. También están los tres objetos
propios de este frente, que son O10 (las credenciales de uno mismo), O6 (datos
personales de dueños) y O9 (cuentas y roles).

Si vas a escribir un endpoint de otro frente, no necesitás leer esta carpeta.
Leé [`contracts/05-sesion.md`](../../../../contracts/05-sesion.md), que trae el
endpoint típico listo para copiar.

## Qué hay en cada lugar

| Archivo | Qué hace |
|---|---|
| `auth/contrasenas.py` | Argon2id, reglas CO-01 y CO-02, hash señuelo, rehash |
| `auth/sesiones.py` | Sesiones en la base, inactividad por perfil, cierre inmediato |
| `auth/totp.py` | Segundo factor RFC 6238, sin repetición, códigos de recuperación |
| `auth/cifrado.py` | AES-256-GCM con contexto atado a la fila |
| `auth/dependencias.py` | `SesionCompleta`, `autorizar()`, `exigir_rol()`. Lo que usan todos |
| `auth/rutas.py` | `/auth/*` y `PATCH /credenciales` (O10) |
| `personas/` | O6, cédula y teléfono cifrados, búsqueda por HMAC |
| `cuentas/` | O9, altas, cambios de rol y bajas con el flujo C10 |
| `bitacora/registrar.py` | `registrar(...)` del contrato 03, vía bandeja de salida |
| `errores.py` | `ErrorAPI` y la forma única de los errores |

El borde (pantallas, cookie, CSRF) está en
[`services/edge/app/identidad.py`](../../../edge/app/identidad.py).

## Lo que no se debe romper

Estas son las decisiones que sostienen el criterio de control de acceso. Si un
cambio toca alguna, hablalo antes.

1. **Las contraseñas se guardan con Argon2id** (19 MiB, 2 iteraciones, 1 hilo,
   sal de 16 bytes). Nunca un hash rápido. Los parámetros salen de
   `config.ARGON2` y son los que fijó la Parte 1.
2. **La sesión vive en la base y el token se guarda solo como SHA-256.** Así se
   puede cerrar al instante (SE-01, CU-11) y quien lea la tabla no puede
   hacerse pasar por nadie.
3. **El error de login es siempre el mismo** (`credenciales_invalidas`), exista
   o no el usuario. El motivo real va a la bitácora. Si el usuario no existe se
   calcula igual un hash señuelo, para que el tiempo no delate quién existe.
4. **El error de una clave o un código equivocado se lanza después de cerrar la
   transacción.** Si se lanza adentro, `bd.transaccion()` revierte el contador
   de intentos y el bloqueo de RC-01 nunca avanza.
5. **Todo `*_id` que va al motor viaja como texto.** `autorizar()` los convierte,
   pero quien arme un `Sujeto` a mano tiene que hacerlo también. Un entero hace
   que C3, C4, C5, C6 y C10 concedan de más.
6. **No existe `GET /credenciales`**, a propósito. En la matriz los ocho roles
   tienen M sobre O10 y ninguno tiene L.
7. **En C10 quien pide, quien aprueba y quien aplica son tres cuentas
   distintas.** Lo refuerzan el código y los CHECK de la migración 011.
8. **Cédula, teléfono y secreto TOTP se guardan cifrados**, con la llave
   `LLAVE_CIFRADO_DATOS`. Para buscar por cédula se usa un HMAC con otra llave
   (`LLAVE_BUSQUEDA_CEDULA`). Ninguna de las dos va en el repositorio.

## Endpoints de este frente

| Método y ruta | Qué hace |
|---|---|
| `POST /auth/entrar` | Contraseña a sesión nueva, con bloqueo RC-01 |
| `POST /auth/salir` | Cierra la sesión |
| `GET /auth/sesion` | Quién soy, para que el borde dibuje |
| `POST /auth/totp/activar` | Alta del segundo factor, con QR y códigos de recuperación |
| `POST /auth/totp/verificar` | Código de seis dígitos o de recuperación |
| `POST /auth/reautenticar` | Contraseña otra vez antes de una acción grave |
| `PATCH /credenciales` | Cambiar la propia contraseña (O10) |
| `GET /personas`, `GET /personas/{cuenta}` | Leer datos personales (O6) |
| `POST /personas`, `PATCH /personas/{cuenta}` | Crear y modificar datos personales |
| `GET /solicitudes-rol`, `POST /solicitudes-rol` | Pedir un alta, cambio de rol o baja |
| `POST /solicitudes-rol/{id}/aprobar`, `/rechazar` | Dirección General decide |
| `GET /cuentas`, `POST /cuentas`, `PATCH /cuentas/{id}` | Ver y aplicar lo aprobado (O9) |

El detalle de cada uno está en
[`contracts/04-endpoints.md`](../../../../contracts/04-endpoints.md).

## Cambios a la base

La migración [`011_identidad_ajustes.sql`](../../../../db/migrations/011_identidad_ajustes.sql)
agrega lo que la 004 no previó. Hay que aplicarla en Neon antes de desplegar
(`python db/migrar.py app`).

## Pruebas

```bash
pytest tests/identidad -v
```

Las unitarias corren siempre. Las de integración necesitan un PostgreSQL con
PostGIS y un OPA, y se saltan si faltan. Para armarlos en local, mirá el
encabezado de [`tests/identidad/conftest.py`](../../../../tests/identidad/conftest.py).
En el CI las corre el job `identidad`.

La base de pruebas es desechable y nunca es Neon.

## Antes de desplegar

Es una configuración única en la nube, y sin ella el servicio no arranca.

- Crear el secreto `llave-cifrado-datos` en Secret Manager (32 bytes en base64 url).
- Crear la cuenta de servicio `verdeazul-edge` con `roles/run.invoker` sobre
  `verdeazul-api` y `roles/iam.serviceAccountUser` para `ci-despliegue`.
- Aplicar la migración 011 en `verdeazul-app`.
- Correr `python db/credenciales_prueba.py` para crear una cuenta de prueba por
  rol. Las contraseñas salen una sola vez en la terminal y no se guardan.

## Desviaciones respecto a la Parte 1

D-13 a D-16 en
[`docs/P2_Desviaciones_respecto_P1.md`](../../../../docs/P2_Desviaciones_respecto_P1.md).
