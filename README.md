# Backend CED - Integração com Mercado Pago e ChatPro

## Descrição
Este projeto integra notificações de pagamento do Mercado Pago com um sistema de backend para:
1. Processar notificações de pagamento via webhook.
2. Matricular alunos em cursos após a aprovação do pagamento.
3. Enviar mensagens de boas-vindas personalizadas via WhatsApp utilizando a API ChatPro.
4. Registrar eventos importantes em um webhook do Discord para monitoramento.

## Configuração

### Variáveis de Ambiente
Certifique-se de configurar as seguintes variáveis de ambiente no arquivo `.env`:

- `MP_ACCESS_TOKEN`: Token de acesso da API do Mercado Pago.
- `CHATPRO_TOKEN`: Token de autenticação da API ChatPro.
- `CHATPRO_URL`: URL base da API ChatPro.
- `DISCORD_WEBHOOK_URL`: URL do webhook do Discord para envio de logs.

### Dependências
Instale as dependências do projeto utilizando o comando:

```bash
pip install -r requirements.txt
```

## Endpoints

### Webhook Mercado Pago
- **URL**: `/webhook/mp`
- **Método**: `POST`
- **Descrição**: Processa notificações de pagamento do Mercado Pago.

### Matricular Aluno
- **URL**: `/matricular`
- **Método**: `POST`
- **Descrição**: Matricula um aluno em um curso com base nos dados fornecidos.

## Fluxo do Sistema
1. O Mercado Pago envia uma notificação de pagamento para o endpoint `/webhook/mp`.
2. O backend valida o pagamento e, se aprovado, chama o endpoint `/matricular` para matricular o aluno.
3. Após a matrícula, o sistema utiliza a API ChatPro para enviar uma mensagem de boas-vindas ao WhatsApp do aluno.
4. Todos os eventos importantes são registrados em um webhook do Discord para monitoramento.

## Testes

### Testar o Webhook
Utilize ferramentas como o Postman para enviar notificações simuladas ao endpoint `/webhook/mp` e verifique os logs no Discord.

### Verificar Matrícula
Certifique-se de que o endpoint `/matricular` está funcionando corretamente e que os dados do aluno são registrados no sistema.

### Envio de Mensagens no WhatsApp
Confirme que as mensagens de boas-vindas estão sendo enviadas corretamente para o número de WhatsApp do aluno.

## Melhorias Futuras
- Implementar mecanismos de retry para chamadas de API em caso de falhas temporárias.
- Adicionar mais testes automatizados para validar o fluxo completo.
- Melhorar a documentação com exemplos de payloads para cada endpoint.

### URLs do Sistema

- **Backend**: `https://api.cedbrasilia.com.br`
- **Frontend**: `https://www.cedbrasilia.com.br`

---

**Autor**: Equipe CED
