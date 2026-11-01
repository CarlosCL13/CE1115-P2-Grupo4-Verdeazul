# Roles de base de datos (F1)

Tres roles, ninguno dueño de las tablas. La aplicación **nunca** se conecta
como `neondb_owner`.

| Rol | Permisos | Lo usa |
|---|---|---|
| `app_rw` | SELECT, INSERT, UPDATE. Sin DELETE, sin DDL | El backend en ejecución |
| `app_migrate` | DDL | Solo las migraciones |
| `log_writer` | INSERT en la bitácora, nada más | El transmisor |

Hay que revocar explícitamente lo que `PUBLIC` trae por defecto: PostgreSQL le
concede permisos sobre el esquema `public` a todo el mundo si nadie lo quita.

Que `app_rw` no tenga DELETE no es exceso de celo. Ninguna de las 88 celdas de
la matriz concede el permiso E, así que la aplicación no debería poder borrar
ni por un error de código. Es la matriz aplicada también a la capa de datos.
