"""Bitacora de auditoria (O11). Ver contracts/03-evento-bitacora.md.

`from app.bitacora import registrar` entrega la funcion, no el modulo.
"""

from app.bitacora.registrar import registrar

__all__ = ["registrar"]
