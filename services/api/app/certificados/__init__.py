"""O5 Certificados de carbono.

    firma.py          firmar con Ed25519 (2.3.6, D-10)
    verificacion.py   comprobar un archivo sin tocar la base (D-09)
    consultas.py      SQL y atributos para el motor
    rutas.py          los endpoints

Vacio a proposito: main.py importa el router desde rutas.py, igual que la
bitacora. Asi firma.py y verificacion.py se pueden probar sin levantar
FastAPI ni la base.
"""
