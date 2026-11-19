# Pruebas de la matriz (F3)

La evidencia del criterio de 25 puntos y la fuente de la tabla de cobertura del
informe (§5.1, punto 6).

```bash
pytest tests/matriz -v
```

La matriz vive como datos en [`conf_test_celdas.py`](conf_test_celdas.py), transcrita de
[`contracts/matriz.md`](../../contracts/matriz.md). Las pruebas se generan a
partir de esos datos, así que agregar una celda es editar una línea, no
escribir una prueba nueva.

## Las dos direcciones

| Familia | Casos | Estado |
|---|---|---|
| Lo que la matriz **no** concede se niega | 884 | Pasan |
| Lo que la matriz **sí** concede se permite | 84 | Pasan |

La primera familia es la que de verdad protege. Es fácil acordarse de probar
que un verificador puede aprobar; es fácil olvidar probar que un tercero
autorizado **no** puede leer la bitácora. Esas 884 son las que detectan que
alguien concedió de más.

## Dónde corren

En el job «Pruebas de la matriz» del CI, en cada pull request, contra un OPA
real que el job levanta antes de pytest. Si el motor no arranca, el job falla en
rojo: no puede quedar en verde con las pruebas saltadas. Junto con
`test_motor.py` son 977.
