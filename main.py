from fastapi import FastAPI
from matricular import router as matricular_router
from cursos import router as cursos_router
from checkout import router as checkout_router

app = FastAPI()

# Incluindo todos os Sistemas presentes como rotas (Yuri ki fez :)
app.include_router(matricular_router, prefix="/matricular")
app.include_router(cursos_router, prefix="/cursos")
app.include_router(checkout_router, prefix="/checkout")
