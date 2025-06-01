from fastapi import APIRouter
router = APIRouter()

@router.post("/")
async def criar_aluno():
    return {"msg": "aluno criado"}