from pathlib import Path
from dotenv import load_dotenv
from app.core.database import Base, get_engine
from app.models.case import Case  # noqa: F401, E402
from app.models.document import Document  # noqa: F401, E402
from app.models.document_chunk import DocumentChunk  # noqa: F401, E402
from app.models.event import Event  # noqa: F401, E402
from app.models.risk import Risk  # noqa: F401, E402
from app.models.fact import Fact  # noqa: F401, E402
from app.models.fact_evidence import FactEvidence  # noqa: F401, E402

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")
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
