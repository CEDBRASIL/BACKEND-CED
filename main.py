from fastapi import FastAPI
from cursos import router as cursos_router
from matricular import router as matricular_router

app = FastAPI()

# Incluindo os sistemas no app
app.include_router(cursos_router, prefix="/cursos")
app.include_router(matricular_router, prefix="/matricular")
app.include_router(secure_router, prefix="/secure", tags=["cursos"])

@app.get("/")
async def root():
    return {"status": "online"}


