# 1. Recrear los contenedores
docker compose down
docker compose up -d --build

# 2. Comprobar que los dos estén arriba
docker compose ps

# 3. Instalar pytest dentro del contenedor (una vez, se pierde al recrear), esto es solo para el test, no va en producción
docker compose exec --user root api pip install pytest

# 4. Correr las pruebas
docker compose exec api python -m pytest tests/matriz/test_motor.py -v
docker compose exec api python -m pytest tests/matriz/test_celdas.py -v -p no:cacheprovider

