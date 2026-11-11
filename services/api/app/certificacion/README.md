# Certificación

Acá viven las fincas (O1), los períodos de medición (O2) y las mediciones de
biomasa (O3). Es lo que alimenta a los certificados: una medición aprobada de
una finca con polígono válido es la materia prima de la emisión.

Si vas a escribir un endpoint que lea estos objetos, por ejemplo los
certificados o las enmiendas, usá `consultas.py` para armar los atributos que
el motor necesita. No los calcules cada uno por su cuenta.

## Qué hay en cada lugar

| Archivo | Qué hace |
|---|---|
| `consultas.py` | Atributos para C1, C2, C3, C7 y C8, el filtro previo por rol y las consultas base |
| `estados.py` | Los estados de períodos y mediciones, y las transiciones que se permiten |
| `fincas.py` | O1, con la validación del polígono |
| `periodos.py` | O2, abrir y cerrar con reautenticación |
| `mediciones.py` | O3, registrar, aprobar, devolver y exportar |
| `rutas.py` | Junta los tres routers en uno |

Las pantallas están en
[`services/edge/app/certificacion.py`](../../../edge/app/certificacion.py) y
sus plantillas en `services/edge/templates/certificacion/`.

## Lo que no se debe romper

1. **Una medición no se modifica.** No existe ninguna ruta que cambie la
   biomasa, y la base lo refuerza: `app_rw` solo tiene UPDATE sobre las
   columnas de la decisión (migración 006). Corregir una medición decidida es
   una enmienda (O4).
2. **C3 se decide con dos mitades.** El motor compara el autor con quien
   aprueba, y este módulo calcula si el sujeto ya midió esa finca en ese período
   (`contexto.sujeto_midio_en_finca_periodo`), porque eso mira otras filas.
   Si el atributo falta, el motor niega.
3. **Todo `*_id` que va al motor viaja como texto.** Un entero hace que C3
   conceda de más.
4. **El período se bloquea al registrar y al cerrar.** `FOR SHARE` al
   registrar una medición y `FOR UPDATE` al cerrar, para que no entre una
   medición justo mientras el período se cierra y C2 deje de ser cierta.
5. **Un período no cierra con mediciones REGISTRADAS.** Las DEVUELTAS no
   cuentan, porque su autor no las puede corregir.
6. **El polígono se valida dos veces.** La forma en Python y después
   `ST_IsValid` en PostGIS. Sobre un polígono inválido `ST_Intersects` devuelve
   cualquier cosa y C6 dejaría de ser confiable. La tabla además tiene un CHECK.
7. **No se delatan ids.** Una finca o medición que no existe responde 403, y no
   404, a quien no puede verlas todas. Si no, compararía respuestas para saber
   qué ids existen.
8. **`GET /mediciones/exportar` va antes de `GET /mediciones/{id}`**, para que
   "exportar" no se tome por un id.
9. **El auditor sin ventana vigente no recibe una lista vacía, recibe 403.** Su
   condición (C7) es de él y no de la fila, y fuera de la ventana el permiso
   deja de existir.

## Endpoints de este frente

| Método y ruta | Qué hace |
|---|---|
| `GET /fincas`, `GET /fincas/{id}` | Ver fincas (L, con C1, C7 o C8 según el rol) |
| `POST /fincas`, `PATCH /fincas/{id}` | Registrar y corregir una finca (Personal Administrativo) |
| `GET /periodos`, `GET /periodos/{id}` | Ver períodos |
| `POST /periodos` | Abrir un período nuevo (Ab), D-17 |
| `POST /periodos/{id}/abrir`, `/cerrar` | Reabrir y cerrar (Ab, Cr), con reautenticación |
| `GET /mediciones`, `GET /mediciones/{id}` | Ver mediciones |
| `POST /mediciones` | Registrar (C2, y el técnico además en su zona, D-18) |
| `POST /mediciones/{id}/aprobar`, `/devolver` | El verificador decide (C3). Aprobar pide reautenticación y devolver pide motivo |
| `GET /mediciones/exportar` | CSV para el auditor (C7) |

El detalle está en [`contracts/04-endpoints.md`](../../../../contracts/04-endpoints.md).

## Pruebas

```bash
pytest tests/certificacion -v
```

Son de integración. Necesitan un PostgreSQL con PostGIS y un OPA, y se saltan
si no hay base configurada. Para armarlos en local, mirá el encabezado de
[`tests/certificacion/conftest.py`](../../../../tests/certificacion/conftest.py).
En el CI las corre el job `identidad`, porque usa la misma base y el mismo motor.
La base de pruebas es desechable y nunca es Neon.

## Desviaciones respecto a la Parte 1

D-17 y D-18 en
[`docs/P2_Desviaciones_respecto_P1.md`](../../../../docs/P2_Desviaciones_respecto_P1.md).
