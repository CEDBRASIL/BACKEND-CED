from fastapi import APIRouter
router = APIRouter()

@router.post("/")
async def receber_webhook():
    return {"msg": "webhook recebido"}