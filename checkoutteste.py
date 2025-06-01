from fastapi import FastAPI, Request, Form, HTTPException, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import httpx
import os
import logging
from cursos import CURSOS_OM

router = APIRouter()
logging.basicConfig(level=logging.DEBUG)

# Token SANDBOX do Mercado Pago (use sua variável de ambiente)
MP_ACCESS_TOKEN = os.getenv("MP_TEST_ACCESS_TOKEN")
MP_BASE_URL = "https://api.mercadopago.com"

VALOR_ASSINATURA = 4990  # em centavos

# URLs de retorno
URL_SUCCESS = "https://www.cedbrasilia.com.br/obrigado"
URL_FAILURE = "https://www.cedbrasilia.com.br/falha"

# Endpoint de matrícula
MATRICULAR_URL = "https://api.cedbrasilia.com.br/matricular"

@router.get("/pay/eeb/checkoutteste", response_class=HTMLResponse)
async def form_checkout_teste():
    options_html = ""
    for curso_nome in CURSOS_OM.keys():
        options_html += f'<input type="checkbox" name="cursos" value="{curso_nome}"> {curso_nome}<br>'
    html_content = f"""
    <html>
      <body>
        <h2>Teste Cadastro e Pagamento - CED</h2>
        <form action="/checkoutteste/pay/eeb/checkoutteste" method="post">
          Nome: <input name="nome" type="text" required><br>
          WhatsApp: <input name="telefone" type="text" required><br>
          Email: <input name="email" type="email" required><br>
          <h3>Selecione os cursos:</h3>
          {options_html}
          <br>
          <button type="submit">Gerar link para pagamento (Teste)</button>
        </form>
      </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@router.post("/pay/eeb/checkoutteste")
async def gerar_link_pagamento_teste(
    nome: str = Form(...),
    telefone: str = Form(...),
    email: str = Form(...),
    cursos: list[str] = Form(...)
):
    logging.debug(f"Recebido: nome={nome}, telefone={telefone}, email={email}, cursos={cursos}")

    if not cursos:
        raise HTTPException(status_code=400, detail="Selecione ao menos um curso")

    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    item_title = "Assinatura CED TESTE - Cursos: " + ", ".join(cursos)
    preference_data = {
        "items": [{
            "title": item_title,
            "quantity": 1,
            "unit_price": VALOR_ASSINATURA / 100
        }],
        "payer": {
            "name": nome,
            "email": email,
            "phone": {"number": telefone}
        },
        "back_urls": {
            "success": URL_SUCCESS,
            "failure": URL_FAILURE,
            "pending": URL_FAILURE
        },
        "auto_return": "approved",
        "notification_url": "https://api.cedbrasilia.com.br/checkoutteste/webhook/mpteste"
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{MP_BASE_URL}/checkout/preferences", json=preference_data, headers=headers)
        if resp.status_code != 201:
            logging.error(f"Erro ao criar preferência: {resp.text}")
            raise HTTPException(status_code=500, detail="Erro ao criar preferência Mercado Pago")
        preference = resp.json()
        return RedirectResponse(url=preference["init_point"])

@router.post("/webhook/mpteste")
async def webhook_mp_teste(request: Request):
    data = await request.json()
    logging.debug(f"Webhook recebido: {data}")

    if data.get("type") != "payment":
        return JSONResponse(content={"message": "Evento ignorado"})

    payment_id = data["data"].get("id")
    if not payment_id:
        return JSONResponse(status_code=400, content={"message": "ID de pagamento ausente."})

    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{MP_BASE_URL}/v1/payments/{payment_id}", headers=headers)
        if resp.status_code != 200:
            return JSONResponse(status_code=400, content={"message": "Pagamento não encontrado"})
        pay = resp.json()

    if pay.get("status") != "approved":
        return JSONResponse(content={"message": "Pagamento não aprovado"})

    # Simulação básica de matrícula (substituir por lógica real se quiser)
    matricular_payload = {
        "nome": pay["payer"].get("first_name", "Aluno Teste"),
        "telefone": pay["payer"].get("phone", {}).get("number", ""),
        "email": pay["payer"].get("email", ""),
        "cursos": ["Pacote Office"]
    }

    async with httpx.AsyncClient() as client:
        matricula_resp = await client.post(MATRICULAR_URL, json=matricular_payload)
        if matricula_resp.status_code != 200:
            return JSONResponse(status_code=500, content={"message": "Falha ao matricular aluno"})

    return JSONResponse(content={"message": "Matrícula de teste realizada com sucesso"})

# Importante: não esqueça de incluir esse router no main.py
# app.include_router(checkoutteste_router)
