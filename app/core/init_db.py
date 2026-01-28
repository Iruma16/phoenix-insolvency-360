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
