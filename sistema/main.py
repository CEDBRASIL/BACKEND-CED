from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import mercadopago
import os
import logging
import requests
import json

# Inicializa logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("matriculas")

app = FastAPI()

# CORS: permitir apenas o domínio oficial
origins = ["https://www.cedbrasilia.com.br"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Token de acesso do Mercado Pago (usar variável de ambiente MP_ACCESS_TOKEN)
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", None)
if not MP_ACCESS_TOKEN:
    logger.error("Token do Mercado Pago (MP_ACCESS_TOKEN) não configurado")
mp_sdk = mercadopago.SDK(MP_ACCESS_TOKEN) if MP_ACCESS_TOKEN else None

# Dados estáticos de cursos (id, nome, valor)
cursos_data = [
    {"id": 1, "nome": "Matemática", "valor": 150.0},
    {"id": 2, "nome": "Português", "valor": 120.0},
    {"id": 3, "nome": "Ciências", "valor": 130.0},
    {"id": 4, "nome": "História", "valor": 110.0},
    {"id": 5, "nome": "Geografia", "valor": 100.0}
]

@app.get("/cursos")
async def get_cursos():
    """
    Retorna lista de cursos disponíveis.
    """
    return {"cursos": cursos_data}

@app.post("/pay/eeb/checkout")
async def checkout(request: Request):
    """
    Gera um link de pagamento do Mercado Pago com base nos dados do aluno e cursos.
    """
    if not mp_sdk:
        raise HTTPException(status_code=500, detail="Erro de configuração do Mercado Pago")
    data = await request.json()
    nome = data.get("nome")
    email = data.get("email")
    whatsapp = data.get("whatsapp")
    cursos = data.get("cursos")  # lista de nomes de cursos

    # Validação básica dos campos
    if not nome or not email or not whatsapp or not cursos:
        raise HTTPException(status_code=400, detail="Dados incompletos enviados")
    if not isinstance(cursos, list) or len(cursos) == 0:
        raise HTTPException(status_code=400, detail="Curso(s) inválido(s)")

    # Monta os items para a preferência do Mercado Pago
    items = []
    total_amount = 0.0
    for curso_nome in cursos:
        # Busca curso por nome
        curso = next((c for c in cursos_data if c["nome"] == curso_nome), None)
        if not curso:
            raise HTTPException(status_code=400, detail=f"Curso desconhecido: {curso_nome}")
        items.append({
            "title": curso["nome"],
            "quantity": 1,
            "currency_id": "BRL",
            "unit_price": float(curso["valor"])
        })
        total_amount += float(curso["valor"])

    # Dados da preferência de pagamento
    preference_data = {
        "items": items,
        "payer": {
            "name": nome,
            "email": email
        },
        "metadata": {
            "nome": nome,
            "email": email,
            "whatsapp": whatsapp,
            "cursos": json.dumps(cursos)  # armazena lista de cursos como JSON
        },
        # URL de notificação (webhook) do Mercado Pago
        "notification_url": "https://api.cedbrasilia.com.br/webhook/mp"
    }

    try:
        response = mp_sdk.preference().create(preference_data)
    except Exception as e:
        logger.error(f"Erro criando preferência MP: {e}")
        raise HTTPException(status_code=502, detail="Erro ao gerar link de pagamento")
    
    preference = response["response"]
    init_point = preference.get("init_point")
    if not init_point:
        logger.error("Nenhum link de pagamento recebido do Mercado Pago")
        raise HTTPException(status_code=500, detail="Falha ao obter link de pagamento")

    return {"link": init_point}

@app.post("/webhook/mp")
async def mp_webhook(request: Request):
    """
    Recebe notificações do Mercado Pago. Se pagamento aprovado, envia dados para matricular.
    """
    data = await request.json()
    logger.info(f"Webhook Mercado Pago recebido: {data}")

    # Extrai o ID do pagamento notificado
    payment_id = None
    if data.get("type") == "payment" and "data" in data:
        payment_id = data["data"].get("id")
    if not payment_id:
        logger.warning("ID de pagamento não encontrado na notificação")
        return {"status": "no_action"}

    # Consulta o pagamento para verificar status
    try:
        headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
        payment_resp = requests.get(f"https://api.mercadopago.com/v1/payments/{payment_id}", headers=headers)
        payment_resp.raise_for_status()
        payment_info = payment_resp.json()
    except Exception as e:
        logger.error(f"Erro ao consultar pagamento {payment_id}: {e}")
        return {"status": "error"}

    status = payment_info.get("status")
    if status != "approved":
        logger.info(f"Pagamento {payment_id} com status {status}, sem ação")
        return {"status": "ignored", "status_pago": status}

    # Pagamento aprovado: recupera ID da preferência para obter metadata
    preference_id = payment_info.get("preference_id")
    if not preference_id:
        logger.error(f"Preference ID não encontrado no pagamento {payment_id}")
        return {"status": "error"}

    # Consulta a preferência para obter dados armazenados (metadata)
    try:
        pref_resp = requests.get(f"https://api.mercadopago.com/checkout/preferences/{preference_id}", headers=headers)
        pref_resp.raise_for_status()
        pref_info = pref_resp.json()
    except Exception as e:
        logger.error(f"Erro ao recuperar preferência {preference_id}: {e}")
        return {"status": "error"}

    metadata = pref_info.get("metadata", {})
    nome = metadata.get("nome")
    email = metadata.get("email")
    whatsapp = metadata.get("whatsapp")
    cursos_json = metadata.get("cursos")
    cursos = []
    if cursos_json:
        try:
            cursos = json.loads(cursos_json)
        except Exception:
            cursos = cursos_json.split(",") if isinstance(cursos_json, str) else []

    # Envia dados para endpoint de matrícula
    matricula_payload = {
        "nome": nome,
        "email": email,
        "whatsapp": whatsapp,
        "cursos": cursos
    }
    try:
        resp = requests.post("https://www.cedbrasilia.com.br/matricular", json=matricula_payload)
        logger.info(f"POST para /matricular retornou status {resp.status_code}")
    except Exception as e:
        logger.error(f"Erro ao enviar dados para /matricular: {e}")
        return {"status": "error"}

    return {"status": "success"}
