from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field, AnyHttpUrl
from typing import Annotated
import httpx
import os
import structlog
import json

router = APIRouter()
log = structlog.get_logger()

MP_ACCESS_TOKEN = os.getenv("MP_TEST_ACCESS_TOKEN", "TOKEN_TESTE")
MP_BASE_URL = "https://api.mercadopago.com"

VALOR_ASSINATURA = 4990          # R$49,90 (centavos)
URL_SUCCESS = "https://www.cedbrasilia.com.br/obrigado"
URL_FAILURE = "https://www.cedbrasilia.com.br/NAN"
NOTIF_URL = "https://www.cedbrasilia.com.br/webhook/webhook_mp"
MATRICULAR_URL = "https://www.cedbrasilia.com.br/matricular"
CHATPRO_TOKEN = os.getenv("CHATPRO_TOKEN")
CHATPRO_URL = os.getenv("CHATPRO_URL")

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1377838283975036928/IgVvwyrBBWflKyXbIU9dgH4PhLwozHzrf-nJpj3w7dsZC-Ds9qN8_Toym3Tnbj-3jdU4"


NomeConstrained = Annotated[str, Field(min_length=3, strip_whitespace=True)]
WhatsappConstrained = Annotated[str, Field(pattern=r"^\d{10,11}$")]


class CheckoutIn(BaseModel):
    nome: NomeConstrained
    email: EmailStr
    whatsapp: WhatsappConstrained
    cursos: list[str]


class CheckoutOut(BaseModel):
    mp_link: AnyHttpUrl


@router.post("/pay/eeb/checkout", response_model=CheckoutOut, summary="Gera link de pagamento Mercado Pago")
async def gerar_link_pagamento(dados: CheckoutIn):
    log.info("Recebendo dados para gerar link de pagamento", dados=dados.dict())
    send_discord_log(f"Recebendo dados para gerar link de pagamento: {json.dumps(dados.dict(), indent=2)}")

    if not dados.cursos:
        log.error("Nenhum curso selecionado")
        send_discord_log("Erro: Nenhum curso selecionado")
        raise HTTPException(400, "Selecione ao menos um curso")

    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    item_title = "Assinatura CED – Cursos: " + ", ".join(dados.cursos)
    pref = {
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": VALOR_ASSINATURA / 100,
            "currency_id": "BRL",
            "start_date": "2025-06-01T00:00:00.000-03:00",
            "end_date": "2026-06-01T00:00:00.000-03:00"
        },
        "back_url": URL_SUCCESS,
        "reason": item_title,
        "external_reference": "CED-ASSINATURA",
        "payer": {
            "name": dados.nome,
            "email": dados.email,  # Corrigindo para incluir o email no objeto payer
            "phone": {"number": dados.whatsapp}
        },
        "notification_url": NOTIF_URL,
    }

    # Adicionando log detalhado do payload corrigido
    send_discord_log(f"Payload corrigido para criar assinatura: {json.dumps(pref, indent=2)}")

    async with httpx.AsyncClient(http2=True, timeout=20) as client:
        r = await client.post(f"{MP_BASE_URL}/preapproval", json=pref, headers=headers)
        if r.status_code != 201:
            log.error("Erro ao criar assinatura no Mercado Pago", status=r.status_code, body=r.text)
            send_discord_log(f"Erro ao criar assinatura no Mercado Pago: {r.text}")
            raise HTTPException(500, "Erro ao criar assinatura no Mercado Pago")
        link = r.json().get("init_point")
        log.info("Assinatura criada com sucesso", link=link)
        send_discord_log(f"Assinatura criada com sucesso: {link}")
        return {"mp_link": link}


def send_discord_log(message: str):
    """Envia logs detalhados para o Discord."""
    payload = {"content": f"```{message}```"}
    try:
        httpx.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        log.error("Falha ao enviar log para o Discord", error=str(e))


