"""报告子表 / 标签同步单测。"""
from app.models import DocumentTag, KnowledgeDocument, ReportCitation, ReportScore, ReportTodo, TrainingReport, TrainingSession, User
from app.services.report_details import backfill_normalized_tables, soft_delete_document, sync_document_tags, write_report_details


def _user(db):
    return db.query(User).filter(User.username == "sales").one()


def test_sync_document_tags(db):
    user = _user(db)
    doc = KnowledgeDocument(
        title="标签测试文档",
        source_type="SOP 与话术",
        source_name="标签测试文档",
        tags="",
        purpose="",
        stage="通用",
        scenario="通用",
        customer_type="通用",
        recommended="r",
        banned="b",
        parse_status="parsed",
        status="active",
    )
    db.add(doc)
    db.commit()
    sync_document_tags(db, doc, "推荐话术, 价格异议，推荐话术")
    db.commit()
    tags = {row.tag for row in db.query(DocumentTag).filter(DocumentTag.document_id == doc.id).all()}
    assert tags == {"推荐话术", "价格异议"}
    assert doc.tags == "推荐话术,价格异议"


def test_write_report_details(db):
    user = _user(db)
    session = TrainingSession(
        owner_id=user.id,
        training_type="客户情景陪练",
        stage="方案论证",
        goal="技术交涉",
        customer_name="测试客户",
        customer_type="技术型客户",
        background="bg",
        status="active",
    )
    db.add(session)
    db.commit()
    report = TrainingReport(
        session_id=session.id,
        overall_score=80,
        summary="ok",
        scores=[{"name": "工艺探询", "value": 4, "reason": "问清了"}],
        good_lines=["g"],
        risk_lines=["r"],
        alternatives=["a"],
        checklist=[{"title": "补问水质", "detail": "问硬度", "due": "1 天内"}],
        citations=[{"source": "SOP", "reason": "依据"}],
    )
    db.add(report)
    db.commit()
    write_report_details(db, report)
    db.commit()
    assert db.query(ReportScore).filter(ReportScore.report_id == report.id).count() == 1
    assert db.query(ReportTodo).filter(ReportTodo.report_id == report.id).count() == 1
    assert db.query(ReportCitation).filter(ReportCitation.report_id == report.id).count() == 1

    # 幂等：再写一次不翻倍
    write_report_details(db, report)
    db.commit()
    assert db.query(ReportScore).filter(ReportScore.report_id == report.id).count() == 1


def test_soft_delete_document(db):
    doc = KnowledgeDocument(
        title="软删测试",
        source_type="产品说明书",
        source_name="软删测试",
        tags="t",
        purpose="",
        stage="通用",
        scenario="通用",
        customer_type="通用",
        recommended="r",
        banned="b",
        parse_status="parsed",
        status="active",
    )
    db.add(doc)
    db.commit()
    soft_delete_document(db, doc)
    db.commit()
    assert doc.status == "deleted"
    assert doc.deleted_at is not None


def test_backfill_idempotent(db):
    stats1 = backfill_normalized_tables(db)
    stats2 = backfill_normalized_tables(db)
    assert stats2["documents"] == 0
    assert stats2["reports"] == 0
    assert isinstance(stats1, dict)
