# Motor de autorización (F3)

Acá vive el cliente del punto de decisión. El `__init__.py` es el contrato
congelado; el cuerpo de `puede(...)` es lo que hay que implementar.

Las políticas en Rego están en [`services/policies/rego/`](../../../policies/rego/),
no acá. Esta carpeta es el lado Python: traduce la petición, consulta a OPA en
`localhost` y traduce la respuesta.

Orden sugerido para implementarlo:

1. Los **47 permisos sin condición**, que solo dependen del rol. Son más de la
   mitad del total y con eso ya hay algo que funciona de punta a punta.
2. **C8** (8 permisos) y **C1** (6), las de atributo simple: propietario y zona.
3. **C7** (10), la ventana de auditoría. Es la que más permisos cubre de una.
4. **C2**, **C11**, **C5**, que miran estados y dependen de F4.
5. **C3**, **C4**, **C10**, las de separación de deberes.
6. **C9**, la autorización vigente del tercero.
7. **C6 al final**: un solo permiso, pero es el más caro. Necesita PostGIS, el
   bloqueo de transacción, y depende de que la persona 4 tenga cargados los
   polígonos.

En total son 47 permisos sin condición y 37 con condición, que suman los 84 que
la matriz concede.

Cada celda se cierra con su prueba en [`tests/matriz/`](../../../../tests/matriz/).
No se marca como lista sin prueba, porque la tabla de cobertura del informe sale
de ahí.