@router.post("/webhook/mp")
async def webhook_mp(evento: dict):
    """
    Rota que o Mercado Pago chama quando um pagamento muda de status.
    Se estiver aprovado, envia os dados do aluno para /matricular e envia mensagem no WhatsApp.
    """
    log.info("Recebendo evento do Mercado Pago", evento=evento)

    # Envia log para o Discord para monitoramento
    send_discord_log(f"Evento recebido: {json.dumps(evento, indent=2)}")

    if evento.get("type") != "payment":
        log.info("Evento ignorado por não ser do tipo 'payment'", tipo=evento.get("type"))
        send_discord_log(f"Evento ignorado: {evento.get('type')}")
        return {"msg": "evento ignorado"}

    payment_id = evento["data"].get("id")
    if not payment_id:
        log.error("ID do pagamento ausente no evento", evento=evento)
        send_discord_log("Erro: ID do pagamento ausente no evento")
        raise HTTPException(400, "ID do pagamento ausente no evento")

    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}

    # Consulta os dados do pagamento
    log.info("Consultando dados do pagamento", payment_id=payment_id)
    send_discord_log(f"Consultando pagamento: {payment_id}")
    async with httpx.AsyncClient(http2=True) as client:
        resp = await client.get(f"{MP_BASE_URL}/v1/payments/{payment_id}", headers=headers)
        if resp.status_code != 200:
            log.error("Pagamento não encontrado", id=payment_id, status=resp.status_code, body=resp.text)
            send_discord_log(f"Erro ao consultar pagamento: {resp.text}")
            raise HTTPException(400, "Pagamento não encontrado")
        pay = resp.json()

    log.info("Dados do pagamento recebidos", pagamento=pay)
    send_discord_log(f"Dados do pagamento: {json.dumps(pay, indent=2)}")

    # Ignora pagamentos não aprovados
    if pay["status"] != "approved":
        log.info("Pagamento não aprovado", status=pay["status"], id=payment_id)
        send_discord_log(f"Pagamento não aprovado: {pay['status']}")
        return {"msg": "Pagamento não aprovado"}

    # Extrai os dados salvos no metadata
    meta = pay.get("metadata", {})
    payload = {
        "nome":     meta.get("nome"),
        "email":    meta.get("email"),
        "whatsapp": meta.get("whatsapp"),
        "cursos":   [c.strip() for c in meta.get("cursos", "").split(",") if c.strip()],
    }

    log.info("Dados extraídos do metadata", payload=payload)
    send_discord_log(f"Payload para matrícula: {json.dumps(payload, indent=2)}")

    # Chama o endpoint de matrícula com os dados do aluno
    log.info("Enviando dados para matrícula", url=MATRICULAR_URL, payload=payload)
    async with httpx.AsyncClient(http2=True, timeout=15) as client:
        r = await client.post(MATRICULAR_URL, json=payload)
        if r.status_code >= 300:
            log.error("Falha ao matricular aluno", status=r.status_code, body=r.text)
            send_discord_log(f"Erro ao matricular aluno: {r.text}")
            raise HTTPException(500, "Falha ao matricular aluno")

    log.info("Aluno matriculado com sucesso", payload=payload)
    send_discord_log("Aluno matriculado com sucesso")

    # Envia mensagem de boas-vindas pelo WhatsApp
    whatsapp_message = f"""👋 Seja bem-vindo(a), {payload['nome']}! 

🔑 Acesso
Login: 20254158021
Senha: 123456

📚 Cursos Adquiridos: 
• " + "\n• ".join(payload['cursos']) + "

🧑‍🏫 Grupo da Escola: https://chat.whatsapp.com/Gzn00RNW15ABBfmTc6FEnP

📱 Acesse pelo seu dispositivo preferido:
• Android: https://play.google.com/store/apps/details?id=br.com.om.app&hl=pt
• iOS: https://apps.apple.com/fr/app/meu-app-de-cursos/id1581898914
• Computador: https://ead.cedbrasilia.com.br/

Caso deseje trocar ou adicionar outros cursos, basta responder a esta mensagem.

Obrigado por escolher a CED Cursos! Estamos aqui para ajudar nos seus objetivos educacionais.

Atenciosamente, Equipe CED"""

    whatsapp_payload = {
        "number": payload["whatsapp"],
        "message": whatsapp_message
    }

    log.info("Enviando mensagem no WhatsApp", url=f"{CHATPRO_URL}/send-message", payload=whatsapp_payload)
    send_discord_log(f"Enviando mensagem no WhatsApp: {json.dumps(whatsapp_payload, indent=2)}")
    async with httpx.AsyncClient(http2=True, timeout=15) as client:
        whatsapp_headers = {"Authorization": f"Bearer {CHATPRO_TOKEN}"}
        whatsapp_resp = await client.post(f"{CHATPRO_URL}/send-message", json=whatsapp_payload, headers=whatsapp_headers)
        if whatsapp_resp.status_code >= 300:
            log.error("Falha ao enviar mensagem no WhatsApp", status=whatsapp_resp.status_code, body=whatsapp_resp.text)
            send_discord_log(f"Erro ao enviar mensagem no WhatsApp: {whatsapp_resp.text}")
            raise HTTPException(500, "Falha ao enviar mensagem no WhatsApp")

    log.info("Mensagem enviada com sucesso no WhatsApp", payload=whatsapp_payload)
    send_discord_log("Mensagem enviada com sucesso no WhatsApp")

    return {"msg": "Aluno matriculado e mensagem enviada com sucesso"}
