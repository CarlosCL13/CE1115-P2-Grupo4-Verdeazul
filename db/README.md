# Base de datos

PostgreSQL 18.6 en Neon, con PostGIS 3.6.4 en la base principal. Dos proyectos
separados, que es como se implementa la frontera F6 del diseño: quien
comprometa la aplicación no alcanza el rastro de auditoría.

| Carpeta | Qué hay | Con qué rol se aplica |
|---|---|---|
| [`roles/`](roles/) | Los roles de la base principal | el dueño, una sola vez |
| [`migrations/`](migrations/) | El esquema de `verdeazul-app` | `app_migrate` |
| [`bitacora/`](bitacora/) | El esquema de `verdeazul-bitacora` | el dueño de ese proyecto |
| [`migrar.py`](migrar.py) | El que las aplica y lleva la cuenta | |

## Cómo arrancar

Las bases ya están creadas y los roles ya existen. Lo que necesitás es el
`.env`, que **te lo pasa Carlos por fuera del chat del grupo**, porque lleva
las cinco contraseñas.

```
.venv/Scripts/python.exe -m pip install -r db/requirements.txt
.venv/Scripts/python.exe db/migrar.py estado
```

Si `estado` lista las migraciones, ya está. Para aplicar las que falten:

```
.venv/Scripts/python.exe db/migrar.py app
```

Un archivo ya aplicado nunca se edita: `migrar.py` guarda su huella y se niega
a seguir si cambió. Si algo está mal, se corrige con una migración nueva.

### Si preferís tu propia base

Opcional, y sirve si vas a escribir migraciones y no querés romperle el
esquema a los demás. Creás dos proyectos tuyos en Neon, corrés
`CREATE EXTENSION postgis` en el principal, generás cinco contraseñas con
`secrets.token_urlsafe(24)`, llenás tu `.env` a partir de `.env.example`, y
después:

```
python db/migrar.py roles      # crea app_migrate, app_rw, outbox_rw
python db/migrar.py bitacora   # crea log_writer, log_reader y la tabla eventos
python db/migrar.py claves     # les pone contraseña
python db/migrar.py app        # el esquema
```

Las cadenas terminan en `?sslmode=verify-full`. No agregues `sslrootcert`: la
ruta del almacén de certificados la pone el código con `certifi`, porque
depende de la máquina.

## Los cinco roles

Ninguno es dueño de nada. La aplicación nunca se conecta como `neondb_owner`:
esa cuenta se usa una sola vez, para crear las demás.

| Rol | Proyecto | Puede | No puede |
|---|---|---|---|
| `app_migrate` | app | crear y alterar tablas | atender peticiones |
| `app_rw` | app | SELECT, INSERT, UPDATE | **DELETE**, crear tablas |
| `outbox_rw` | app | leer y marcar la bandeja de salida | todo lo demás |
| `log_writer` | bitácora | INSERT en `eventos` | **leer**, alterar, borrar |
| `log_reader` | bitácora | SELECT en `eventos` | escribir |

Dos de esas casillas hay que poder explicarlas en la defensa.

`app_rw` sin DELETE, porque ninguna de las 88 celdas de la matriz concede el
permiso E. La aplicación no debería poder borrar ni por un error de código.

`log_writer` sin SELECT, porque el transmisor no necesita releer lo que
escribió, y no dárselo significa que comprometerlo no entrega el historial.

Las cinco filas están verificadas contra Neon intentando cada operación
prohibida: 17 de 17 dieron lo esperado.

## Secretos

El `.env` está en `.gitignore` y ahí se queda. Una credencial versionada anula
el criterio completo de gestión de secretos, 12 puntos, aunque el sistema
funcione, y git conserva el historial aunque después se borre.

Por eso ningún `.sql` lleva contraseñas. PostgreSQL no acepta parámetros en
DDL, así que lo natural sería escribir `CREATE ROLE app_rw LOGIN PASSWORD
'...'`, y eso es justo el error. Los roles nacen `NOLOGIN` y el login se les da
con `migrar.py claves`, que compone el `ALTER ROLE` en memoria desde el
entorno. Se versiona la política de permisos; la contraseña no es política.

Antes de desplegar conviene cambiar la contraseña de `app_rw` con
`migrar.py claves`, para que la que corre en producción solo exista en Secret
Manager. Es higiene, no urgencia.
