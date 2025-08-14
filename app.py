// index.js — Chatwoot <-> 360dialog <-> (Streamlit opcional)
// - Refleja mensajes OUTGOING (from_me) con texto humano de plantilla
// - Renderiza templates ({{1}}, {{2}}) a texto
// - Crea conversación por contact_inbox_id y hace polling antes del 1er mensaje
// - Dedupe con processedMessages

const express = require('express');
const bodyParser = require('body-parser');
const axios = require('axios');
const https = require('https');

const app = express();
app.use(bodyParser.json());

// ======== CONFIG (usa tus valores) ========
const CHATWOOT_API_TOKEN = '5ZSLaX4VCt4T2Z1aHRyPmTFb';
const CHATWOOT_ACCOUNT_ID = '1';
const CHATWOOT_INBOX_ID = '1';
const BASE_URL = 'https://srv904439.hstgr.cloud/api/v1/accounts';

const D360_API_URL = 'https://waba-v2.360dialog.io/messages';
const D360_API_KEY = '7Ll0YquMGVElHWxofGvhi5oFAK';

const N8N_WEBHOOK_URL = 'https://n8n.srv876216.hstgr.cloud/webhook-test/confirmar-tarimas';

const processedMessages = new Set();

// ======== Utils ========
function normalizarNumero(numero) {
  if (!numero || typeof numero !== 'string') return '';
  let n = numero.trim().replace(/\s|-/g, '');
  if (!n.startsWith('+')) n = `+${n}`;
  if (n.startsWith('+52') && !n.startsWith('+521')) {
    n = '+521' + n.slice(3);
  }
  return n;
}

async function findOrCreateContact(phone, name = 'Cliente WhatsApp') {
  const identifier = normalizarNumero(phone);
  const payload = {
    inbox_id: CHATWOOT_INBOX_ID,
    name,
    identifier,
    phone_number: identifier
  };
  try {
    const response = await axios.post(`${BASE_URL}/${CHATWOOT_ACCOUNT_ID}/contacts`, payload, {
      headers: { api_access_token: CHATWOOT_API_TOKEN }
    });
    return response.data.payload;
  } catch (err) {
    // ya existe -> buscar
    if (err.response?.data?.message?.includes('has already been taken')) {
      const getResp = await axios.get(
        `${BASE_URL}/${CHATWOOT_ACCOUNT_ID}/contacts/search?q=${encodeURIComponent(identifier)}`,
        { headers: { api_access_token: CHATWOOT_API_TOKEN } }
      );
      return getResp.data.payload?.[0];
    }
    console.error('❌ Contacto error:', err.response?.data || err.message);
    return null;
  }
}

async function getContactInboxInfo(contactId) {
  try {
    const res = await axios.get(`${BASE_URL}/${CHATWOOT_ACCOUNT_ID}/contacts/${contactId}`, {
      headers: { api_access_token: CHATWOOT_API_TOKEN }
    });
    const ci = res.data.payload?.contact_inboxes?.[0];
    if (!ci) return null;
    return { contact_inbox_id: ci.id, source_id: ci.source_id };
  } catch (err) {
    console.error('❌ No se pudo obtener contact_inbox_id:', err.response?.data || err.message);
    return null;
  }
}

async function getOrCreateConversationByInbox(contact_inbox_id) {
  try {
    // Crear conversación directamente con contact_inbox_id (Chatwoot recomienda)
    const newConv = await axios.post(
      `${BASE_URL}/${CHATWOOT_ACCOUNT_ID}/conversations`,
      { contact_inbox_id },
      { headers: { api_access_token: CHATWOOT_API_TOKEN } }
    );
    return newConv.data.id;
  } catch (err) {
    // si ya hay conversación abierta, Chatwoot a veces devuelve error; intenta listar
    try {
      const convs = await axios.get(
        `${BASE_URL}/${CHATWOOT_ACCOUNT_ID}/conversations`,
        { headers: { api_access_token: CHATWOOT_API_TOKEN } }
      );
      const found = (convs.data?.payload || []).find(c => c.meta?.sender?.contact_inbox_id === contact_inbox_id);
      if (found) return found.id;
    } catch (e) {}
    console.error(':x: Error creando/obteniendo conversación:', err.response?.data || err.message);
    return null;
  }
}

