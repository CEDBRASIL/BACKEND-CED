from fastapi import FastAPI
from cursos import router as cursos_router
from matricular import router as matricular_router

app = FastAPI()
router = APIRouter()


# Incluindo os sistemas no app
app.include_router(cursos_router, prefix="/cursos")
app.include_router(matricular_router, prefix="/matricular")

@app.get("/")
async def root():
    return {"status": "online"}
