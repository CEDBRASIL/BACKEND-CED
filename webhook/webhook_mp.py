from fastapi import APIRouter, HTTPException
import httpx, os, structlog, json

router = APIRouter()
log = structlog.get_logger()

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
MP_BASE_URL     = "https://api.mercadopago.com"
MATRICULAR_URL  = "https://www.cedbrasilia.com.br/matricular"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

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
    Se estiver aprovado, envia os dados do aluno para /matricular.
    """
    log.info("Recebendo evento do Mercado Pago", evento=evento)
    send_discord_log(f"Evento recebido: {json.dumps(evento, indent=2)}")

    if evento.get("type") != "payment":
        log.info("Evento ignorado por não ser do tipo 'payment'", tipo=evento.get("type"))
        send_discord_log(f"Evento ignorado: {evento.get('type')}")
        return {"msg": "evento ignorado"}

    payment_id = evento.get("data", {}).get("id")
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
    if pay.get("status") != "approved":
        log.info("Pagamento não aprovado", status=pay.get("status"), id=payment_id)
        send_discord_log(f"Pagamento não aprovado: {pay.get('status')}")
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

    return {"msg": "Aluno matriculado com sucesso"}