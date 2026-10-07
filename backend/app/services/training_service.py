"""训练用例服务：承载事务边界与业务编排，路由只做鉴权与协议映射。"""
from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import TrainingMessage, TrainingReport, TrainingSession, User, utcnow
from app.services.knowledge import find_relevant_knowledge
from app.services.llm import LLMClient, extract_speaker
from app.services.report_details import soft_delete_training_session, write_report_details
from app.services.voice import SPEAKER_DEFAULT, VoiceClient, get_speaker_voice, get_tts_style, normalize_speaker

logger = logging.getLogger(__name__)


class TrainingService:
    def __init__(self, llm: LLMClient | None = None, voice: VoiceClient | None = None):
        self.llm = llm or LLMClient()
        self.voice = voice or VoiceClient()

    # ---------- 权限 ----------
    @staticmethod
    def can_read(user: User, session: TrainingSession) -> bool:
        return user.role == "admin" or session.owner_id == user.id

    @staticmethod
    def can_write(user: User, session: TrainingSession) -> bool:
        return session.owner_id == user.id

    @staticmethod
    def split_speaker(text: str) -> tuple[str, str]:
        try:
            speaker, clean = extract_speaker(text or "")
        except Exception:
            from app.services.voice import extract_speaker_tag

            return extract_speaker_tag(text or "")
        speaker = normalize_speaker(speaker)
        clean = (clean or "").strip() or (text or "").strip()
        return speaker, clean

    # ---------- 用例 ----------
    async def start_session(self, db: Session, user: User, payload: dict[str, Any]) -> TrainingSession:
        session = TrainingSession(owner_id=user.id, **payload)
        db.add(session)
        db.commit()
        db.refresh(session)
        await self._append_opening_customer_message(db, session)
        return session

    async def retry_session(self, db: Session, user: User, source: TrainingSession) -> TrainingSession:
        retry_focus = ""
        if source.report:
            retry_focus = f"\n\n复训重点：{source.report.summary}"
        session = TrainingSession(
            owner_id=user.id,
            training_type=source.training_type,
            stage=source.stage,
            goal=source.goal,
            customer_name=source.customer_name,
            customer_type=source.customer_type,
            customer_difficulty=source.customer_difficulty,
            customer_personality=source.customer_personality,
            customer_concern=source.customer_concern,
            template_id=source.template_id,
            setup_context=source.setup_context or {},
            background=f"{source.background}{retry_focus}",
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        await self._append_opening_customer_message(db, session)
        return session

    async def _append_opening_customer_message(self, db: Session, session: TrainingSession) -> TrainingMessage:
        knowledge = find_relevant_knowledge(db, session)
        first_reply = await self.llm.customer_reply(session, [], knowledge)
        speaker, clean = self.split_speaker(first_reply)
        message = TrainingMessage(
            session_id=session.id, role="customer", content=clean, speaker=speaker
        )
        db.add(message)
        db.commit()
        db.refresh(session)
        return message

    def append_sales_message(
        self, db: Session, session: TrainingSession, content: str, speaker: str | None
    ) -> TrainingMessage:
        sales_speaker = normalize_speaker(speaker) if speaker else SPEAKER_DEFAULT
        message = TrainingMessage(
            session_id=session.id, role="sales", content=content, speaker=sales_speaker
        )
        db.add(message)
        db.commit()
        db.refresh(session)
        return message

    async def send_message(
        self, db: Session, session: TrainingSession, content: str, speaker: str | None
    ) -> TrainingMessage:
        self.append_sales_message(db, session, content, speaker)
        knowledge = find_relevant_knowledge(db, session)
        reply = await self.llm.customer_reply(session, session.messages, knowledge)
        speaker_tag, clean = self.split_speaker(reply)
        message = TrainingMessage(
            session_id=session.id, role="customer", content=clean, speaker=speaker_tag
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        return message

    async def suggest_reply(self, db: Session, session: TrainingSession) -> str:
        knowledge = find_relevant_knowledge(db, session)
        return await self.llm.suggested_reply(session, session.messages, knowledge)

    async def live_tip(self, db: Session, session: TrainingSession, context: str) -> list[str]:
        knowledge = find_relevant_knowledge(db, session)
        try:
            tips = await self.llm.live_tip(session, session.messages, knowledge, context=context)
        except Exception as exc:
            logger.warning("live-tip 生成失败 context=%s：%s", context, exc)
            tips = []
        if not isinstance(tips, list):
            tips = []
        tips = [str(t).strip() for t in tips if str(t).strip()][:2]
        return tips or ["补问水质与水温", "把下一步收成具体人/时间"][:2]

    def snapshot_session(self, session: TrainingSession) -> dict[str, Any]:
        return {
            "id": session.id,
            "owner_id": session.owner_id,
            "training_type": session.training_type,
            "stage": session.stage,
            "goal": session.goal,
            "customer_name": session.customer_name,
            "customer_type": session.customer_type,
            "customer_difficulty": getattr(session, "customer_difficulty", "") or "标准",
            "customer_personality": getattr(session, "customer_personality", "") or "谨慎型",
            "customer_concern": getattr(session, "customer_concern", "") or "供应稳定",
            "template_id": session.template_id or "",
            "background": session.background,
        }

    @staticmethod
    def snapshot_messages(session: TrainingSession) -> list[dict[str, Any]]:
        return [
            {"role": m.role, "content": m.content, "speaker": getattr(m, "speaker", SPEAKER_DEFAULT)}
            for m in session.messages
        ]

    async def stream_reply_events(
        self,
        session_id: int,
        session_snapshot: dict[str, Any],
        messages_snapshot: list[dict[str, Any]],
        knowledge: list,
    ) -> AsyncGenerator[str, None]:
        """SSE 事件流：token → done(入库) → audio → complete。"""
        import base64 as _b64
        import json

        gen_db = SessionLocal()
        try:
            collected_text = []
            async for chunk in self.llm.customer_reply_stream(
                session_snapshot, messages_snapshot, knowledge
            ):
                collected_text.append(chunk)
                yield f"event: token\ndata: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"

            full_text = "".join(collected_text).strip()
            speaker, clean_text = self.split_speaker(full_text)
            message = TrainingMessage(
                session_id=session_id,
                role="customer",
                content=clean_text,
                speaker=speaker,
            )
            gen_db.add(message)
            gen_db.commit()
            gen_db.refresh(message)
            yield (
                "event: done\n"
                f"data: {json.dumps({'id': message.id, 'content': clean_text, 'role': 'customer', 'speaker': speaker}, ensure_ascii=False)}\n\n"
            )

            if self.voice.configured and clean_text:
                style = get_tts_style(
                    template_id=session_snapshot["template_id"],
                    difficulty=session_snapshot["customer_difficulty"],
                    personality=session_snapshot["customer_personality"],
                    speaker=speaker,
                )
                voice_name = get_speaker_voice(speaker)
                try:
                    async for pcm_chunk in self.voice.synthesize_stream(
                        clean_text, style, voice=voice_name
                    ):
                        yield (
                            "event: audio\n"
                            f"data: {json.dumps({'data': _b64.b64encode(pcm_chunk).decode(), 'speaker': speaker}, ensure_ascii=False)}\n\n"
                        )
                except Exception as exc:  # TTS 失败不阻断主流程
                    from app.services.voice import VoiceError, VoiceTimeoutError

                    if isinstance(exc, (VoiceTimeoutError, VoiceError)):
                        logger.warning("TTS 流式合成失败：%s", exc)
                        yield f"event: tts_error\ndata: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
                    else:
                        raise

            yield "event: complete\ndata: {}\n\n"
        except Exception as exc:
            logger.exception("流式端点异常")
            yield f"event: error\ndata: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
            yield "event: complete\ndata: {}\n\n"
        finally:
            gen_db.close()

    async def finish_session(self, db: Session, session: TrainingSession) -> TrainingReport:
        if session.report:
            return session.report
        knowledge = find_relevant_knowledge(db, session)
        data = await self.llm.score_report(session, session.messages, knowledge)
        report = TrainingReport(
            session_id=session.id,
            overall_score=int(data.get("overall_score", 70)),
            summary=data.get("summary", ""),
            scores=data.get("scores", []),
            good_lines=data.get("good_lines", []),
            risk_lines=data.get("risk_lines", []),
            alternatives=data.get("alternatives", []),
            checklist=data.get("checklist", []),
            citations=data.get("citations", []),
        )
        session.status = "completed"
        session.completed_at = utcnow()
        db.add(report)
        db.commit()
        db.refresh(report)
        write_report_details(db, report)
        db.commit()
        db.refresh(report)
        return report

    def clear_sessions(self, db: Session, user: User) -> int:
        sessions = (
            db.query(TrainingSession)
            .filter(TrainingSession.owner_id == user.id, TrainingSession.status != "deleted")
            .all()
        )
        count = len(sessions)
        for session in sessions:
            soft_delete_training_session(db, session)
        db.commit()
        return count