async function waitConversationReady(conversationId, attempts = 8, delayMs = 1000) {
  for (let i = 0; i < attempts; i++) {
    try {
      const check = await axios.get(
        `${BASE_URL}/${CHATWOOT_ACCOUNT_ID}/conversations/${conversationId}`,
        { headers: { api_access_token: CHATWOOT_API_TOKEN } }
      );
      if (check.status === 200) return true;
    } catch (e) {}
    await new Promise(r => setTimeout(r, delayMs));
  }
  return false;
}

async function sendToChatwoot(conversationId, type, content, outgoing = false) {
  const payload = {
    message_type: outgoing ? 'outgoing' : 'incoming',
    private: false
  };
  if (['image', 'document', 'audio', 'video'].includes(type)) {
    payload.attachments = [{ file_type: type, file_url: content }];
  } else {
    payload.content = content;
  }
  await axios.post(
    `${BASE_URL}/${CHATWOOT_ACCOUNT_ID}/conversations/${conversationId}/messages`,
    payload,
    { headers: { api_access_token: CHATWOOT_API_TOKEN } }
  );
}

// ======== Render de plantillas a texto humano ========
function renderTemplateToText(name, parameters = []) {
  const p1 = parameters?.[0]?.text || parameters?.[0]?.payload || '';
  const p2 = parameters?.[1]?.text || parameters?.[1]?.payload || '';

  if (name === 'mensaje_entre_semana_24_hrs') {
    return `Buen día, te saludamos de CHEP (Tarimas azules), es un gusto en saludarte.

Te escribo para confirmar que el día de mañana tenemos programada la recolección de tarimas en tu localidad: ${p1}.

¿Me podrías indicar cuántas tarimas tienes para entregar? Así podremos coordinar la unidad.`;
  }

  if (name === 'recordatorio_24_hrs') {
    return 'Buen día, estamos siguiendo tu solicitud, ¿Me ayudarías a confirmar si puedo validar la cantidad de tarimas que serán entregadas?';
  }

  // Genérico por si llega otra plantilla
  const extra =
    p1 && p2 ? ` Parámetros: ${p1} | ${p2}` :
    p1 ? ` Parámetro: ${p1}` : '';
  return `Plantilla ${name} enviada.${extra}`;
}

// ======== WEBHOOK 360dialog ========
app.post('/webhook', async (req, res) => {
  try {
    const entry = req.body.entry?.[0];
    const changes = entry?.changes?.[0]?.value;
    const rawPhone = `+${changes?.contacts?.[0]?.wa_id}`;
    const phone = normalizarNumero(rawPhone);
    const name = changes?.contacts?.[0]?.profile?.name;
    const msg = changes?.messages?.[0];

    if (!phone || !msg) return res.sendStatus(200);

    const messageId = msg.id;
    if (processedMessages.has(messageId)) return res.sendStatus(200);
    processedMessages.add(messageId);

    // Crear/obtener contacto + inbox + conversación
    const contact = await findOrCreateContact(phone, name);
    if (!contact?.id) return res.sendStatus(500);

    const inboxInfo = await getContactInboxInfo(contact.id);
    if (!inboxInfo?.contact_inbox_id) return res.sendStatus(500);

    let conversationId = await getOrCreateConversationByInbox(inboxInfo.contact_inbox_id);
    if (!conversationId) return res.sendStatus(500);

    await waitConversationReady(conversationId, 8, 1000);

    // ----- OUTGOING (from_me) -> que aparezca directo en Chatwoot -----
    if (msg.from_me) {
      if (msg.type === 'template') {
        const texto = renderTemplateToText(
          msg.template?.name,
          msg.template?.components?.[0]?.parameters || []
        );
        await sendToChatwoot(conversationId, 'text', texto, true);
      } else if (msg.type === 'text') {
        await sendToChatwoot(conversationId, 'text', msg.text?.body || '', true);
      } else if (['image', 'document', 'audio', 'video'].includes(msg.type)) {
        const url = msg[msg.type]?.link || '[media]';
        await sendToChatwoot(conversationId, msg.type, url, true);
      } else {
        await sendToChatwoot(conversationId, 'text', '[Mensaje enviado]', true);
      }
      return res.sendStatus(200);
    }

    // ----- INCOMING -----
    const type = msg.type;
    if (type === 'text') {
      await sendToChatwoot(conversationId, 'text', msg.text?.body || '');
    } else if (['image', 'document', 'audio', 'video'].includes(type)) {
      const url = msg[type]?.link || msg[type]?.body || msg[type]?.caption || '[media]';
      await sendToChatwoot(conversationId, type, url);
    } else if (type === 'location') {
      const loc = msg.location;
      const locStr = `📍 Ubicación: https://maps.google.com/?q=${loc.latitude},${loc.longitude}`;
      await sendToChatwoot(conversationId, 'text', locStr);
    } else if (type === 'template') {
      const texto = renderTemplateToText(
        msg.template?.name,
        msg.template?.components?.[0]?.parameters || []
      );
      await sendToChatwoot(conversationId, 'text', texto);
    } else {
      await sendToChatwoot(conversationId, 'text', '[Contenido no soportado]');
    }

    // Reenvío a n8n (opcional)
    try {
      await axios.post(
        N8N_WEBHOOK_URL,
        { phone, name, type, content: msg[type]?.body || msg[type]?.caption || msg[type]?.link || '' },
        { httpsAgent: new https.Agent({ rejectUnauthorized: false }) }
      );
    } catch (n8nErr) {
      console.warn('⚠️ n8n:', n8nErr.message);
    }

    res.sendStatus(200);
  } catch (err) {
    console.error(':x: Webhook error:', err.response?.data || err.message);
    res.sendStatus(500);
  }
});

