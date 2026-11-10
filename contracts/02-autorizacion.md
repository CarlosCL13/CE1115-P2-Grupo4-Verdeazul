# Contrato 2: la función de autorización

**Esta firma está congelada.** La llaman las personas 1, 2, 4 y 5 desde todos
sus endpoints, así que cambiarla rompe el trabajo de cuatro.

La implementación vive en [`services/api/app/authz/`](../services/api/app/authz/)
y le pregunta al motor de políticas, OPA, que corre como contenedor adjunto en
`127.0.0.1:8181`. Las reglas están en
[`services/policies/rego/`](../services/policies/rego/).

## Cómo se pregunta

```python
from app.authz.Modelos_opa import Objeto, Sujeto
from app.authz.Servicio_opa import servicio_consulta_autorizacion

decision = servicio_consulta_autorizacion(
    sujeto=Sujeto(id="7", rol="VERIFICADOR", zonas=("CS",)),
    operacion="Em",
    objeto=Objeto(tipo="O5", atributos={
        "medicion.estado": "APROBADA",
        "medicion.autor_id": "5",
        "contexto.poligono_traslapa_certificado_vigente": False,
    }),
)

if not decision.permitido:
    # 403, y el intento se registra en la bitacora
    ...
```

`app/authz/__init__.py` está vacío, así que se importa desde los módulos y no
desde `app.authz`.

## Las tres piezas de la pregunta

**Sujeto**: quién pregunta.

| Campo | Tipo | De dónde sale |
|---|---|---|
| `id` | str | La sesión. El id de `cuentas`, **convertido a texto** |
| `rol` | str | Uno de los 8 roles, igual que el ENUM `rol_sujeto` |
| `zonas` | tuple[str, ...] | Las asignaciones vigentes de `asignaciones_zona`, con el código de dos letras (`"PN"`, `"CS"`). Lo usa C1 |

**Operación**: qué quiere hacer. Una de las once letras de la matriz:
`L C M E A D Ab Cr Em An X`.

**Objeto**: sobre qué. El `tipo` es `O1` a `O11`. Los `atributos` son los que
la condición necesita, con las claves exactas de la tabla de abajo.

## Todo id viaja como texto

Los id de la base son enteros y `Sujeto.id` es texto. Si un endpoint pasa el
entero tal como sale de la consulta, Rego compara `"6" != 6`, que da verdadero
porque son de tipos distintos.

Comprobado contra el motor: un verificador con id `"6"` **logra aprobar su
propia medición** si `medicion.autor_id` llega como `6`. Lo mismo pasa en todas
las condiciones que comparan con `!=`, que son justo las de separación de
deberes: C3, C4, C5, C6 y C10. Las que comparan con `==` (C8, C9, C11) fallan
al revés y niegan siempre.

Regla: **todo `*_id` que se mande al motor va con `str(...)`**, igual que el
id del sujeto.

## Qué atributos manda cada condición

Si falta un atributo, la condición no se cumple y se niega. Mandar de más no
hace daño.

| Condición | Claves | Valor que cumple |
|---|---|---|
| C1 zona | `finca.zona` | uno de `sujeto.zonas` |
| C2 período abierto | `periodo.estado` | `"ABIERTO"` |
| C3 aprobar medición | `medicion.autor_id`, `contexto.sujeto_midio_en_finca_periodo` | distinto del sujeto, `False` |
| C4 revisar enmienda | `enmienda.solicitante_id` | distinto del sujeto |
| C5 cerrar enmienda | `enmienda.estado`, `enmienda.solicitante_id`, `enmienda.revisor_id` | `"REVISADA"`, los dos distintos del sujeto |
| C6 emitir certificado | `medicion.estado`, `medicion.autor_id`, `contexto.poligono_traslapa_certificado_vigente` | `"APROBADA"`, distinto del sujeto, `False` |
| C7 ventana de auditoría | `auditoria.inicio`, `auditoria.fin` | fechas `AAAA-MM-DD` que encierran hoy |
| C8 propietario | `finca.propietario_id` | igual al sujeto |
| C9 tercero autorizado | `autorizacion.tercero_id`, `autorizacion.vence` | igual al sujeto, fecha posterior a hoy |
| C10 cambio aprobado | `cambio.aprobador_id`, `cambio.aprobador_rol` | distinto del sujeto, `"DIRECCION_GENERAL"` |
| C11 enmienda propia | `medicion.autor_id`, `periodo.estado` | igual al sujeto, `"CERRADO"` |

Las claves `contexto.*` no son columnas: las calcula el endpoint con una
consulta antes de preguntar. `contexto.hoy` lo agrega
`servicio_consulta_autorizacion` solo, no hay que mandarlo.

Para O8, C1 usa la misma clave `finca.zona` aunque una asignación no tenga
finca detrás: se manda la zona de la asignación.

## Qué devuelve

```python
@dataclass(frozen=True)
class Decision:
    permitido: bool
    motivo: str                       # legible, va a la bitacora
    condicion: str | None = None      # "C6" si fallo una condicion, None si fue el rol
    version_politica: str | None = None
```

El `motivo` no se le muestra al usuario: va a la bitácora. Al cliente se le
responde 403 sin detalles, porque el detalle revela estructura interna.

## Las cuatro reglas que no se negocian

1. **Denegación por omisión.** Lo que no está concedido en la matriz, se niega.
2. **Si el motor falla, se niega.** Un error de evaluación no es un permiso.
   `servicio_consulta_autorizacion` ya lo hace: si OPA no contesta, devuelve
   `permitido=False`.
3. **ABAC quita, nunca agrega.** Una condición no puede conceder lo que el rol
   no tiene.
4. **Toda denegación se registra.** El intento fallido es evidencia y el
   enunciado pide una captura de uno (§5.1, punto 7).

## Por qué esto vive en el servidor

§2.3 del enunciado: «Ocultar un botón en la interfaz no es un control: el
servidor debe rechazar la operación». La interfaz puede esconder lo que quiera
por comodidad, pero **cada endpoint llama a `servicio_consulta_autorizacion(...)`
sin excepción**. Si un endpoint no la llama, es un agujero, no una
optimización.
