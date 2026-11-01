# Esquema de `verdeazul-bitacora`

Instancia de Neon **separada** de la principal. Así se implementa la frontera
F6: quien comprometa la aplicación no puede borrar el rastro.

El rol `log_writer` solo tiene INSERT. Verificado en Neon: un rol creado por
SQL queda sin superusuario y sin `rolbypassrls`, así que la bitácora
solo-anexar de BI-01 es implementable de verdad y no solo de palabra.

No hay UPDATE ni DELETE para nadie. Un evento mal escrito se corrige con otro
evento, no editando el anterior.

Formato de los registros: [`contracts/03-evento-bitacora.md`](../../contracts/03-evento-bitacora.md).
