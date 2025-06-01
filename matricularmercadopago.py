from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timedelta
import requests
import os
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Request


load_dotenv()
router = APIRouter()

router = APIRouter()

MERCADO_PAGO_TOKEN = os.getenv("MP_TOKEN")  # Defina no .env

@router.post("/mercadopago")
async def criar_assinatura_mp(request: Request):
    dados = await request.json()

    nome = dados.get("nome")
    email = dados.get("email")
    whatsapp = dados.get("whatsapp")
    cursos = dados.get("cursos", [])

    if not (nome and email and whatsapp and cursos):
        raise HTTPException(status_code=400, detail="Dados incompletos para assinatura.")

    curso_str = ", ".join(cursos)

    hoje = datetime.now()
    daqui_um_ano = hoje + timedelta(days=365)

    payload = {
        "payer_email": email,
        "payer": {
            "name": nome,
            "email": email,
            "phone": {
                "number": whatsapp
            }
        },
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": 49.9,
            "currency_id": "BRL",
            "start_date": hoje.strftime("%Y-%m-%dT00:00:00.000-03:00"),
            "end_date": daqui_um_ano.strftime("%Y-%m-%dT00:00:00.000-03:00")
        },
        "reason": f"Assinatura CED – Cursos: {curso_str}",
        "external_reference": "CED-ASSINATURA",
        "back_url": "https://www.cedbrasilia.com.br/obrigado",
        "notification_url": "https://api.cedbrasilia.com.br/webhook/mp"
    }

    headers = {
        "Authorization": f"Bearer {MERCADO_PAGO_TOKEN}",
        "Content-Type": "application/json"
    }

    url = "https://api.mercadopago.com/preapproval"

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 201:
            return response.json()
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Erro ao criar assinatura: {response.text}"
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
