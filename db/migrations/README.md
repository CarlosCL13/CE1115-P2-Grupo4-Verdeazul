# Migraciones de `verdeazul-app`

SQL plano, numerado, que se aplica en orden con `app_migrate`:

```
python db/migrar.py app
```

Un archivo ya aplicado **no se edita nunca**. `migrar.py` guarda la huella de
cada uno y se niega a seguir si cambió. Si algo está mal, se corrige con una
migración nueva.

El número lo toma quien crea el archivo. Si dos personas toman el mismo, lo
resuelve el pull request.

## Plan

```
002_cimientos.sql     zonas, cuentas
003_nucleo.sql        fincas (PostGIS + GiST), periodos_medicion, mediciones
004_identidad.sql     credenciales, sesiones, datos_personales
005_atributos.sql     asignaciones_zona, consentimientos,
                      ventanas_auditoria, solicitudes_rol
006_cierre.sql        enmiendas, certificados, eventos_pendientes
```

La 001 no está aquí: crea los roles y va en [`../roles/`](../roles/), porque se
aplica como dueño y una sola vez.

La 002 es la urgente. Hasta que exista `cuentas`, nadie puede crear una tabla
con llave foránea hacia ella, y once de las dieciséis la referencian.

Qué tabla lleva qué columnas y por qué:
[`contracts/01-esquema.md`](../../contracts/01-esquema.md).

**Todavía no hay ninguna escrita.**

## Dos cosas que no se pueden olvidar

En la 003, el `GRANT` por columna sobre `mediciones`:

```sql
REVOKE UPDATE ON mediciones FROM app_rw;
GRANT  UPDATE (estado, revisada_por, motivo_devolucion) ON mediciones TO app_rw;
```

Los privilegios por omisión dan UPDATE sobre toda la tabla, así que hay que
quitarlo y volver a darlo por columna. Eso impide que la aplicación modifique
`biomasa_toneladas`, que es «ningún rol tiene M en O3» aplicado por el motor.

En la 006, el `GRANT` a `outbox_rw` sobre `eventos_pendientes`, que es la única
tabla que ese rol debe ver.
