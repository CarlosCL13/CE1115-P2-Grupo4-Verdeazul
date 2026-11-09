# Esquema de `verdeazul-bitacora`

Instancia de Neon **separada** de la principal. Así se implementa la frontera
F6: quien comprometa la aplicación no puede borrar el rastro.

Se aplica como dueño de este proyecto, que es otro distinto al de la base
principal:

```
python db/migrar.py bitacora
```

Crea dos roles y la tabla `eventos`.

| Rol | Puede | Lo usa |
|---|---|---|
| `log_writer` | INSERT, nada más | el transmisor, al copiar eventos |
| `log_reader` | SELECT, nada más | la API, para las celdas L y X de O11 |

Ninguno puede UPDATE ni DELETE. Eso es lo que hace cierto el solo-anexar de
BI-01: no es una costumbre del equipo, es que el motor no lo permite. Un evento
mal escrito se corrige con otro evento, no editando el anterior.

`log_writer` tampoco tiene SELECT. No necesita releer lo que escribió, porque
el eslabón anterior de la cadena lo lleva él en la bandeja de salida, y no
dárselo significa que comprometer el transmisor no entrega el historial.

Hace falta `log_reader` porque la matriz da `L` sobre O11 a Dirección General,
Dirección de Certificación, Personal Administrativo y Auditor Externo. Alguien
tiene que poder consultar la bitácora.

Dos cosas que la tabla impone y no dependen de que nadie se acuerde:

```sql
resultado_valido        rechaza un resultado que no sea PERMITIDO o DENEGADO
denegado_lleva_motivo   rechaza denegar sin decir por qué
```

La columna `secuencia` existe porque la cadena HMAC necesita un orden total.
`momento` no sirve: dos eventos pueden caer en el mismo microsegundo y entonces
no se sabe cuál eslabón va antes.

Formato de los registros: [`contracts/03-evento-bitacora.md`](../../contracts/03-evento-bitacora.md).
