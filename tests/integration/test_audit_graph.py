from app.graphs.audit_graph import build_audit_graph


def main():
    graph = build_audit_graph()

    initial_state = {
        "case_id": "demo-case-id",
        "documents_processed": [],
        "events_detected": [],
        "risks": [],
        "notes": None,
    }

    result = graph.invoke(initial_state)

    print("🧠 Auditor ejecutado correctamente")
    print(result)


if __name__ == "__main__":
    main()
