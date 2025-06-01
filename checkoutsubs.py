# checkoutsubs.py

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import httpx, os, logging
from cursos import CURSOS_OM

router = APIRouter()
logging.basicConfig(level=logging.INFO)

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
MP_BASE_URL = "https://api.mercadopago.com"
VALOR_ASSINATURA = 59.90

BACK_URL = "https://www.cedbrasilia.com.br/obrigado"
WEBHOOK_URL = "https://api.cedbrasilia.com.br/webhook/mp"

@router.get("/pay/eeb/checkout", response_class=HTMLResponse)
async def exibir_formulario():
    options = ""
    for nome in CURSOS_OM:
        options += f'<input type="checkbox" name="cursos" value="{nome}"> {nome}<br>'
    html = f"""
    <html><body>
      <h2>Assinatura CED - R$59,90/mês</h2>
      <form method="post" action="/pay/eeb/checkout">
        Nome: <input name="nome" required><br>
        WhatsApp (somente números): <input name="whatsapp" required><br>
        Email: <input name="email" type="email" required><br><br>
        <strong>Cursos:</strong><br>{options}<br>
        <button type="submit">Iniciar matrícula e pagar</button>
      </form>
    </body></html>
    """
    return HTMLResponse(content=html)

@router.post("/pay/eeb/checkout")
async def criar_assinatura(
    nome: str = Form(...),
    whatsapp: str = Form(...),
    email: str = Form(...),
    cursos: list[str] = Form(...)
):
    if not cursos:
        raise HTTPException(400, "Selecione ao menos um curso")

    metadata = {
        "nome": nome,
        "whatsapp": whatsapp,
        "email": email,
        "cursos": ",".join(cursos)
    }

    payload = {
        "reason": f"Assinatura CED – Cursos: {', '.join(cursos)}",
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": VALOR_ASSINATURA,
            "currency_id": "BRL",
            "start_date": "2025-06-01T00:00:00.000-03:00",
            "end_date": "2026-06-01T00:00:00.000-03:00"
        },
        "payer_email": email,
        "back_url": BACK_URL,
        "notification_url": WEBHOOK_URL,
        "metadata": metadata
    }

    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(http2=True, timeout=15) as client:
        r = await client.post(f"{MP_BASE_URL}/preapproval", json=payload, headers=headers)
        if r.status_code != 201 and r.status_code != 200:
            logging.error(f"Erro ao criar assinatura MP: {r.text}")
            raise HTTPException(500, "Erro ao criar assinatura Mercado Pago")
        assinatura = r.json()
        init_point = assinatura.get("init_point") or assinatura.get("sandbox_init_point")
        if not init_point:
            raise HTTPException(500, "Link de assinatura não retornado")
        return RedirectResponse(url=init_point)
