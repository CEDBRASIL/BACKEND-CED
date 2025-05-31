from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import httpx
import os
import logging
from cursos import CURSOS_OM

app = FastAPI()
logging.basicConfig(level=logging.DEBUG)

# Configurações Mercado Pago TESTE (usar sandbox token)
MP_ACCESS_TOKEN = os.getenv("MP_TEST_ACCESS_TOKEN", "TOKEN_TESTE")
MP_BASE_URL = "https://api.mercadopago.com"

# Valor fixo assinatura (em centavos)
VALOR_ASSINATURA = 4990

# URLs de retorno teste
URL_SUCCESS = "https://www.cedbrasilia.com.br/obrigado"
URL_FAILURE = "https://www.cedbrasilia.com.br/teste/failure"

@app.get("/pay/eeb/checkoutteste", response_class=HTMLResponse)
async def form_checkout_teste():
    options_html = ""
    for curso_nome in CURSOS_OM.keys():
        options_html += f'<input type="checkbox" name="cursos" value="{curso_nome}"> {curso_nome}<br>'
    html_content = f"""
    <html><body>
    <h2>Teste Cadastro e Pagamento - CED</h2>
    <form action="/pay/eeb/checkoutteste" method="post">
      Nome: <input name="nome" type="text" required><br>
      WhatsApp: <input name="telefone" type="text" required><br>
      Email: <input name="email" type="email" required><br>
      <h3>Selecione os cursos:</h3>
      {options_html}
      <br>
      <button type="submit">Gerar link para pagamento (Teste)</button>
    </form>
    </body></html>
    """
    return HTMLResponse(content=html_content)

@app.post("/pay/eeb/checkoutteste")
async def gerar_link_pagamento_teste(
    nome: str = Form(...),
    telefone: str = Form(...),
    email: str = Form(...),
    cursos: list[str] = Form(...)
):
    logging.debug(f"Dados recebidos: nome={nome}, telefone={telefone}, email={email}, cursos={cursos}")

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
        "notification_url": "https://seusistema.com.br/webhook/mpteste"
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{MP_BASE_URL}/checkout/preferences", json=preference_data, headers=headers)
        if resp.status_code != 201:
            logging.error(f"Erro ao criar preferência MP Teste: {resp.text}")
            raise HTTPException(status_code=500, detail="Erro ao criar preferência Mercado Pago Teste")
        preference = resp.json()
        payment_link = preference.get("init_point")

    return RedirectResponse(url=payment_link)

@app.post("/webhook/mpteste")
async def webhook_mp_teste(request: Request):
    data = await request.json()
    logging.debug(f"Webhook teste recebido: {data}")

    if "type" in data and data["type"] == "payment":
        payment_id = data["data"].get("id")
        if not payment_id:
            logging.error("Webhook recebido sem ID de pagamento.")
            return JSONResponse(status_code=400, content={"message": "ID de pagamento ausente."})

        headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}

        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{MP_BASE_URL}/v1/payments/{payment_id}", headers=headers)
            if resp.status_code != 200:
                logging.error(f"Erro ao buscar pagamento teste: {resp.text}")
                return JSONResponse(status_code=400, content={"message": "Pagamento não encontrado"})

            payment_info = resp.json()

        if payment_info.get("status") == "approved":
            payer = payment_info.get("payer", {})
            nome = payer.get("first_name", "") + " " + payer.get("last_name", "")
            email = payer.get("email", "")
            telefone = payer.get("phone", {}).get("number", "")
            cursos_selecionados = ["Teste Curso A"]  # Placeholder para teste

            matricular_payload = {
                "nome": nome,
                "telefone": telefone,
                "email": email,
                "cursos": cursos_selecionados
            }

            async with httpx.AsyncClient() as client:
                matricular_resp = await client.post(MATRICULAR_URL, json=matricular_payload)
                if matricular_resp.status_code != 200:
                    logging.error(f"Falha na matrículaa teste: {matricular_resp.text}")
                    return JSONResponse(status_code=500, content={"message": "Falha na matrícula"})

            return JSONResponse(content={"message": "Pagamento aprovado e aluno matriculado (teste)"})

    return JSONResponse(content={"message": "Evento ignorado"})
