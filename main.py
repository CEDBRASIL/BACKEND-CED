from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
import structlog

from cursos import router as cursos_router
from matricular import router as matricular_router
from secure import router as secure_router
from checkout_api import router as checkout_router

logger = structlog.get_logger()

app = FastAPI(title="CED API", version="1.0.0")

origins = ["https://www.cedbrasilia.com.br"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cursos_router, prefix="/cursos", tags=["Cursos"])
app.include_router(matricular_router, prefix="/matricular", tags=["Matrícula"])
app.include_router(secure_router, prefix="/secure", tags=["Autenticação"])
app.include_router(checkout_router, tags=["Checkout"])

@app.get("/")
async def root():
    return {"status": "online"}

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Recebendo requisição: {request.method} {request.url}")
    if request.url.path == "/webhook/mp":
        logger.info("Webhook Mercado Pago acionado")
    response = await call_next(request)
    logger.info(f"Resposta: {response.status_code}")
    return response
