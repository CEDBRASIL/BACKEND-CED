from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field, AnyHttpUrl
from typing import Annotated
import httpx
import os
import structlog

router = APIRouter()
log = structlog.get_logger()

MP_ACCESS_TOKEN = os.getenv("MP_TEST_ACCESS_TOKEN", "TOKEN_TESTE")
MP_BASE_URL = "https://api.mercadopago.com"

VALOR_ASSINATURA = 4990          # R$49,90 (centavos)
URL_SUCCESS = "https://www.cedbrasilia.com.br/obrigado"
URL_FAILURE = "https://www.cedbrasilia.com.br/NAN"
NOTIF_URL = "https://www.cedbrasilia.com.br/webhook/webhook_mp"
MATRICULAR_URL = "https://www.cedbrasilia.com.br/matricular"


NomeConstrained = Annotated[str, Field(min_length=3, strip_whitespace=True)]
WhatsappConstrained = Annotated[str, Field(pattern=r"^\d{10,11}$")]


class CheckoutIn(BaseModel):
    nome: NomeConstrained
    email: EmailStr
    whatsapp: WhatsappConstrained
    cursos: list[str]


class CheckoutOut(BaseModel):
    mp_link: AnyHttpUrl


@router.post("/pay/eeb/checkout", response_model=CheckoutOut)
async def gerar_link(dados: CheckoutIn):
    log.info("Recebendo dados para gerar link de pagamento", dados=dados.dict())
    if not dados.cursos:
        raise HTTPException(400, "Selecione ao menos um curso")

    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    pref = {
        "items": [{
            "title": "Assinatura CED – " + ", ".join(dados.cursos),
            "quantity": 1,
            "unit_price": VALOR_ASSINATURA / 100,
            "currency_id": "BRL",
        }],
        "payer": {
            "name": dados.nome,
            "email": dados.email,
            "phone": {"number": dados.whatsapp},
        },
        "back_urls": {
            "success": URL_SUCCESS,
            "failure": URL_FAILURE,
            "pending": URL_FAILURE,
        },
        "auto_return": "approved",
        "notification_url": NOTIF_URL,
        "metadata": {
            "nome": dados.nome,
            "email": dados.email,
            "whatsapp": dados.whatsapp,
            "cursos": ",".join(dados.cursos),
        },
    }

    async with httpx.AsyncClient(http2=True, timeout=20) as client:
        r = await client.post(f"{MP_BASE_URL}/checkout/preferences", json=pref, headers=headers)
        if r.status_code != 201:
            log.error("MP erro", status=r.status_code, body=r.text)
            raise HTTPException(502, "Falha ao criar preferência de pagamento")
        return {"mp_link": r.json()["init_point"]}


@router.post("/webhook/mp")
async def webhook_mp(evento: dict):
    if evento.get("type") != "payment":
        return {"msg": "evento ignorado"}

    payment_id = evento["data"]["id"]
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}

    async with httpx.AsyncClient(http2=True) as client:
        resp = await client.get(f"{MP_BASE_URL}/v1/payments/{payment_id}", headers=headers)
        if resp.status_code != 200:
            log.error("Pagamento não encontrado", id=payment_id)
            raise HTTPException(400, "Pagamento não encontrado")
        pay = resp.json()

    if pay["status"] != "approved":
        return {"msg": "Pagamento não aprovado"}

    meta = pay.get("metadata", {})
    payload = {
        "nome": meta.get("nome"),
        "email": meta.get("email"),
        "whatsapp": meta.get("whatsapp"),
        "cursos": [c.strip() for c in meta.get("cursos", "").split(",") if c.strip()],
    }

    async with httpx.AsyncClient(http2=True, timeout=15) as client:
        r = await client.post(MATRICULAR_URL, json=payload)
        if r.status_code >= 300:
            log.error("Falha matrícula", status=r.status_code, body=r.text)
            raise HTTPException(500, "Falha ao matricular aluno")

    return {"msg": "Aluno matriculado com sucesso"}
