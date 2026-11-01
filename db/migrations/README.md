# Migraciones de `verdeazul-app`

SQL plano, numerado, que se aplica en orden y nunca se edita una vez fusionado.
Si algo está mal, se corrige con una migración nueva.

```
001_extensiones.sql     postgis
002_objetos.sql         las tablas de O1 a O10
003_indices.sql         GiST sobre certificados.poligono, y los demás
004_salida.sql          la bandeja de salida del patrón outbox
```

Se aplican con el rol **`app_migrate`**, nunca con `app_rw` ni con
`neondb_owner`. La aplicación en ejecución no puede alterar el esquema, y eso
es parte de lo que compensa que las credenciales de Neon sean estáticas (D-03).

Qué tiene que existir y por qué: [`contracts/01-esquema.md`](../../contracts/01-esquema.md).

**Todavía no hay ninguna migración escrita.** Es el siguiente paso y es el
contrato que desbloquea a los otros cuatro frentes.
