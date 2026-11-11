# Contrato 5: la sesión en tus endpoints

**Implementado.** Lo escribió el frente de identidad (persona 2) y lo usan
los 56 endpoints restantes. El código está en
[`services/api/app/auth/dependencias.py`](../services/api/app/auth/dependencias.py).

Este contrato responde la pregunta que cada uno se va a hacer al escribir su
primer endpoint. ¿De dónde saco el `Sujeto` que pide el contrato 02, y qué
hago si el motor dice que no?

## El endpoint típico

```python
from fastapi import APIRouter

from app import bd
from app.auth.dependencias import SesionCompleta, autorizar
from app.bitacora import registrar
from app.errores import ErrorAPI

router = APIRouter()


@router.get("/fincas/{finca_id}")
def ver_finca(finca_id: int, sesion: SesionCompleta) -> dict:
    with bd.transaccion() as cur:
        cur.execute("SELECT id, nombre, zona, propietario FROM fincas "
                    "WHERE id = %s", (finca_id,))
        finca = cur.fetchone()
        if finca is None:
            raise ErrorAPI(404, "no_existe")

        autorizar(sesion, "L", "O1", objeto="O1:%d" % finca_id, atributos={
            "finca.zona": finca["zona"],
            "finca.propietario_id": finca["propietario"],
        })

        registrar(accion="FINCA_CONSULTADA", sujeto=sesion.sujeto.id,
                  objeto="O1:%d" % finca_id, resultado="PERMITIDO")
    return {"id": finca["id"], "nombre": finca["nombre"]}
```

Tres líneas hacen todo el trabajo de seguridad.

`sesion: SesionCompleta` hace que FastAPI busque la sesión antes de entrar a
la función. Si no hay sesión, o le falta el segundo factor, o tiene una clave
temporal sin cambiar, la función ni se ejecuta y el cliente recibe 401.

`autorizar(...)` le pregunta al motor con `sesion.sujeto`. Si el motor niega,
registra el intento en la bitácora, revierte la transacción sin perder ese
evento y responde 403. No hay que escribir ni un `if`.

`registrar(...)` deja el rastro de lo que sí se hizo, en la misma transacción.

## Lo que trae la sesión

| Campo | Qué es |
|---|---|
| `sesion.sujeto` | El `Sujeto` del contrato 02, con el id ya convertido a texto |
| `sesion.cuenta` | El id de la cuenta, entero, para tus consultas SQL |
| `sesion.rol` | Uno de los 8 roles |
| `sesion.zonas` | Las zonas con asignación vigente hoy (sin revocar y sin vencer) |
| `sesion.usuario`, `sesion.nombre` | Para mostrar |

Las zonas se leen en cada petición, no al iniciar sesión. Si Dirección de
Certificación le quita una zona a un técnico, el técnico deja de verla en su
siguiente clic, sin volver a entrar.

## Los atributos van tal como salen de la base

`autorizar` convierte a texto todo atributo cuya clave termine en `_id`, así
que `finca["propietario"]` puede ir como entero. Es la regla "todo id viaja
como texto" del contrato 02, aplicada en un solo lugar para que nadie la
olvide. Si llamás directo a `servicio_consulta_autorizacion` en vez de
`autorizar`, la conversión es tuya.

## Acciones graves: reautenticación

P1 vuelve a pedir el factor antes de aprobar mediciones y enmiendas, emitir,
abrir y cerrar períodos y cambiar roles. Para esos endpoints se cambia
`SesionCompleta` por `SesionReautenticada`, y nada más.

```python
from app.auth.dependencias import SesionReautenticada

@router.post("/mediciones/{medicion_id}/aprobar")
def aprobar(medicion_id: int, sesion: SesionReautenticada) -> dict:
    ...
```

Si la persona no confirmó su contraseña (y su código TOTP, si lo tiene) en
los últimos cinco minutos, el backend responde 401
`reautenticacion_requerida`. El borde la manda a `/reautenticar` y la regresa
a la página donde estaba. No hay que hacer nada más en el borde.

Endpoints que según P1 llevan `SesionReautenticada`: aprobar medición y
enmienda, emitir certificado, abrir y cerrar período, y todo lo de O9 (ya
hecho).

## Listados: filtrar sin registrar cada fila

Un listado devuelve solo las filas que el sujeto puede ver. Para eso está
`consultar(...)`, que pregunta al motor sin registrar ni cortar. El patrón,
usado en `GET /personas` y `GET /cuentas`:

```python
general = consultar(sesion, "L", "O1")
if not general.permitido and general.condicion is None:
    autorizar(sesion, "L", "O1", objeto="O1:*")   # el rol no tiene L: 403

for fila in filas:
    if general.permitido or consultar(sesion, "L", "O1", atributos_de(fila)).permitido:
        visibles.append(fila)
```

Si el motor niega sin nombrar una condición, el rol no tiene el permiso y eso
es un intento denegado. Si niega nombrando una (C1, C7, C8), el rol sí tiene
el permiso y lo que falta es filtrar fila por fila.

## Lo que no es una celda de la matriz

Para acciones que ningún objeto cubre (quién aprueba una solicitud de cambio
de rol, quién crea una ventana de auditoría) está `exigir_rol(sesion,
{"DIRECCION_GENERAL"}, "crear una ventana de auditoria", "O11:ventana")`. Niega
por omisión, registra y responde 403 igual que `autorizar`. Cada uso tiene que
estar justificado en `docs/P2_Desviaciones_respecto_P1.md`.

## Errores

Todo error sale como `{"detail": "codigo"}`, con el mismo campo que usa
FastAPI. Para los tuyos, `raise ErrorAPI(409, "ya_cerrado", "El período ya
está cerrado.")`. El tercer argumento es un mensaje para la persona, sin
detalles internos.

| Estado | `detail` | Qué hace el borde |
|---|---|---|
| 401 | `sin_sesion` | Manda a `/entrar` |
| 401 | `segundo_factor_pendiente` | Manda a `/segundo-factor` |
| 401 | `cambio_de_clave_pendiente` | Manda a `/clave` |
| 401 | `reautenticacion_requerida` | Manda a `/reautenticar` y regresa |
| 403 | `denegado` | Dibuja "Acceso denegado" |

## En el borde

`services/edge/app/web.py` tiene `pedir(request, metodo, ruta, ...)`, que
llama al backend con la sesión de la persona y convierte esas respuestas en
la página que corresponde. Una página nueva queda así:

```python
from fastapi import APIRouter, Request
from app.web import pagina, pedir

router = APIRouter()

@router.get("/fincas")
def fincas(request: Request):
    datos = pedir(request, "GET", "/fincas").json()
    return pagina(request, "certificacion/fincas.html", fincas=datos["fincas"])
```

Todo formulario POST lleva el token CSRF y se comprueba antes de llamar al
backend:

```html
<input type="hidden" name="csrf" value="{{ csrf }}">
```

```python
from app.web import comprobar_csrf

@router.post("/fincas/nueva")
def finca_nueva(request: Request, csrf: str = Form("")):
    comprobar_csrf(request, csrf)
    ...
```

## Cuentas de prueba

`python db/credenciales_prueba.py` le pone contraseña a las once cuentas de
`db/semilla.sql` y las imprime una vez. Las que tienen rol con segundo factor
obligatorio (DG, DC, PA y verificadores) salen con su línea `otpauth://` para
cargarla en la aplicación autenticadora. Las contraseñas no van a ningún
archivo del repositorio.
