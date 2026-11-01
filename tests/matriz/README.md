# Pruebas de la matriz (F3)

La evidencia del criterio de 25 puntos y la fuente de la tabla de cobertura del
informe (§5.1, punto 6).

```bash
pytest tests/matriz -v
```

La matriz vive como datos en [`conftest.py`](conftest.py), transcrita de
[`contracts/matriz.md`](../../contracts/matriz.md). Las pruebas se generan a
partir de esos datos, así que agregar una celda es editar una línea, no
escribir una prueba nueva.

## Las dos direcciones

| Familia | Casos | Estado hoy |
|---|---|---|
| Lo que la matriz **no** concede se niega | 884 | Pasan, y tienen que seguir pasando |
| Lo que la matriz **sí** concede se permite | 84 | `xfail` hasta que la persona 3 implemente |

La primera familia es la que de verdad protege. Es fácil acordarse de probar
que un verificador puede aprobar; es fácil olvidar probar que un tercero
autorizado **no** puede leer la bitácora. Esas 884 son las que detectan que
alguien concedió de más.

## Cómo avanza esto

Cada celda que la persona 3 implementa convierte un `xfail` en `xpass`. Cuando no quede
ningún `xfail`, la matriz está completa y la tabla de cobertura se genera desde
la salida de pytest.
