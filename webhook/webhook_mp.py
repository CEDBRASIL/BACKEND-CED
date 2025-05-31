from fastapi import APIRouter, HTTPException, Request
import httpx, os, structlog, json, time, asyncio

router = APIRouter()
log = structlog.get_logger()

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
MP_BASE_URL     = "https://api.mercadopago.com"
MATRICULAR_URL  = "https://api.cedbrasilia.com.br/matricular"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
CHATPRO_TOKEN = os.getenv("CHATPRO_TOKEN")
CHATPRO_URL = os.getenv("CHATPRO_URL")

def send_discord_log(message: str):
    """Envia logs detalhados para o Discord."""
    payload = {"content": f"```{message}```"}
    try:
        httpx.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        log.error("Falha ao enviar log para o Discord", error=str(e))

def retry_request(func, retries=3, delay=2, *args, **kwargs):
    """
    Função genérica para realizar retries em chamadas de API.
    :param func: Função a ser chamada.
    :param retries: Número de tentativas.
    :param delay: Tempo de espera entre as tentativas (em segundos).
    """
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            log.error(f"Erro na tentativa {attempt + 1}/{retries}: {str(e)}")
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise

@router.post("/webhook/mp")
async def webhook_mp(evento: dict, request: Request):
    """
    Rota que o Mercado Pago chama quando um pagamento muda de status.
    Se estiver aprovado, envia os dados do aluno para /matricular e envia mensagem no WhatsApp.
    """
    log.info("Recebendo evento do Mercado Pago", evento=evento)
    send_discord_log(f"Evento recebido: {json.dumps(evento, indent=2)}")

    if evento.get("type") != "preapproval":
        log.info("Evento ignorado por não ser do tipo 'preapproval'", tipo=evento.get("type"))
        send_discord_log(f"Evento ignorado: {evento.get('type')}")
        return {"msg": "evento ignorado"}

    preapproval_id = evento.get("data", {}).get("id")
    if not preapproval_id:
        log.error("ID da assinatura ausente no evento", evento=evento)
        send_discord_log("Erro: ID da assinatura ausente no evento")
        raise HTTPException(400, "ID da assinatura ausente no evento")

    # Consulta os dados da assinatura
    log.info("Consultando dados da assinatura", preapproval_id=preapproval_id)
    send_discord_log(f"Consultando assinatura: {preapproval_id}")
    async with httpx.AsyncClient(http2=True) as client:
        resp = await retry_request(client.get, retries=3, delay=2, url=f"{MP_BASE_URL}/preapproval/{preapproval_id}", headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"})
        if resp.status_code != 200:
            log.error("Assinatura não encontrada", id=preapproval_id, status=resp.status_code, body=resp.text)
            send_discord_log(f"Erro ao consultar assinatura: {resp.text}")
            raise HTTPException(400, "Assinatura não encontrada")
        preapproval = resp.json()

    log.info("Dados da assinatura recebidos", assinatura=preapproval)
    send_discord_log(f"Dados da assinatura: {json.dumps(preapproval, indent=2)}")

    # Ignora assinaturas não aprovadas
    if preapproval.get("status") != "authorized":
        log.info("Assinatura não autorizada", status=preapproval.get("status"), id=preapproval_id)
        send_discord_log(f"Assinatura não autorizada: {preapproval.get('status')}\n{json.dumps(preapproval, indent=2)}")
        return {"msg": "Assinatura não autorizada"}

    # Extrai os dados salvos no metadata
    meta = preapproval.get("metadata", {})
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
        r = await retry_request(client.post, retries=3, delay=2, url=MATRICULAR_URL, json=payload)
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
        whatsapp_resp = await retry_request(client.post, retries=3, delay=2, url=f"{CHATPRO_URL}/send-message", json=whatsapp_payload, headers=whatsapp_headers)
        if whatsapp_resp.status_code >= 300:
            log.error("Falha ao enviar mensagem no WhatsApp", status=whatsapp_resp.status_code, body=whatsapp_resp.text)
            send_discord_log(f"Erro ao enviar mensagem no WhatsApp: {whatsapp_resp.text}")
            raise HTTPException(500, "Falha ao enviar mensagem no WhatsApp")

    log.info("Mensagem enviada com sucesso no WhatsApp", payload=whatsapp_payload)
    send_discord_log("Mensagem enviada com sucesso no WhatsApp")

    return {"msg": "Aluno matriculado e mensagem enviada com sucesso"}

# Ensure the `payer_email` field is correctly placed in the payload for Mercado Pago's subscription API.
# Add detailed logging to capture the exact payload being sent.

async def create_subscription(payload):
    """Creates a subscription in Mercado Pago."""
    # Ensure `payer_email` is included in the payload
    if 'payer' not in payload:
        payload['payer'] = {}
    if 'email' not in payload['payer']:
        payload['payer']['email'] = payload.get('email')

    log.info("Criando assinatura no Mercado Pago", payload=payload)
    send_discord_log(f"Payload enviado para criar assinatura: {json.dumps(payload, indent=2)}")

    async with httpx.AsyncClient(http2=True, timeout=15) as client:
        headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
        response = await retry_request(client.post, retries=3, delay=2, url=f"{MP_BASE_URL}/preapproval", json=payload, headers=headers)

        if response.status_code != 200:
            log.error("Erro ao criar assinatura no Mercado Pago", status=response.status_code, body=response.text, headers=headers, payload=payload)
            send_discord_log(f"Erro ao criar assinatura: {response.text}\nHeaders: {json.dumps(headers, indent=2)}\nPayload: {json.dumps(payload, indent=2)}")
            raise HTTPException(400, "Erro ao criar assinatura no Mercado Pago")

        log.info("Assinatura criada com sucesso", response=response.json())
        send_discord_log(f"Assinatura criada com sucesso: {json.dumps(response.json(), indent=2)}")
        return response.json()

async def handle_subscription_creation():
    """Handles the creation of a subscription by calling the create_subscription function."""
    payload = {
        "end_date": "2026-06-01T00:00:00.000-03:00",
        "back_url": "https://www.cedbrasilia.com.br/obrigado",
        "reason": "Assinatura CED – Cursos: Excel PRO",
        "external_reference": "CED-ASSINATURA",
        "payer": {
            "name": "NOME_DO_CLIENTE",
            "email": "EMAIL_DO_CLIENTE",
            "phone": {
                "number": "TELEFONE_DO_CLIENTE"
            }
        },
        "notification_url": "https://www.cedbrasilia.com.br/webhook/webhook_mp"
    }

    await create_subscription(payload)

# Call the async function
asyncio.run(handle_subscription_creation())