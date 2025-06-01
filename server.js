// server.js
const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');
const mercadopago = require('mercadopago');
const fs = require('fs');
const path = require('path');
const twilio = require('twilio');

const app = express();
app.use(cors());
app.use(bodyParser.json());

// Configurações do Mercado Pago
mercadopago.configure({
  access_token: process.env.MP_ACCESS_TOKEN  // Token de acesso do Mercado Pago
});

// Configurações do Twilio (WhatsApp)
const accountSid = process.env.TWILIO_ACCOUNT_SID;   // SID da conta Twilio
const authToken  = process.env.TWILIO_AUTH_TOKEN;    // Auth token da Twilio
const client = twilio(accountSid, authToken);
const twilioFrom = `whatsapp:${process.env.TWILIO_WHATSAPP_NUMBER}`;  // Ex: "whatsapp:+14155238886"

// Arquivo JSON para simular um banco de dados simples
const DATA_FILE = path.join(__dirname, 'students.json');

// Função para ler dados de estudantes do arquivo
function loadStudents() {
  if (!fs.existsSync(DATA_FILE)) {
    fs.writeFileSync(DATA_FILE, JSON.stringify([]));
  }
  const data = fs.readFileSync(DATA_FILE);
  return JSON.parse(data);
}

// Função para salvar dados de estudantes no arquivo
function saveStudents(students) {
  fs.writeFileSync(DATA_FILE, JSON.stringify(students, null, 2));
}

// Rota para criar preferência de pagamento no Mercado Pago
app.post('/create_preference', async (req, res) => {
  try {
    const { name, whatsapp, course } = req.body;
    // Validar campos básicos
    if (!name || !whatsapp || !course) {
      return res.status(400).json({ error: 'Dados incompletos.' });
    }

    // Definir preço conforme o curso (exemplo)
    let price = 0;
    if (course === 'EEB') {
      price = 1500.00;  // Exemplo de valor em R$
    } else {
      price = 0;
    }

    // Criar um identificador único para referenciar o aluno (timestamp ou UUID)
    const reference = Date.now().toString();
    
    // Montar o objeto de preferência
    let preference = {
      items: [
        {
          title: `Inscrição no curso ${course}`,
          quantity: 1,
          currency_id: "BRL",
          unit_price: price
        }
      ],
      payer: {
        name: name
        // Poderíamos adicionar email/telefone aqui se quiser
      },
      external_reference: reference,  // nossa referência para o aluno
      back_urls: {
        success: "https://www.cedbrasilia.com.br/obrigado",
        failure: "https://www.cedbrasilia.com.br/obrigado",
        pending: "https://www.cedbrasilia.com.br/obrigado"
      }
    };

    // Cria a preferência no Mercado Pago
    const mpResponse = await mercadopago.preferences.create(preference);
    const initPoint = mpResponse.body.init_point; // URL de checkout:contentReference[oaicite:3]{index=3}:contentReference[oaicite:4]{index=4}

    // Salvar os dados do aluno associados a essa referência
    let students = loadStudents();
    students.push({
      reference: reference,
      name: name,
      whatsapp: whatsapp,
      course: course,
      status: 'pending'
    });
    saveStudents(students);

    // Retornar a URL de redirecionamento ao frontend
    res.json({ init_point: initPoint });
  } catch (error) {
    console.error("Erro ao criar preferência:", error);
    res.status(500).json({ error: 'Erro ao criar preferência.' });
  }
});

// Webhook do Mercado Pago
// Configure no seu dashboard do Mercado Pago a URL: https://api.cedbrasilia.com.br/mp-webhook
app.post('/mp-webhook', async (req, res) => {
  // Mercado Pago envia notificações de diversos tipos. Focaremos em pagamentos aprovados.
  // Eles podem vir com req.body.type = 'payment' ou 'payment.created', etc. O corpo pode variar.
  // Simplificaremos assumindo que veio o ID do pagamento.
  try {
    const data = req.body;
    console.log("Recebido webhook do Mercado Pago:", data);

    // Exemplo genérico: vamos buscar o pagamento se houver um payment id
    let paymentId = null;
    if (data.type === 'payment') {
      paymentId = data.data.id;
    } else if (data.type === 'payment.created') {
      paymentId = data.data.id;
    }

    if (paymentId) {
      // Buscar detalhes do pagamento
      const payment = await mercadopago.payment.get(paymentId);
      const paymentInfo = payment.body;
      if (paymentInfo.status === 'approved') {
        // Encontrar o aluno pela referência externa
        const externalRef = paymentInfo.external_reference;
        let students = loadStudents();
        let aluno = students.find(s => s.reference === externalRef);
        if (aluno && aluno.status === 'pending') {
          // Chama a matrícula (rota interna)
          // Podemos fazer por função direta:
          await matricularAluno(aluno);
          // Atualiza status
          aluno.status = 'completed';
          saveStudents(students);
          console.log(`Aluno ${aluno.name} matriculado com sucesso.`);
        }
      }
    }
    // Responde OK (Mercado Pago requer status 200 para não reenviar notificação)
    res.status(200).send('OK');
  } catch (err) {
    console.error("Erro no webhook:", err);
    res.status(500).send('Erro interno');
  }
});

// Função auxiliar para matricular aluno e enviar WhatsApp
async function matricularAluno(aluno) {
  // Exemplo: enviar mensagem no WhatsApp com os dados de acesso
  const mensagem = `Olá ${aluno.name}! Sua inscrição no curso ${aluno.course} foi confirmada. Em breve você receberá seus dados de acesso.`;
  try {
    const message = await client.messages.create({
      body: mensagem,
      from: twilioFrom,               // número do Twilio com WhatsApp
      to:   `whatsapp:+${aluno.whatsapp.replace(/\D/g,'')}`  // número do aluno em formato internacional
    });
    console.log("Mensagem enviada via WhatsApp SID:", message.sid);
  } catch (err) {
    console.error("Falha ao enviar WhatsApp:", err);
  }
}

// Rota pública para acionar matrícula (poderia ser acessada diretamente, se desejado)
app.post('/matricular', async (req, res) => {
  const { name, whatsapp, course } = req.body;
  if (!name || !whatsapp || !course) {
    return res.status(400).json({ error: 'Dados incompletos.' });
  }
  try {
    await matricularAluno({ name, whatsapp, course });
    res.json({ success: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Erro ao matricular aluno.' });
  }
});

// Inicia o servidor
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`API rodando na porta ${PORT}`);
});
