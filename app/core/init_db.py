import importlib
import pkgutil

import app.models  # noqa: F401
from app.core.database import Base, get_engine

# =========================================================
# INIT DB
# =========================================================


def main():
    """
    Inicializa la base de datos:
    - Crea todas las tablas definidas en los modelos
    - Muestra las tablas registradas en SQLAlchemy
    """

    engine = get_engine()

    # IMPORTANTE:
    # `Base.metadata` solo contiene tablas de modelos ORM que hayan sido importados.
    # `app.models.__init__` es intencionalmente ligero, por lo que aquí importamos
    # dinámicamente todos los submódulos para registrar tablas antes del create_all.
    for m in pkgutil.iter_modules(app.models.__path__, app.models.__name__ + "."):
        # En algunos entornos pueden existir ficheros accidentales tipo "foo 2.py"
        # (no válidos como identificador Python) que duplican modelos/tablas.
        # Los ignoramos para evitar colisiones del tipo "Table X is already defined".
        last_segment = m.name.split(".")[-1]
        if not last_segment.isidentifier():
            continue
        importlib.import_module(m.name)

    # Crear todas las tablas
    Base.metadata.create_all(bind=engine)

    # Listar tablas creadas / registradas
    tables = sorted(Base.metadata.tables.keys())

    print("✅ Tablas creadas / registradas en SQLAlchemy:")
    for table in tables:
        print(f"   - {table}")

    print(f"\n📊 Total tablas: {len(tables)}")


if __name__ == "__main__":
    main()
