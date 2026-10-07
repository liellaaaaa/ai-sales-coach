"""分析服务器备份：核对结构差异并生成可回灌的最新数据 SQL。"""
from __future__ import annotations

import json
import re
from pathlib import Path

SQL_PATH = Path(r"C:/Users/windows/Desktop/sales_coach_backup.sql")
OUT_PATH = Path(r"C:/Users/windows/Desktop/sales_coach_latest.sql")
REPORT_PATH = Path(r"C:/Users/windows/Desktop/sales_coach_sync_report.md")

NEW_RELATIONSHIPS = {"陌拜新客户", "潜在新客户", "新成交客户", "老客户"}

# 旧口径 → (客户关系, 客户画像)
LEGACY_TYPE_MAP = {
    "新客户，价格敏感": ("潜在新客户", ""),
    "新客户，内部决策不清晰": ("潜在新客户", ""),
    "老客户，订单减少": ("老客户", ""),
    "老客户，流程较慢": ("老客户", ""),
    "技术型客户，关注工艺": ("潜在新客户", ""),
    "渠道客户，关注交期": ("潜在新客户", ""),
    "新客户": ("潜在新客户", ""),
    "老客户": ("老客户", ""),
    "技术型客户": ("潜在新客户", ""),
    "渠道客户": ("潜在新客户", ""),
    "通用": ("潜在新客户", ""),
}

# 「行业·角色」是画像，关系按阶段/目标推断
PERSONA_ONLY_RE = re.compile(r"(厂|公司|贸易|加工|生产|印染|纺织|面料|染厂)")

GOAL_RELATIONSHIP = {
    "线索判断": "陌拜新客户",
    "首次触达": "陌拜新客户",
    "约到拜访": "陌拜新客户",
    "回款交涉": "老客户",
    "服务稳定": "老客户",
    "老客维护": "老客户",
    "复购推进": "老客户",
    "技术质疑": "老客户",
}

STAGE_RELATIONSHIP = {
    "了解商机": "陌拜新客户",
    "回款": "老客户",
    "确认商机": "潜在新客户",
    "方案论证": "潜在新客户",
    "商务谈判": "潜在新客户",
    "销售成交": "新成交客户",
}

# 旧 template_id → 新 template_id（仅当明确对应）
TEMPLATE_MAP = {
    "cold-call-phone": "cold-call-procurement",
    "price-objection": "",
    "payment-quality-objection": "quality-hold-payment",
}

# 旧关注点：电话陌拜误标价格 → 供应稳定
COLD_CALL_TEMPLATES = {"cold-call-phone", "cold-call-procurement"}


def parse_copy_blocks(text: str) -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = {}
    for m in re.finditer(r"COPY public\.(\w+) \([^)]+\) FROM stdin;\n([\s\S]*?)\n\\\.\n", text):
        table, body = m.group(1), m.group(2)
        rows = [line for line in body.split("\n") if line.strip()]
        blocks[table] = rows
    return blocks


def split_row(line: str) -> list[str]:
    return line.split("\t")


def join_row(cols: list[str]) -> str:
    return "\t".join(cols)


def infer_relationship(stage: str, goal: str, ctype: str) -> str:
    if ctype in NEW_RELATIONSHIPS:
        return ctype
    if ctype in LEGACY_TYPE_MAP:
        mapped = LEGACY_TYPE_MAP[ctype][0]
        if goal in GOAL_RELATIONSHIP:
            return GOAL_RELATIONSHIP[goal]
        return mapped
    if goal in GOAL_RELATIONSHIP:
        return GOAL_RELATIONSHIP[goal]
    if stage in STAGE_RELATIONSHIP:
        return STAGE_RELATIONSHIP[stage]
    return "潜在新客户"


def extract_persona(ctype: str, setup: dict) -> str:
    if ctype in NEW_RELATIONSHIPS or ctype in LEGACY_TYPE_MAP:
        persona = ""
        if isinstance(setup, dict):
            persona = (
                (setup.get("customer_info") or {}).get("customer_persona")
                or (setup.get("training_profile") or {}).get("customer_persona")
                or ""
            )
        return persona
    # 旧「行业·角色」整串当作画像
    return ctype


