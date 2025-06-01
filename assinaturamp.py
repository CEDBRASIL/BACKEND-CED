# assinaturamp.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field, AnyHttpUrl
from typing import Annotated
import httpx, os, structlog

router = APIRouter()
log = structlog.get_logger()

# Carrega token do Mercado Pago do .env
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
MP_BASE_URL = "https://api.mercadopago.com"
VALOR_ASSINATURA = 49.90     # em reais
# URLs de retorno após pagamento
URL_SUCCESS    = "https://www.cedbrasilia.com.br/obrigado"
URL_FAILURE    = "https://www.cedbrasilia.com.br/obrigado"
# URL onde o Mercado Pago enviará notificações de pagamento
NOTIF_URL      = "https://api.cedbrasilia.com.br/webhook/mp"
# Endpoint interno para matrícula automática após pagamento
MATRICULAR_URL = "https://api.cedbrasilia.com.br/matricular"

# Validações com Pydantic
NomeConstrained     = Annotated[str, Field(min_length=3, strip_whitespace=True)]
WhatsappConstrained = Annotated[str, Field(pattern=r"^\d{10,11}$")]

class CheckoutIn(BaseModel):
    nome: NomeConstrained
    email: EmailStr
    whatsapp: WhatsappConstrained
    cursos: list[str]

class CheckoutOut(BaseModel):
    mp_link: AnyHttpUrl

@router.post("/", response_model=CheckoutOut, summary="Gera link de pagamento Mercado Pago")
async def gerar_link_pagamento(dados: CheckoutIn):
    """
    Recebe: nome, email, whatsapp e lista de cursos.
    Retorna: { mp_link: "URL do checkout Mercado Pago" }.
    """
    log.info("Recebendo dados para gerar link de pagamento", dados=dados.dict())

    if not dados.cursos:
        raise HTTPException(400, "Selecione ao menos um curso")

    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    # Monta título + cursos
    item_title = "Assinatura CED – Cursos: " + ", ".join(dados.cursos)
    # Valor em reais (Mercado Pago requer float)
    unit_price = VALOR_ASSINATURA

    # Montagem do payload conforme documentação:
    pref_payload = {
        "items": [
            {
                "title": item_title,
                "quantity": 1,
                "unit_price": unit_price
            }
        ],
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
        # (opcional) external_reference ou outros campos se necessários
    }

    async with httpx.AsyncClient(http2=True, timeout=20) as client:
        r = await client.post(f"{MP_BASE_URL}/checkout/preferences",
                              json=pref_payload, headers=headers)
        if r.status_code != 201:
            log.error("MP erro", status=r.status_code, body=r.text)
            raise HTTPException(500, "Erro ao criar preferência Mercado Pago")
        resposta = r.json()
        link = resposta.get("init_point")
        if not link:
            log.error("MP não retornou init_point", body=r.text)
            raise HTTPException(500, "Falha ao gerar link de pagamento")
        log.info("Preferência criada", link=link)
        return {"mp_link": link}

# ------ Webhook (não modifica) ------

@router.post("/webhook/mp", summary="Recebe eventos do Mercado Pago")
async def webhook_mp(evento: dict):
    """
    Espera receber JSON do Mercado Pago. Se for evento de pagamento,
    verifica status e, se aprovado, aciona matrícula no endpoint interno.
    """
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

    # Extrai dados do pagador
    nome  = (pay["payer"].get("first_name", "") + " " +
             pay["payer"].get("last_name", "")).strip()
    email = pay["payer"].get("email", "")
    fone  = pay["payer"].get("phone", {}).get("number", "")

    # Aqui usamos um placeholder de cursos; em produção você
    # deve mapear com base em external_reference ou metadata.
    # Exemplo fixo:
    cursos = pay.get("metadata", {}).get("cursos", ["Pacote Office"])

    payload = {"nome": nome, "whatsapp": fone, "email": email, "cursos": cursos}
    async with httpx.AsyncClient(http2=True) as client:
        resp = await client.post(MATRICULAR_URL, json=payload)
        if resp.status_code != 200:
            log.error("Matrícula falhou", detalhes=resp.text)
            raise HTTPException(500, "Falha na matrícula")

    return {"msg": "Aluno matriculado com sucesso"}

@router.get("/assinaturamp", summary="Verifica se a rota está funcionando")
async def teste_ativo():
    return {"status": "Rota /assinaturamp ativa e funcionando"}
