# Matriz de control de acceso

Transcripción de las Tablas 2.1 y 2.2 del documento de matrices de la Parte 1.
Esta es la referencia de trabajo: nadie debería tener que abrir el PDF.

8 roles x 11 objetos = **88 celdas**. Cada celda tiene que estar implementada y
probada. De aquí sale la tabla de cobertura del informe (§5.1, punto 6).

## Operaciones

| Símbolo | Permiso | | Símbolo | Permiso |
|---|---|---|---|---|
| L | Leer | | Cr | Cerrar |
| C | Crear | | Em | Emitir |
| M | Modificar | | An | Anular |
| E | Eliminar | | X | Exportar |
| A | Aprobar | | — | Ningún permiso |
| D | Devolver | | | |
| Ab | Abrir | | | |V

**E (eliminar) está en el vocabulario pero ningún rol lo recibe.** No es un
olvido: es una decisión de diseño. Nada se borra, todo se anula o se enmienda.

## Objetos

| | Objeto | | | Objeto |
|---|---|---|---|---|
| O1 | Catálogo de fincas | | O7 | Consentimientos y autorizaciones |
| O2 | Períodos de medición | | O8 | Asignaciones técnico–zona |
| O3 | Mediciones de biomasa | | O9 | Cuentas, roles y permisos |
| O4 | Enmiendas | | O10 | Credenciales propias |
| O5 | Certificados de carbono | | O11 | Bitácora de auditoría |
| O6 | Datos personales de dueños | | | |

## Matriz, O1 a O6

| Rol | O1 Fincas | O2 Períodos | O3 Mediciones | O4 Enmiendas | O5 Certificados | O6 Datos personales |
|---|---|---|---|---|---|---|
| Dirección General | L | L | L | L | L | L |
| Dirección de Certificación | L | L, Ab, Cr | L | L, Cr·C5 | L, An | — |
| Personal Administrativo | L, C, M | — | — | — | — | L, C, M |
| Técnico de campo | L·C1 | L | L·C1, C·C2 | L·C1, C·C11 | — | — |
| Verificador | L·C1 | L | L, C·(C1∧C2), A·C3, D·C3 | L, A·C4, D·C4 | L, Em·C6 | — |
| Auditor externo | L·C7 | L·C7 | L·C7, X·C7 | L·C7, X·C7 | L·C7, X·C7 | — |
| Dueño de finca | L·C8 | L | L·C8 | L·C8 | L·C8 | L·C8 |
| Tercero autorizado | — | — | — | — | L·C9 | — |

## Matriz, O7 a O11

| Rol | O7 Consentimientos | O8 Asignaciones | O9 Cuentas y roles | O10 Credenciales propias | O11 Bitácora |
|---|---|---|---|---|---|
| Dirección General | L | L | L | M | L, X |
| Dirección de Certificación | — | L, C, M | — | M | L, X |
| Personal Administrativo | L, C | — | L·C10, C·C10, M·C10 | M | L |
| Técnico de campo | — | L·C1 | — | M | — |
| Verificador | — | L·C1 | — | M | — |
| Auditor externo | — | — | — | M | L·C7, X·C7 |
| Dueño de finca | L·C8, C·C8, M·C8 | — | — | M | — |
| Tercero autorizado | — | — | — | M | — |

`L·C1` se lee «puede leer, pero solo si se cumple C1». Un permiso sin condición
depende únicamente del rol.

## Condiciones

| ID | Celda | Permiso | Regla verificable | Origen |
|---|---|---|---|---|
| **C1** | TC → O1, O3, O4, O8<br>VF → O1, O3, O8 | L, C | `finca.zona ∈ sujeto.zonas`: la finca pertenece a una zona con asignación vigente del sujeto | ABAC zona |
| **C2** | TC → O3<br>VF → O3 | C | `periodo.estado = ABIERTO` | Estado del sistema |
| **C3** | VF → O3 | A, D | `medicion.autor ≠ sujeto.id` ∧ el sujeto no registró ninguna otra medición de esa finca en ese período | SoD / HBAC-01 |
| **C4** | VF → O4 | A, D | `enmienda.solicitante ≠ sujeto.id` | SoD / SR-03 |
| **C5** | DC → O4 | Cr | `enmienda.estado = REVISADA` ∧ `solicitante ≠ sujeto.id` ∧ `revisor ≠ sujeto.id`: tres personas distintas obligatorias | SoD / SR-03 |
| **C6** | VF → O5 | Em | `medicion.estado = APROBADA` ∧ `medicion.autor ≠ sujeto.id` ∧ ningún certificado vigente tiene un polígono que se superponga con el de esta medición | SoD / SR-05 |
| **C7** | AE → O1, O2, O3, O4, O5, O11 | L, X | `hoy ∈ [auditoria.inicio, auditoria.fin]`. Fuera de la ventana el permiso **no se suspende, deja de existir** | HBAC-03 |
| **C8** | DF → O1, O3, O4, O5, O6, O7 | L, C, M | `finca.propietario = sujeto.id` | ABAC propietario |
| **C9** | TA → O5 | L | `autorizacion.tercero = sujeto.id` ∧ `hoy < autorizacion.vence` | HBAC-03 |
| **C10** | PA → O9 | L, C, M | Existe aprobación previa de DG para el cambio solicitado ∧ `aprobador.id ≠ sujeto.id` | SR-04 / CU-03 |
| **C11** | TC → O4 | C | `medicion.autor = sujeto.id` ∧ `periodo.estado = CERRADO` | Estado / SoD |

Cuando una condición no se cumple, el motor **deniega y registra el intento en
la bitácora**. La denegación es la respuesta por omisión en todos los casos.

## Dos decisiones de diseño que hay que respetar al implementar

**Ningún rol tiene M en O3.** Modificar una medición no se concede a nadie.
Toda corrección posterior al cierre del período pasa por una enmienda (O4), que
involucra tres personas distintas.

**ABAC quita permisos, nunca los agrega.** Un atributo que restringe una celda
no puede ampliar lo que el rol no tiene. Si el rol no lo tiene, ninguna
condición se lo da.



