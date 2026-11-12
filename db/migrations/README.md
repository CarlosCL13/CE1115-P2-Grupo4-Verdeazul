# Migraciones de `verdeazul-app`

SQL plano, numerado, aplicado en orden con `app_migrate`:

```
python db/migrar.py app
```

Cada archivo corre dentro de su propia transacción. Si falla a la mitad se
revierte entero, así que nunca queda media tabla creada.

Un archivo ya aplicado **no se edita**. `migrar.py` guarda su huella y se
niega a seguir si cambió. Si algo está mal, se corrige con una migración
nueva.

## Los archivos

Uno por dueño, para que cuatro personas no editen el mismo y se peleen en
cada pull request.

| Archivo | Quién | Tablas |
|---|---|---|
| `002_zonas.sql` | p4 | `zonas` |
| `003_cuentas.sql` | p2 | `cuentas` |
| `004_identidad.sql` | p2 | `credenciales`, `sesiones`, `datos_personales`, `solicitudes_rol` |
| `005_fincas_periodos.sql` | p4 | `fincas`, `periodos_medicion` |
| `006_mediciones.sql` | p4 | `mediciones` |
| `007_atributos.sql` | p1 | `asignaciones_zona`, `consentimientos`, `ventanas_auditoria` |
| `008_enmiendas.sql` | p1 | `enmiendas` |
| `009_certificados.sql` | p5 | `certificados` |
| `010_salida.sql` | p5 | `eventos_pendientes` |
| `011_identidad_ajustes.sql` | p2 | columnas de sesión, segundo factor y solicitudes de alta y baja |
| `012_transmisor_y_certificados.sql` | p1 | el eslabón en la bandeja, y permisos por columna en la bandeja y en `certificados` |

El orden no es estético, lo imponen las llaves foráneas. `consentimientos`
apunta a `fincas`, así que la 007 va después de la 005. `enmiendas` y
`certificados` apuntan a `mediciones`, así que van después de la 006.

La 001 no está aquí: crea los roles, va en [`../roles/`](../roles/) y se
aplica como dueño una sola vez.

Qué lleva cada tabla y por qué:
[`contracts/01-esquema.md`](../../contracts/01-esquema.md).

## Dos cosas que no son solo tablas

En la **006**, el `GRANT` por columna sobre `mediciones`. Los privilegios por
omisión dan UPDATE sobre toda la tabla, así que hay que quitarlo y devolverlo
solo sobre `estado`, `revisada_por`, `revisada_en` y `motivo_devolucion`. Eso
impide que la aplicación toque `biomasa_toneladas`, que es «ningún rol tiene M
en O3» aplicado por el motor.

En la **010**, el `GRANT` a `outbox_rw`, que ve esa tabla y ninguna otra, y de
ella solo puede cambiar `enviado_en`.

## Lo que las restricciones ya resuelven

Parte de las condiciones de la matriz está escrita como `CHECK`, así que no
depende de que el código se acuerde:

| Restricción | Qué cubre |
|---|---|
| `revisor_distinto_del_autor` | la mitad de C3 |
| `revisor_distinto_del_solicitante` | C4 |
| `cierre_de_una_tercera_persona` | C5 |
| `aprobador_distinto_del_solicitante` | la mitad de C10 |

La otra mitad de C3 y de C10 la comprueba el PDP, porque miran otras filas o
el rol de quien actúa, y eso no cabe en un `CHECK`.

## Sobre los id

`integer GENERATED ALWAYS AS IDENTITY` en las catorce. Cuatro bytes dan hasta
2100 millones de filas por tabla, de sobra para lo que este sistema va a
guardar. `zonas` es la única con
llave de texto, dos letras (`PN`, `PC`, `PS`, `CN`, `CS`, `VC`, `ZN`), porque
ahí las iniciales son la llave natural y son siete filas que no cambian.

`IDENTITY` y no `serial`: la secuencia pertenece a la columna, así que con el
permiso de INSERT sobre la tabla alcanza y no hay que dar `GRANT USAGE` sobre
una secuencia aparte. Con quince tablas, eso son quince oportunidades de
olvidarse y que la aplicación falle con `permission denied` ya desplegada.

`ALWAYS` significa que la aplicación no puede fijar el id ni por error. Los
datos de prueba que necesiten ids fijos lo dicen explícitamente:

```sql
INSERT INTO cuentas (id, usuario, nombre, rol)
OVERRIDING SYSTEM VALUE
VALUES (1, 'dg', 'Direccion General', 'DIRECCION_GENERAL');
```

Que los id sean secuenciales deja contar cuántos certificados hay. Lo
asumimos: el control de acceso no depende de que el id sea impredecible, y
probar `/certificados/2` sin permiso es justo lo que hay que demostrar
rechazado el 19 de noviembre.
