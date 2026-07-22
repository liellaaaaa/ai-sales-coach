from app.db.session import Base, SessionLocal, engine
from app.models import KnowledgeItem, Team, User
from app.services.auth import hash_password


def get_or_create_team(db, name: str) -> Team:
    team = db.query(Team).filter(Team.name == name).first()
    if team:
        return team
    team = Team(name=name)
    db.add(team)
    db.flush()
    return team


def get_or_create_user(db, username: str, name: str, role: str, team_id=None, manager_id=None):
    user = db.query(User).filter(User.username == username).first()
    if user:
        return user
    user = User(
        username=username,
        name=name,
        role=role,
        team_id=team_id,
        manager_id=manager_id,
        password_hash=hash_password("123456"),
    )
    db.add(user)
    db.flush()
    return user


def seed_knowledge(db):
    if db.query(KnowledgeItem).count():
        return
    items = [
        KnowledgeItem(
            title="价格异议处理",
            source_type="销售 SOP",
            source_name="商务谈判 SOP",
            stage="商务谈判",
            scenario="价格异议",
            customer_type="通用",
            recommended="先确认客户价格顾虑，再用总成本、稳定性和返修风险解释报价。",
            banned="不要直接说我们的质量更好，也不要立即降价。",
            content="价格异议处理中，先确认客户比较对象，再解释稳定性、返修、交期和总成本。",
        ),
        KnowledgeItem(
            title="商机停滞推进",
            source_type="推进规范",
            source_name="商机推进规范",
            stage="确认商机",
            scenario="商机停滞",
            customer_type="通用",
            recommended="把下一步收敛到时间、关键人、资料或测试条件其中一个动作。",
            banned="不要只说后续保持沟通。",
            content="客户收资料后停滞时，应确认关键人、下一次沟通时间和具体推进条件。",
        ),
        KnowledgeItem(
            title="技术交涉说明",
            source_type="产品资料",
            source_name="方案论证 SOP",
            stage="方案论证",
            scenario="技术交涉",
            customer_type="技术型客户",
            recommended="用小样测试、色牢度数据和工艺条件说明方案。",
            banned="不要在没有数据时承诺绝对稳定。",
            content="技术型客户应优先给测试条件、样品验证和数据依据。",
        ),
        KnowledgeItem(
            title="回款交涉推进",
            source_type="销售 SOP",
            source_name="回款交涉 SOP",
            stage="回款",
            scenario="回款交涉",
            customer_type="通用",
            recommended="先确认付款节点和内部流程，再把回款安排拆成责任人、金额和时间。",
            banned="不要只催客户尽快付款，也不要把回款压力直接转嫁给客户。",
            content="回款交涉应明确付款流程、审批节点、责任人和可接受的分期或对账安排。",
        ),
        KnowledgeItem(
            title="老客户订单减少维护",
            source_type="销售 SOP",
            source_name="老客户维护 SOP",
            stage="回款",
            scenario="老客维护",
            customer_type="老客户",
            recommended="先确认订单减少原因，再讨论稳定供应、服务响应和复购安排。",
            banned="不要一上来追问为什么不下单。",
            content="老客户订单减少时，应先复盘近期服务体验，再确认竞品、价格、库存和生产计划。",
        ),
    ]
    db.add_all(items)


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        team = get_or_create_team(db, "华南销售一组")
        get_or_create_user(db, "sales", "陈宇", "sales", team.id)
        get_or_create_user(db, "admin", "系统管理员", "admin", team.id)
        seed_knowledge(db)
        db.commit()
    finally:
        db.close()
    print("seed ok: sales/admin password=123456")


if __name__ == "__main__":
    main()
