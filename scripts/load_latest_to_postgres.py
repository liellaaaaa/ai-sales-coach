"""把清洗后的服务器训练数据载入当前配置的 PostgreSQL（本地 Docker 与服务器同一套口径）。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.migrations import ensure_runtime_schema  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402

SQL_LATEST = Path(r"C:/Users/windows/Desktop/sales_coach_latest.sql")


def parse_blocks(text: str) -> dict[str, list[list[str | None]]]:
    out: dict[str, list[list[str | None]]] = {}
    for m in re.finditer(r"COPY public\.(\w+) \([^)]+\) FROM stdin;\n([\s\S]*?)\n\\\.\n", text):
        rows = []
        for line in m.group(2).split("\n"):
            if not line.strip():
                continue
            cols = [None if c == "\\N" else c for c in line.split("\t")]
            rows.append(cols)
        out[m.group(1)] = rows
    return out


def main() -> None:
    text = SQL_LATEST.read_text(encoding="utf-8")
    blocks = parse_blocks(text)
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()
    db = SessionLocal()
    try:
        for table in (
            "report_citations",
            "report_scores",
            "report_todos",
            "training_reports",
            "training_messages",
            "training_sessions",
        ):
            db.execute(__import__("sqlalchemy").text(f"DELETE FROM {table}"))
        db.commit()

        for r in blocks.get("training_sessions", []):
            setup = r[11] or "{}"
            if isinstance(setup, str):
                try:
                    setup = json.dumps(json.loads(setup), ensure_ascii=False)
                except json.JSONDecodeError:
                    setup = "{}"
            db.execute(
                __import__("sqlalchemy").text(
                    "INSERT INTO training_sessions (id, owner_id, training_type, stage, goal, customer_name, customer_type,"
                    " customer_difficulty, customer_personality, customer_concern, template_id, setup_context, background,"
                    " status, created_at, completed_at, updated_at, deleted_at)"
                    " VALUES (:id,:owner_id,:training_type,:stage,:goal,:customer_name,:customer_type,"
                    ":customer_difficulty,:customer_personality,:customer_concern,:template_id,CAST(:setup_context AS json),:background,"
                    ":status,:created_at,:completed_at,:updated_at,:deleted_at)"
                ),
                {
                    "id": int(r[0]),
                    "owner_id": int(r[1]),
                    "training_type": r[2],
                    "stage": r[3],
                    "goal": r[4],
                    "customer_name": r[5],
                    "customer_type": r[6],
                    "customer_difficulty": r[7],
                    "customer_personality": r[8],
                    "customer_concern": r[9],
                    "template_id": r[10] or "",
                    "setup_context": setup,
                    "background": r[12] or "",
                    "status": r[13],
                    "created_at": r[14],
                    "completed_at": r[15],
                    "updated_at": r[16],
                    "deleted_at": r[17],
                },
            )

        for r in blocks.get("training_messages", []):
            db.execute(
                __import__("sqlalchemy").text(
                    "INSERT INTO training_messages (id, session_id, role, content, created_at, speaker)"
                    " VALUES (:id,:session_id,:role,:content,:created_at,:speaker)"
                ),
                {
                    "id": int(r[0]),
                    "session_id": int(r[1]),
                    "role": r[2],
                    "content": r[3] or "",
                    "created_at": r[4],
                    "speaker": r[5] or "buyer",
                },
            )

        for r in blocks.get("training_reports", []):
            db.execute(
                __import__("sqlalchemy").text(
                    "INSERT INTO training_reports (id, session_id, overall_score, summary, scores, good_lines, risk_lines, alternatives, checklist, citations, created_at)"
                    " VALUES (:id,:session_id,:overall_score,:summary,CAST(:scores AS json),CAST(:good_lines AS json),CAST(:risk_lines AS json),CAST(:alternatives AS json),CAST(:checklist AS json),CAST(:citations AS json),:created_at)"
                ),
                {
                    "id": int(r[0]),
                    "session_id": int(r[1]),
                    "overall_score": int(r[2] or 0),
                    "summary": r[3] or "",
                    "scores": r[4] or "[]",
                    "good_lines": r[5] or "[]",
                    "risk_lines": r[6] or "[]",
                    "alternatives": r[7] or "[]",
                    "checklist": r[8] or "[]",
                    "citations": r[9] or "[]",
                    "created_at": r[10],
                },
            )

        for r in blocks.get("report_scores", []):
            db.execute(
                __import__("sqlalchemy").text(
                    "INSERT INTO report_scores (id, report_id, name, value, reason, sort_order) VALUES (:id,:report_id,:name,:value,:reason,:sort_order)"
                ),
                {
                    "id": int(r[0]),
                    "report_id": int(r[1]),
                    "name": r[2],
                    "value": int(r[3] or 0),
                    "reason": r[4] or "",
                    "sort_order": int(r[5] or 0),
                },
            )

        for r in blocks.get("report_todos", []):
            db.execute(
                __import__("sqlalchemy").text(
                    "INSERT INTO report_todos (id, report_id, title, detail, due, sort_order) VALUES (:id,:report_id,:title,:detail,:due,:sort_order)"
                ),
                {
                    "id": int(r[0]),
                    "report_id": int(r[1]),
                    "title": r[2] or "",
                    "detail": r[3] or "",
                    "due": r[4] or "",
                    "sort_order": int(r[5] or 0),
                },
            )

        for r in blocks.get("report_citations", []):
            db.execute(
                __import__("sqlalchemy").text(
                    "INSERT INTO report_citations (id, report_id, source, reason, sort_order) VALUES (:id,:report_id,:source,:reason,:sort_order)"
                ),
                {
                    "id": int(r[0]),
                    "report_id": int(r[1]),
                    "source": r[2] or "",
                    "reason": r[3] or "",
                    "sort_order": int(r[4] or 0),
                },
            )

        db.commit()
        print("database:", engine.url)
        print("sessions", db.execute(__import__("sqlalchemy").text("SELECT count(*) FROM training_sessions")).scalar())
        print("messages", db.execute(__import__("sqlalchemy").text("SELECT count(*) FROM training_messages")).scalar())
        print("reports", db.execute(__import__("sqlalchemy").text("SELECT count(*) FROM training_reports")).scalar())
        for row in db.execute(
            __import__("sqlalchemy").text(
                "SELECT id, customer_name, stage, goal, customer_type, customer_concern, template_id FROM training_sessions ORDER BY id"
            )
        ):
            print(
                f"id={row[0]:>2} {row[1]} | {row[2]}/{row[3]} | {row[4]} | {row[5]} | {row[6] or '-'}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
