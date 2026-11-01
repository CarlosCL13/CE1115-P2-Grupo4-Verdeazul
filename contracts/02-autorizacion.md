# Contrato 2: la función de autorización

**Esta firma está congelada.** La llaman las personas 1, 2, 4 y 5 desde todos
sus endpoints, así que cambiarla rompe el trabajo de cuatro.

La implementación vive en [`services/api/app/authz/`](../services/api/app/authz/)
y hoy **deniega todo**. Eso es correcto y es a propósito: ver el README de
contratos.

## Cómo se pregunta

```python
from app.authz import puede, Sujeto, Objeto

decision = puede(
    sujeto=Sujeto(id="u-42", rol="VERIFICADOR", zonas=["norte", "atlantica"]),
    operacion="Em",
    objeto=Objeto(tipo="O5", atributos={"medicion.estado": "APROBADA"}),
)

if not decision.permitido:
    # 403, y el intento se registra en la bitacora
    ...
```

## Las tres piezas de la pregunta

**Sujeto** — quién pregunta.

| Campo | Tipo | De dónde sale |
|---|---|---|
| `id` | str | La sesión |
| `rol` | str | Uno de los 8 roles |
| `zonas` | list[str] | Las asignaciones vigentes (O8). Lo usa C1 |

**Operación** — qué quiere hacer. Una de las once letras de la matriz:
`L C M E A D Ab Cr Em An X`.

**Objeto** — sobre qué. El `tipo` es `O1` a `O11`. Los `atributos` son los que
la condición necesita, con los nombres **exactos** del contrato 1:
`finca.zona`, `periodo.estado`, `medicion.autor`, `enmienda.solicitante`, etc.

## Qué devuelve

```python
@dataclass(frozen=True)
class Decision:
    permitido: bool
    motivo: str               # legible, va a la bitacora
    condicion: str | None     # "C6" si fallo una condicion, None si fue el rol
```

El `motivo` no se le muestra al usuario: va a la bitácora. Al cliente se le
responde 403 sin detalles, porque el detalle revela estructura interna.

## Las cuatro reglas que no se negocian

1. **Denegación por omisión.** Lo que no está concedido en la matriz, se niega.
2. **Si el motor falla, se niega.** Un error de evaluación no es un permiso.
3. **ABAC quita, nunca agrega.** Una condición no puede conceder lo que el rol
   no tiene.
4. **Toda denegación se registra.** El intento fallido es evidencia y el
   enunciado pide una captura de uno (§5.1, punto 7).

## Por qué esto vive en el servidor

§2.3 del enunciado: «Ocultar un botón en la interfaz no es un control: el
servidor debe rechazar la operación». La interfaz puede esconder lo que quiera
por comodidad, pero **cada endpoint llama a `puede(...)` sin excepción**. Si un
endpoint no la llama, es un agujero, no una optimización.
