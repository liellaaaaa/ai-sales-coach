from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.schemas import LLMConfigOut, LLMConfigUpdateIn, LLMConnectionTestOut
from app.services.auth import require_roles
from app.services.llm import MiniMaxClient
from app.services.llm_config import config_to_public, get_effective_llm_config, save_llm_config


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/llm", response_model=LLMConfigOut)
def get_llm_config(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    return config_to_public(get_effective_llm_config(db))


@router.patch("/llm", response_model=LLMConfigOut)
def update_llm_config(
    payload: LLMConfigUpdateIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    try:
        config = save_llm_config(
            db,
            api_key=payload.api_key,
            clear_api_key=payload.clear_api_key,
            base_url=payload.base_url,
            model_name=payload.model_name,
            model_id=payload.model_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return config_to_public(config)


@router.post("/llm/test", response_model=LLMConnectionTestOut)
async def test_llm_connection(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    config = get_effective_llm_config(db)
    return await MiniMaxClient().test_connection(config)
