from datetime import datetime

from app.core.database import get_db
from app.core.variables import DATA
from app.models.case import Case
from app.models.document import Document

# =========================================================
# SEED DE DATOS DE PRUEBA (CONTROLADO Y VÁLIDO)
# =========================================================


def main():
    db = next(get_db())

    print("--------------------------------------------------")
    print("[SEED] Creando datos de prueba Phoenix")

    # --------------------------------------------------
    # 1️⃣ Crear caso
    # --------------------------------------------------
    case = Case(
        name="Caso de prueba Phoenix",
        client_ref="TEST_CLIENT",
        status="active",
    )
    db.add(case)
    db.flush()  # para obtener case_id

    print(f"[OK] Caso creado: {case.case_id}")

    # --------------------------------------------------
    # 2️⃣ Preparar archivo de prueba en disco
    # --------------------------------------------------
    test_dir = DATA / "test_client" / "cases" / case.case_id / "documents"
    test_dir.mkdir(parents=True, exist_ok=True)

    test_file_path = test_dir / "doc1.txt"
    test_file_path.write_text(
        "Este contrato presenta posibles riesgos legales relacionados "
        "con la responsabilidad del administrador y la insolvencia."
    )

    print(f"[OK] Archivo de prueba creado: {test_file_path}")

    # --------------------------------------------------
    # 3️⃣ Crear documento (CUMPLE TODOS LOS CONSTRAINTS)
    # --------------------------------------------------
    document = Document(
        case_id=case.case_id,
        filename="doc1.txt",
        doc_type="contrato",
        source="seed",
        date_start=datetime(2023, 1, 1),
        date_end=datetime(2023, 12, 31),
        reliability="original",
        file_format="txt",
        storage_path=str(test_file_path),
    )

    db.add(document)
    db.commit()

    print(f"[OK] Documento creado: {document.document_id}")

    print("--------------------------------------------------")
    print("[SEED] Seed completado correctamente")
    print(f"[SEED] case_id = {case.case_id}")
    print("--------------------------------------------------")


if __name__ == "__main__":
    main()
