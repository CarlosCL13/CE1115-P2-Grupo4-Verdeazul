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

## Cómo armar tu `.env`

El `.env` es el archivo con las cadenas de conexión y las contraseñas. Está en
`.gitignore` y nunca entra al repositorio, así que cada quien tiene el suyo en
su máquina.

Hay dos caminos. Si solo vas a **usar** la base, pedile el `.env` a Carlos y
saltá al paso 5. Si vas a **escribir migraciones**, conviene tener la tuya para
no romperle el esquema a los demás, y entonces seguí los cinco pasos.

### 1. Creá dos proyectos en Neon

En [neon.tech](https://neon.tech), PostgreSQL 18, región AWS us-east-1. Uno
para la base principal y otro para la bitácora, porque viven separadas a
propósito.

En el **principal**, abrí el SQL Editor y corré:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

En el de bitácora no hace falta: esa base guarda texto.

### 2. Instalá lo que necesita el runner

```
.venv/Scripts/python.exe -m pip install -r db/requirements.txt
```

### 3. Generá cinco contraseñas

```
.venv/Scripts/python.exe -c "import secrets; [print(secrets.token_urlsafe(24)) for _ in range(5)]"
```

Salen en formato seguro para URL, así que no hay que escapar nada al pegarlas
en una cadena de conexión.

### 4. Llená el `.env`

```
cp .env.example .env
```

Por ahora **solo seis líneas**. Las dos cadenas de dueño salen de la consola de
Neon, en Dashboard → Connect, con el rol `neondb_owner`:

```
VERDEAZUL_OWNER_URL=postgresql://neondb_owner:...@ep-xxx.../neondb?sslmode=verify-full
VERDEAZUL_BITACORA_OWNER_URL=postgresql://neondb_owner:...@ep-yyy.../neondb?sslmode=verify-full

CLAVE_APP_MIGRATE=la-primera-que-generaste
CLAVE_APP_RW=la-segunda
CLAVE_OUTBOX_RW=la-tercera
CLAVE_LOG_WRITER=la-cuarta
CLAVE_LOG_READER=la-quinta
```

Neon da la cadena terminada en `?sslmode=require`. Cambiá ese final por
`?sslmode=verify-full`, que es lo que prometió la Parte 1. No agregues
`sslrootcert`: esa ruta la pone el código con `certifi`, porque depende de la
máquina.

Creá los roles y ponerles contraseña:

```
.venv/Scripts/python.exe db/migrar.py roles
.venv/Scripts/python.exe db/migrar.py bitacora
.venv/Scripts/python.exe db/migrar.py claves
```

Ahora completá las **cinco cadenas que faltan**, tomando la cadena de dueño del
proyecto que corresponda y cambiándole usuario y contraseña. Ojo con el host:
`log_writer` y `log_reader` viven en el proyecto de bitácora, que tiene uno
distinto.

```
VERDEAZUL_MIGRATE_URL=postgresql://app_migrate:...@ep-xxx.../neondb?sslmode=verify-full
VERDEAZUL_DB_URL=postgresql://app_rw:...@ep-xxx.../neondb?sslmode=verify-full
VERDEAZUL_OUTBOX_URL=postgresql://outbox_rw:...@ep-xxx.../neondb?sslmode=verify-full
VERDEAZUL_BITACORA_URL=postgresql://log_writer:...@ep-yyy.../neondb?sslmode=verify-full
VERDEAZUL_BITACORA_LECTURA_URL=postgresql://log_reader:...@ep-yyy.../neondb?sslmode=verify-full
```

Falta una última, la llave con la que se busca por cédula sin descifrarla:

```
.venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

```
LLAVE_BUSQUEDA_CEDULA=lo-que-salio
```

### 5. Aplicá el esquema y comprobá

```
.venv/Scripts/python.exe db/migrar.py app
.venv/Scripts/python.exe db/migrar.py estado
```

`estado` lista qué migraciones están aplicadas y cuáles faltan. Si las once
aparecen con fecha, ya está.

### 6. Credenciales de prueba

Con la semilla cargada (`migrar.py semilla`), falta darle contraseña a las
cuentas. Antes, agregá al `.env` la llave de cifrado, **la misma que está en
Secret Manager** como `llave-cifrado-datos` (pedísela a quien la creó, o
creala vos y subila con el mismo valor):

```
LLAVE_CIFRADO_DATOS=la-misma-de-secret-manager
```

```
.venv/Scripts/python.exe db/credenciales_prueba.py
```

Genera una contraseña al azar para cada una de las once cuentas, activa el
segundo factor de las que lo exigen (DG, DC, PA y verificadores), registra los
datos personales de los dos dueños y lo imprime todo **una sola vez**.
Guardalo en el gestor de contraseñas del grupo. Ninguna de esas credenciales
va a un archivo del repositorio: una credencial versionada anula el criterio
de secretos aunque sea de prueba.

`db/credenciales_prueba.py dg pa` regenera solo esas dos, y `--sin-totp` las
deja sin segundo factor para activarlo desde la pantalla, con el QR.

Un archivo ya aplicado nunca se edita: `migrar.py` guarda su huella y se niega
a seguir si cambió. Si algo está mal, se corrige con una migración nueva.

### Si algo falla

`Falta VERDEAZUL_X en el .env` dice exactamente qué variable no está.

`no pide verify-full` significa que dejaste el `?sslmode=require` que da Neon.

`password authentication failed` casi siempre es haber puesto la contraseña de
un rol en la cadena de otro, o haber usado el host del proyecto equivocado.

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
