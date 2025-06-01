from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from routers.auth import router as auth_router
from routers.cursos import router as cursos_router
from routers.alunos import router as alunos_router
from routers.matricula import router as matricula_router
from routers.webhook import router as webhook_router
from routers.whatsapp import router as whatsapp_router

app = FastAPI(title="CED BRASIL API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth", tags=["Autenticação"])
app.include_router(cursos_router, prefix="/cursos", tags=["Cursos"])
app.include_router(alunos_router, prefix="/alunos", tags=["Alunos"])
app.include_router(matricula_router, prefix="/matricula", tags=["Matrícula"])
app.include_router(webhook_router, prefix="/webhook", tags=["Webhook MP"])
app.include_router(whatsapp_router, prefix="/whatsapp", tags=["WhatsApp"])

@app.get("/", tags=["Status"])
async def root():
    return {"status": "online", "projeto": "CED BRASIL"}
