
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import structlog
from cursos import router as cursos_router
from matricular import router as matricular_router
from secure import router as secure_router
from checkout_api import router as checkout_router
from matricularmercadopago import router as mp_router
from mp import mp_router


log = structlog.get_logger()

app = FastAPI(title="CED API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cursos_router, prefix="/cursos", tags=["Cursos"])
app.include_router(matricular_router, prefix="/matricular", tags=["Matrícula"])
app.include_router(secure_router, prefix="/secure", tags=["Token"])
app.include_router(checkout_router, tags=["Checkout"])
app.include_router(mp_router, prefix="/checkout")


@app.get("/")
async def root():
    return {"status": "online"}

@app.middleware("http")
async def log_requests(request: Request, call_next):
    log.info("request", method=request.method, path=request.url.path)
    response = await call_next(request)
    log.info("response", status=response.status_code)
    return response
