# Roles de la base principal

Se aplican una sola vez, como dueño del proyecto:

```
python db/migrar.py roles
```

Es la única vez en todo el proyecto que se usa `neondb_owner`. De ahí en
adelante el esquema lo toca `app_migrate` y la aplicación corre como `app_rw`.

| Rol | Permisos | Lo usa |
|---|---|---|
| `app_migrate` | crear y alterar tablas | solo las migraciones |
| `app_rw` | SELECT, INSERT, UPDATE. Sin DELETE, sin DDL | el backend en ejecución |
| `outbox_rw` | leer y marcar la bandeja de salida | el transmisor |

Los dos roles de la bitácora, `log_writer` y `log_reader`, viven en el otro
proyecto y se crean en [`../bitacora/`](../bitacora/).

Que `app_rw` no tenga DELETE no es exceso de celo. Ninguna de las 88 celdas de
la matriz concede el permiso E, así que la aplicación no debería poder borrar
ni por un error de código. Es la matriz aplicada también a la capa de datos.

## Lo que hay que mirar al leer el archivo

**El `REVOKE` a `PUBLIC`.** PostgreSQL le concede permisos a todo el mundo si
nadie se los quita, y `PUBLIC` incluye a cualquier rol que se cree en el
futuro.

**Los privilegios por omisión.** Un `GRANT ON ALL TABLES` solo alcanza a las
tablas que ya existen, y cuando esto corre no existe ninguna. El
`ALTER DEFAULT PRIVILEGES FOR ROLE app_migrate` es lo que hace que toda tabla
creada después nazca con SELECT, INSERT y UPDATE para `app_rw` y sin DELETE.
Sin eso, cada migración tendría que acordarse, y el día que alguien lo olvide
la aplicación falla con `permission denied` ya desplegada.

**Que no hay contraseñas.** Los roles nacen `NOLOGIN` y el login se les da con
`migrar.py claves`. Ver [`../README.md`](../README.md).

## Un límite que no está en nuestras manos

`PUBLIC` puede leer `spatial_ref_sys`, y no se puede impedir. El permiso lo
otorgó `cloud_admin`, un rol interno de Neon, y en PostgreSQL solo se revoca lo
que uno mismo otorgó: el `REVOKE` corre sin error y no cambia nada.

Esa tabla son las definiciones de sistemas de coordenadas EPSG, datos de
referencia idénticos en toda instalación de PostGIS, sin nada de Verdeazul.
Pero va nombrado en el informe bajo «qué queda sin cubrir» de §5.2, en vez de
fingir que lo controlamos.
