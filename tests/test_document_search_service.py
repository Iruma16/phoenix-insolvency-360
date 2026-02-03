from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.case import Case
from app.models.document import Document
from app.models.document_chunk import DocumentChunk, generate_deterministic_chunk_id
from app.services.document_search_service import DocumentSearchParams, search_documents


def test_search_documents_devuelve_snippet_y_pagina():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        case = Case(case_id="case_1", name="Caso 1")
        db.add(case)
        db.commit()

        doc = Document(
            document_id="doc_1",
            case_id=case.case_id,
            filename="modelo_303_aeat.pdf",
            sha256_hash="0" * 64,
            file_size_bytes=123,
            mime_type="application/pdf",
            uploaded_at=datetime.utcnow(),
            doc_type="AEAT",
            doc_type_confidence=1.0,
            doc_type_source="mapped",
            source="upload",
            date_start=datetime.utcnow(),
            date_end=datetime.utcnow(),
            reliability="original",
            file_format="pdf",
            storage_path="/tmp/doc_1.pdf",
            created_at=datetime.utcnow(),
            raw_text="Modelo 303 IVA. Agencia Tributaria.",
            parsing_status="completed",
        )
        db.add(doc)
        db.commit()

        chunk_id = generate_deterministic_chunk_id(
            case_id=case.case_id,
            doc_id=doc.document_id,
            chunk_index=0,
            start_char=0,
            end_char=50,
        )
        chunk = DocumentChunk(
            chunk_id=chunk_id,
            document_id=doc.document_id,
            case_id=case.case_id,
            chunk_index=0,
            content="Agencia Tributaria - Modelo 303 IVA (ejemplo).",
            start_char=0,
            end_char=50,
            extraction_method="PDF_TEXT",
            page_start=2,
            page_end=2,
        )
        db.add(chunk)
        db.commit()

        resp = search_documents(
            db=db,
            case_id=case.case_id,
            params=DocumentSearchParams(q="Agencia", page=1, page_size=10),
        )

        assert resp.total == 1
        assert len(resp.items) == 1
        item = resp.items[0]
        assert item.document_id == "doc_1"
        assert item.page == 2
        assert item.snippet and "Agencia" in item.snippet
    finally:
        db.close()