// ======== CHATWOOT -> 360dialog (enviar desde bandeja) ========
app.post('/outbound', async (req, res) => {
  const msg = req.body;
  if (!msg?.message_type || msg.message_type !== 'outgoing') {
    return res.sendStatus(200);
  }

  const messageId = msg.id;
  if (processedMessages.has(messageId)) return res.sendStatus(200);
  processedMessages.add(messageId);

  const rawNumber = msg.conversation?.meta?.sender?.phone_number?.replace('+', '');
  const number = normalizarNumero(`+${rawNumber}`).replace('+', '');
  const content = msg.content;

  if (!number || !content) return res.sendStatus(200);

  try {
    await axios.post(D360_API_URL, {
      messaging_product: 'whatsapp',
      to: number,
      type: 'text',
      text: { body: content }
    }, {
      headers: { 'D360-API-KEY': D360_API_KEY, 'Content-Type': 'application/json' }
    });
    res.sendStatus(200);
  } catch (err) {
    console.error(':x: Error enviando a WhatsApp:', err.response?.data || err.message);
    res.sendStatus(500);
  }
});

// ======== (Opcional) Reflejo manual desde Streamlit ========
app.post('/send-chatwoot-message', async (req, res) => {
  try {
    const { phone, name, content } = req.body;
    const normalizedPhone = normalizarNumero((phone || '').trim());

    const contact = await findOrCreateContact(normalizedPhone, name || 'Cliente WhatsApp');
    if (!contact?.id) return res.status(500).send('Error al crear o recuperar el contacto');

    const inboxInfo = await getContactInboxInfo(contact.id);
    if (!inboxInfo?.contact_inbox_id) return res.status(500).send('No se pudo obtener contact_inbox_id');

    let conversationId = await getOrCreateConversationByInbox(inboxInfo.contact_inbox_id);
    if (!conversationId) return res.status(500).send('No se pudo crear conversación');

    await waitConversationReady(conversationId, 8, 1000);

    const msg = (content || '').trim();
    await sendToChatwoot(conversationId, 'text', msg, true);

    try {
      // Visibilidad en inbox
      await axios.put(
        `${BASE_URL}/${CHATWOOT_ACCOUNT_ID}/conversations/${conversationId}`,
        { status: 'open' },
        { headers: { api_access_token: CHATWOOT_API_TOKEN } }
      );
      await axios.post(
        `${BASE_URL}/${CHATWOOT_ACCOUNT_ID}/conversations/${conversationId}/assignments`,
        { assignee_id: null },
        { headers: { api_access_token: CHATWOOT_API_TOKEN } }
      );
    } catch (e) {}

    return res.sendStatus(200);
  } catch (err) {
    console.error(':x: Error general en /send-chatwoot-message:', err.message);
    res.status(500).send('Error interno al reflejar mensaje');
  }
});

const PORT = process.env.PORT || 10000;
app.listen(PORT, () => console.log(`🚀 Webhook corriendo en puerto ${PORT}`));
