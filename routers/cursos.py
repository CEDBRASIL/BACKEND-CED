from fastapi import APIRouter
router = APIRouter()

@router.get("/")
async def listar_cursos():
    return ["Administração", "Informática", "Inglês"]