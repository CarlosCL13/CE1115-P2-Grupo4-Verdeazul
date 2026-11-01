# Politicas de autorizacion de Verdeazul. Punto de decision (PDP).
#
# RELLENO: no concede nada todavia. Ver contracts/02-autorizacion.md.
#
# La matriz completa esta en contracts/matriz.md. Cada celda que se implemente
# aqui necesita su prueba en autorizacion_test.rego y en tests/matriz/.

package verdeazul.autorizacion

import rego.v1

# Denegacion por omision. Es la regla mas importante del archivo: lo que no
# esta concedido explicitamente, se niega.
default permitir := false

default motivo := "denegado por omision: ninguna regla concede este permiso"

# Ningun rol recibe el permiso E en ninguna celda de la matriz. No es un
# olvido del diseno: nada se borra, todo se anula o se enmienda.
motivo := "la operacion E (eliminar) no se concede a ningun rol" if {
	input.operacion == "E"
}

# ---------------------------------------------------------------------------
# A PARTIR DE AQUI VAN LAS REGLAS. Plantilla de una celda sin condicion:
#
#   permitir if {
#       input.sujeto.rol == "DIRECCION_GENERAL"
#       input.objeto.tipo == "O1"
#       input.operacion == "L"
#   }
#
# Plantilla de una celda con condicion, C8 como ejemplo:
#
#   permitir if {
#       input.sujeto.rol == "DUENO_FINCA"
#       input.objeto.tipo == "O1"
#       input.operacion == "L"
#       input.objeto.atributos["finca.propietario"] == input.sujeto.id
#   }
#
# Regla de oro: una condicion solo puede QUITAR permisos, nunca agregarlos. Si
# el rol no tiene el permiso en la matriz, ninguna condicion se lo da.
# ---------------------------------------------------------------------------