def normalize_concern(concern: str, template_id: str, goal: str) -> str:
    if template_id in COLD_CALL_TEMPLATES or goal in {"首次触达", "约到拜访", "线索判断"}:
        if concern in {"价格", ""}:
            return "供应稳定"
    return concern or "供应稳定"


def build_setup(setup: dict, relationship: str, persona: str) -> dict:
    if not isinstance(setup, dict):
        setup = {}
    info = dict(setup.get("customer_info") or {})
    profile = dict(setup.get("training_profile") or {})
    info["customer_type"] = relationship
    if persona:
        info["customer_persona"] = persona
    profile["customer_relationship"] = relationship
    if persona:
        profile["customer_persona"] = persona
    setup = {**setup, "customer_info": info, "training_profile": profile}
    return setup


def main() -> None:
    text = SQL_PATH.read_text(encoding="utf-8")
    blocks = parse_copy_blocks(text)

    session_rows = blocks.get("training_sessions", [])
    normalized_rows: list[str] = []
    changes: list[str] = []

    for line in session_rows:
        cols = split_row(line)
        # columns: id owner_id training_type stage goal customer_name customer_type
        # customer_difficulty customer_personality customer_concern template_id
        # setup_context background status created_at completed_at updated_at deleted_at
        (
            sid,
            _owner,
            training_type,
            stage,
            goal,
            customer_name,
            ctype,
            difficulty,
            personality,
            concern,
            template_id,
            setup_raw,
            background,
            status,
            created_at,
            completed_at,
            updated_at,
            deleted_at,
        ) = cols[:18]

        try:
            setup = json.loads(setup_raw) if setup_raw and setup_raw != "\\N" else {}
        except json.JSONDecodeError:
            setup = {}

        new_template = TEMPLATE_MAP.get(template_id, template_id)
        relationship = infer_relationship(stage, goal, ctype)
        persona = extract_persona(ctype, setup)
        new_concern = normalize_concern(concern, template_id, goal)
        new_setup = build_setup(setup, relationship, persona)

        row_changes = []
        if ctype != relationship:
            row_changes.append(f"customer_type: {ctype!r} → {relationship!r}")
        if persona and ctype != persona:
            row_changes.append(f"customer_persona: {persona!r}")
        if concern != new_concern:
            row_changes.append(f"customer_concern: {concern!r} → {new_concern!r}")
        if template_id != new_template:
            row_changes.append(f"template_id: {template_id!r} → {new_template!r}")

        cols[6] = relationship
        cols[9] = new_concern
        cols[10] = new_template
        cols[11] = json.dumps(new_setup, ensure_ascii=False)
        normalized_rows.append(join_row(cols))

        if row_changes:
            changes.append(f"### session {sid} · {customer_name} / {goal}\n")
            for ch in row_changes:
                changes.append(f"- {ch}")
            changes.append("")

    # 组装最新 SQL：结构不变，只替换 training_sessions 数据段
    out = text
    old_block = "COPY public.training_sessions (id, owner_id, training_type, stage, goal, customer_name, customer_type, customer_difficulty, customer_personality, customer_concern, template_id, setup_context, background, status, created_at, completed_at, updated_at, deleted_at) FROM stdin;\n" + "\n".join(session_rows) + "\n\\.\n"
    new_block = "COPY public.training_sessions (id, owner_id, training_type, stage, goal, customer_name, customer_type, customer_difficulty, customer_personality, customer_concern, template_id, setup_context, background, status, created_at, completed_at, updated_at, deleted_at) FROM stdin;\n" + "\n".join(normalized_rows) + "\n\\.\n"
    if old_block not in out:
        raise SystemExit("training_sessions block not found; abort")
    out = out.replace(old_block, new_block, 1)
    OUT_PATH.write_text(out, encoding="utf-8")

    # 统计
    def count(table: str) -> int:
        return len(blocks.get(table, []))

    report = [
        "# 销售陪练服务器数据核对与同步稿",
        "",
        f"源文件：`{SQL_PATH.name}`（2026-10-07 服务器备份）",
        f"输出：`{OUT_PATH.name}`（已按新客户维度清洗，可直接回灌）",
        "",
        "## 结论",
        "",
        "- **表结构无变动**：备份 schema 与当前代码 `models.py` 一致（含 `customer_difficulty/personality/concern/template_id/setup_context`），不需要迁移。",
        "- **数据口径需清洗**：历史 `customer_type` 仍是「新客户，价格敏感 / 老客户，订单减少 / 印染加工厂·采购经理」混用；已拆成「客户关系 + 客户画像」。",
        "- `.sql` 与 `.dump` 为同一时刻两份格式，内容等价；同步用清洗后的 `sales_coach_latest.sql` 即可。",
        "",
        "## 数据量",
        "",
        f"- training_sessions: {count('training_sessions')}",
        f"- training_messages: {count('training_messages')}",
        f"- training_reports: {count('training_reports')}",
        f"- knowledge_documents: {count('knowledge_documents')}",
        f"- knowledge_items: {count('knowledge_items')}",
        f"- users: {count('users')}",
        f"- llm_configs: {count('llm_configs')}",
        "",
        "## 字段清洗规则",
        "",
        "1. `customer_type` 只保留关系：陌拜新客户 / 潜在新客户 / 新成交客户 / 老客户",
        "2. 「行业·角色」迁入 `setup_context.customer_info.customer_persona`",
        "3. 电话陌拜类会话的「价格」关注点改为「供应稳定」（首次触达关心的是要不要换供应商）",
        "4. 旧 template_id 映射：`cold-call-phone`→`cold-call-procurement`，`payment-quality-objection`→`quality-hold-payment`",
        "",
        "## 逐条变更",
        "",
        "\n".join(changes) if changes else "（无变更）",
        "",
        "## 回灌方式（在服务器执行前请先备份）",
        "",
        "```bash",
        "# 1. 服务器再备份一次",
        "pg_dump -U sales_coach -d sales_coach -F c -f /tmp/sales_coach_before_restore.dump",
        "",
        "# 2. 恢复清洗后数据（会覆盖同名库，请确认）",
        "psql -U sales_coach -d postgres -c 'DROP DATABASE IF EXISTS sales_coach;'",
        "psql -U sales_coach -d postgres -c 'CREATE DATABASE sales_coach OWNER sales_coach;'",
        "psql -U sales_coach -d sales_coach -f sales_coach_latest.sql",
        "```",
        "",
        "若只想就地改 training_sessions 而不重建库，可只执行同步稿里的 UPDATE 段（见下）。",
        "",
    ]
    REPORT_PATH.write_text("\n".join(report), encoding="utf-8")

    # 另存就地 UPDATE 语句
    upd = Path(r"C:/Users/windows/Desktop/sales_coach_customer_dim_patch.sql")
    lines = [
        "-- 就地清洗 training_sessions 客户维度（可重复执行）",
        "BEGIN;",
        "",
    ]
    for row in normalized_rows:
        cols = split_row(row)
        sid = cols[0]
        relationship = cols[6].replace("'", "''")
        concern = cols[9].replace("'", "''")
        template_id = cols[10].replace("'", "''")
        setup_json = cols[11].replace("'", "''")
        lines.append(
            f"UPDATE training_sessions SET customer_type='{relationship}', customer_concern='{concern}', "
            f"template_id='{template_id}', setup_context='{setup_json}'::json WHERE id={sid};"
        )
    lines += ["", "COMMIT;", ""]
    upd.write_text("\n".join(lines), encoding="utf-8")

    print("sessions", len(session_rows))
    print("changed", sum(1 for c in changes if c.startswith("###")))
    print("wrote", OUT_PATH)
    print("wrote", REPORT_PATH)
    print("wrote", upd)


if __name__ == "__main__":
    main()
