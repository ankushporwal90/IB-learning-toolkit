from uuid import uuid4

from src.storage import session_store


def test_session_store_creates_session_and_events(monkeypatch) -> None:
    db_path = session_store.PROJECT_ROOT / "data" / "sqlite" / f"test_memory_{uuid4().hex}.db"
    monkeypatch.setattr(session_store, "get_database_path", lambda: db_path)

    session_store.initialize_session_store()
    session_id = session_store.create_analysis_session("AAPL Review", ticker="aapl")
    event_id = session_store.save_analysis_event(
        session_id=session_id,
        event_type="rag_question_answer",
        document_name="AAPL 10-K",
        question="What was revenue?",
        content="Revenue was $416.2B.",
    )

    sessions = session_store.list_analysis_sessions()
    events = session_store.list_analysis_events(session_id)

    assert db_path.exists()
    assert session_id == sessions[0].id
    assert event_id == events[0].id
    assert sessions[0].ticker == "AAPL"
    assert events[0].question == "What was revenue?"


def test_export_session_markdown_includes_events(monkeypatch) -> None:
    db_path = session_store.PROJECT_ROOT / "data" / "sqlite" / f"test_memory_{uuid4().hex}.db"
    monkeypatch.setattr(session_store, "get_database_path", lambda: db_path)

    session_store.initialize_session_store()
    session_id = session_store.create_analysis_session("MSFT Review", ticker="MSFT")
    session_store.save_analysis_event(
        session_id=session_id,
        event_type="phase_1_summary",
        document_name="MSFT 10-K",
        content="Business overview text.",
    )

    markdown = session_store.export_session_markdown(session_id)

    assert "# MSFT Review" in markdown
    assert "MSFT 10-K" in markdown
    assert "Business overview text." in markdown
