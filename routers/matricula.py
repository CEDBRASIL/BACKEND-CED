from fastapi import APIRouter
router = APIRouter()

@router.post("/")
async def matricular():
    return {"msg": "matrícula realizada"}