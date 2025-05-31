# Configuração do NOTIF_URL para Mercado Pago

O `NOTIF_URL` é usado para receber notificações do Mercado Pago sobre eventos, como a aprovação de pagamentos. Certifique-se de que o endpoint `/webhook/mp` esteja configurado corretamente no seu backend.

## Passos para Configuração

1. **Endpoint Público**:
   - Certifique-se de que o endpoint `/webhook/mp` esteja acessível publicamente.
   - Exemplo de URL: `https://api.cedbrasilia.com.br/webhook/mp`.

2. **Configuração no Mercado Pago**:
   - Acesse o painel do Mercado Pago.
   - Vá para a seção de notificações e configure a URL de notificação como `https://api.cedbrasilia.com.br/webhook/mp`.

3. **Teste de Notificação**:
   - Use a ferramenta de sandbox do Mercado Pago para enviar notificações de teste para o seu endpoint.
   - Verifique os logs do servidor para garantir que as notificações estão sendo processadas corretamente.

4. **Implementação do Endpoint**:
   - O endpoint `/webhook/mp` já está implementado no arquivo `checkout_api.py`.
   - Ele processa eventos do tipo `payment` e realiza ações como verificar o status do pagamento e matricular o aluno.

## Exemplo de Log para Depuração

Certifique-se de que os logs estão habilitados para capturar informações detalhadas sobre as notificações recebidas:

```python
@router.post("/webhook/mp")
async def webhook_mp(evento: dict):
    log.info("Notificação recebida", evento=evento)
    if evento.get("type") != "payment":
        return {"msg": "evento ignorado"}

    payment_id = evento["data"]["id"]
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}

    async with httpx.AsyncClient(http2=True) as client:
        resp = await client.get(f"{MP_BASE_URL}/v1/payments/{payment_id}", headers=headers)
        if resp.status_code != 200:
            log.error("Pagamento não encontrado", id=payment_id)
            raise HTTPException(400, "Pagamento não encontrado")
        pay = resp.json()

    if pay["status"] != "approved":
        return {"msg": "Pagamento não aprovado"}

    log.info("Pagamento aprovado", payment=pay)
    return {"msg": "Aluno matriculado com sucesso"}
```

Com isso, o `NOTIF_URL` estará configurado corretamente e pronto para receber notificações do Mercado Pago.
