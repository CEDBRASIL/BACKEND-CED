from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field, AnyHttpUrl
from typing import Annotated
import httpx, os, structlog

router = APIRouter()
log = structlog.get_logger()

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
MP_BASE_URL = "https://api.mercadopago.com"
VALOR_ASSINATURA = 4990            # centavos – R$ 49,90

URL_SUCCESS   = "https://www.cedbrasilia.com.br/obrigado"
URL_FAILURE   = "https://www.cedbrasilia.com.br/NAN"
NOTIF_URL     = "https://cedbrasilia.com.br/webhook/mp"
MATRICULAR_URL = "https://www.cedbrasilia.com.br/matricular"

NomeConstrained = Annotated[str, Field(min_length=3, strip_whitespace=True)]
WhatsappConstrained = Annotated[str, Field(regex=r"^\d{10,11}$")]

class CheckoutIn(BaseModel):
    nome: NomeConstrained
    email: EmailStr
    whatsapp: WhatsappConstrained
    cursos: list[str]

class CheckoutOut(BaseModel):
    mp_link: AnyHttpUrl

@router.post("/pay/eeb/checkout", response_model=CheckoutOut, summary="Gera link de pagamento Mercado Pago")
async def gerar_link_pagamento(dados: CheckoutIn):
    if not dados.cursos:
        raise HTTPException(400, "Selecione ao menos um curso")

    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type":  "application/json",
    }

    item_title = "Assinatura CED – Cursos: " + ", ".join(dados.cursos)
    pref = {
        "items": [{
            "title": item_title,
            "quantity": 1,
            "unit_price": VALOR_ASSINATURA / 100
        }],
        "payer": {
            "name":  dados.nome,
            "email": dados.email,
            "phone": {"number": dados.whatsapp}
        },
        "back_urls": {
            "success": URL_SUCCESS,
            "failure": URL_FAILURE,
            "pending": URL_FAILURE
        },
        "auto_return": "approved",
        "notification_url": NOTIF_URL,
    }

    async with httpx.AsyncClient(http2=True, timeout=20) as client:
        r = await client.post(f"{MP_BASE_URL}/checkout/preferences",
                              json=pref, headers=headers)
        if r.status_code != 201:
            log.error("MP erro", status=r.status_code, body=r.text)
            raise HTTPException(500, "Erro ao criar preferência Mercado Pago")
        link = r.json().get("init_point")
        log.info("Preferência criada", link=link)
        return {"mp_link": link}

# --- Webhook ---

@router.post("/webhook/mp", summary="Recebe eventos do Mercado Pago")
async def webhook_mp(evento: dict):
    if evento.get("type") != "payment":
        return {"msg": "Evento ignorado"}

    payment_id = evento["data"]["id"]
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}

    async with httpx.AsyncClient(http2=True) as client:
        r = await client.get(f"{MP_BASE_URL}/v1/payments/{payment_id}", headers=headers)
        if r.status_code != 200:
            log.error("Pagamento não encontrado", id=payment_id)
            raise HTTPException(400, "Pagamento não encontrado")
        pay = r.json()

    if pay["status"] != "approved":
        return {"msg": "Pagamento não aprovado"}

    nome  = (pay["payer"].get("first_name", "") + " " +
             pay["payer"].get("last_name", "")).strip()
    email = pay["payer"].get("email", "")
    fone  = pay["payer"].get("phone", {}).get("number", "")

    # Exemplo simples – em produção use cache ou DB
    cursos = ["Pacote Office"]

    payload = {"nome": nome, "whatsapp": fone, "email": email, "cursos": cursos}
    async with httpx.AsyncClient(http2=True) as client:
        resp = await client.post(MATRICULAR_URL, json=payload)
        if resp.status_code != 200:
            log.error("Matrícula falhou", detalhes=resp.text)
            raise HTTPException(500, "Falha na matrícula")

    return {"msg": "Aluno matriculado com sucesso"}
