from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import httpx
import os

app = FastAPI()

# Configurações do Mercado Pago
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
MP_BASE_URL = "https://api.mercadopago.com"

# URL para matrícula (sua API)
MATRICULAR_URL = "https://api.cedbrasilia.com.br/matricular/"

# Valor fixo assinatura (em centavos)
VALOR_ASSINATURA = 4990

# URLs de retorno
URL_SUCCESS = "https://www.cedbrasilia.com.br/obrigado"
URL_FAILURE = "https://www.cedbrasilia.com.br/NAN"

# Cache simples em memória para pedidos (usar banco de dados em produção)
pedido_cache = {}

# Melhorias na função para buscar cursos
async def get_cursos():
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get("https://cedbrasilia.com.br/api/cursos/")
            resp.raise_for_status()
            data = resp.json()
            return data  # Retorna lista de cursos no formato esperado
        except httpx.RequestError as exc:
            print(f"Erro ao buscar cursos: {exc}")
            return []
        except httpx.HTTPStatusError as exc:
            print(f"Erro HTTP ao buscar cursos: {exc.response.status_code}")
            return []

@app.get("/pay/eeb/checkout", response_class=HTMLResponse)
async def form_checkout():
    cursos = await get_cursos()
    options_html = ""
    for curso in cursos:
        options_html += f'<input type="checkbox" name="cursos" value="{curso["nome"]}"> {curso["nome"]}<br>'
    html_content = f"""
    <html><body>
    <h2>Cadastro e Pagamento - CED</h2>
    <form action="/pay/eeb/checkout" method="post">
      Nome: <input name="nome" type="text" required><br>
      WhatsApp: <input name="telefone" type="text" required><br>
      Email: <input name="email" type="email" required><br>
      <h3>Selecione os cursos:</h3>
      {options_html}
      <br>
      <button type="submit">Gerar link para pagamento</button>
    </form>
    </body></html>
    """
    return HTMLResponse(content=html_content)

# Melhorias na rota para gerar link de pagamento
@app.post("/pay/eeb/checkout")
async def gerar_link_pagamento(
    nome: str = Form(...),
    telefone: str = Form(...),
    email: str = Form(...),
    cursos: list[str] = Form(...)
):
    if not cursos:
        raise HTTPException(status_code=400, detail="Selecione ao menos um curso")

    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    item_title = "Assinatura CED - Cursos: " + ", ".join(cursos)
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
        "notification_url": "https://cedbrasilia.com.br/webhook/mp"
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{MP_BASE_URL}/checkout/preferences", json=preference_data, headers=headers)
        if resp.status_code != 201:
            raise HTTPException(status_code=500, detail="Erro ao criar preferência Mercado Pago")
        preference = resp.json()
        payment_link = preference.get("init_point")

    # Armazenar dados do pedido em cache (exemplo simplificado)
    # Em produção, use um banco de dados ou cache persistente
    pedido_cache[nome] = {"telefone": telefone, "email": email, "cursos": cursos}

    return RedirectResponse(url=payment_link)

# Melhorias no webhook para processar notificações
@app.post("/webhook/mp")
async def webhook_mp(request: Request):
    data = await request.json()

    if "type" in data and data["type"] == "payment":
        payment_id = data["data"]["id"]

        headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{MP_BASE_URL}/v1/payments/{payment_id}", headers=headers)
            if resp.status_code != 200:
                return JSONResponse(status_code=400, content={"message": "Pagamento não encontrado"})
            payment_info = resp.json()

        if payment_info["status"] == "approved":
            payer = payment_info.get("payer", {})
            nome = payer.get("first_name", "") + " " + payer.get("last_name", "")
            email = payer.get("email", "")
            telefone = payer.get("phone", {}).get("number", "")

            # Recuperar cursos do cache
            pedido = pedido_cache.get(nome)
            if not pedido:
                return JSONResponse(status_code=400, content={"message": "Pedido não encontrado no cache"})

            cursos_selecionados = pedido["cursos"]

            matricular_payload = {
                "nome": nome,
                "telefone": telefone,
                "email": email,
                "cursos": cursos_selecionados
            }
            async with httpx.AsyncClient() as client:
                matricular_resp = await client.post(MATRICULAR_URL, json=matricular_payload)
                if matricular_resp.status_code != 200:
                    return JSONResponse(status_code=500, content={"message": "Falha na matrícula"})

            return JSONResponse(content={"message": "Pagamento aprovado e aluno matriculado"})

    return JSONResponse(content={"message": "Evento ignorado"})
