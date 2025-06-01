from fastapi import APIRouter
router = APIRouter()

@router.post("/enviar")
async def enviar_mensagem():
    return {"msg": "mensagem enviada"}