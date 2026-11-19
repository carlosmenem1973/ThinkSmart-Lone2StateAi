(() => {
  if (window.__thinksmartContactWidget) return;
  window.__thinksmartContactWidget = true;
  const script = document.currentScript;
  const api = (script && script.dataset.api) || "/api/v1";
  const visitorKey = "thinksmart_contact_visitor";
  let visitorId = "";
  try {
    visitorId = localStorage.getItem(visitorKey) || (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));
    localStorage.setItem(visitorKey, visitorId);
  } catch (_) {
    visitorId = "visitor-" + Date.now() + "-" + Math.random().toString(16).slice(2);
  }

  const style = document.createElement("style");
  style.textContent = `
    .ts-chat-launch{position:fixed;right:24px;bottom:24px;z-index:2147483000;border:0;border-radius:999px;background:#2563eb;color:#fff;padding:14px 20px;font:600 14px system-ui;box-shadow:0 8px 28px #0003;cursor:pointer}
    .ts-chat{position:fixed;right:24px;bottom:86px;z-index:2147483000;width:min(360px,calc(100vw - 32px));height:480px;max-height:70vh;background:#fff;color:#172033;border:1px solid #dbe2ea;border-radius:16px;box-shadow:0 16px 50px #0003;display:none;overflow:hidden;font:14px system-ui}
    .ts-chat.open{display:flex;flex-direction:column}.ts-chat header{background:#1e3a8a;color:white;padding:14px;font-weight:700}.ts-chat .log{flex:1;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:8px}
    .ts-chat .bubble{padding:9px 11px;border-radius:12px;max-width:88%;white-space:pre-wrap;line-height:1.4}.ts-chat .bot{background:#eef2ff;align-self:flex-start}.ts-chat .visitor{background:#dbeafe;align-self:flex-end}
    .ts-chat form{padding:10px;border-top:1px solid #e5e7eb;display:grid;gap:8px}.ts-chat textarea{resize:none;min-height:54px;border:1px solid #cbd5e1;border-radius:8px;padding:9px;font:inherit}.ts-chat input{font:inherit}.ts-chat button{border:0;border-radius:8px;background:#2563eb;color:white;padding:10px;font-weight:600;cursor:pointer}.ts-chat button:disabled{opacity:.5}
    .ts-chat label{font-size:11px;color:#475569;display:flex;gap:6px;align-items:flex-start}.ts-chat .status{font-size:11px;color:#64748b}
  `;
  document.head.appendChild(style);
  const launch = document.createElement("button");
  launch.className = "ts-chat-launch"; launch.type = "button"; launch.textContent = "Fale connosco";
  const panel = document.createElement("section");
  panel.className = "ts-chat"; panel.setAttribute("aria-label", "Chat ThinkSmart AI");
  panel.innerHTML = '<header>ThinkSmart AI · Loft2 Real Estate</header><div class="log" aria-live="polite"><div class="bubble bot">Olá! Como podemos ajudar com o seu pedido imobiliário?</div></div><form><textarea maxlength="4000" required placeholder="Escreva a sua mensagem…"></textarea><label><input type="checkbox" class="consent"> Autorizo o seguimento deste pedido por email, se fornecer o meu contacto.</label><input class="email" type="email" maxlength="320" placeholder="Email (opcional)"><button type="submit">Enviar mensagem</button><div class="status">Não inclua dados sensíveis.</div></form>';
  document.body.append(launch, panel);
  launch.addEventListener("click", () => panel.classList.toggle("open"));
  const log = panel.querySelector(".log");
  const form = panel.querySelector("form");
  const input = panel.querySelector("textarea");
  const submit = panel.querySelector("button");
  const status = panel.querySelector(".status");
  function addBubble(text, role) {
    const item = document.createElement("div");
    item.className = "bubble " + role; item.textContent = text; log.appendChild(item); log.scrollTop = log.scrollHeight;
  }
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message) return;
    submit.disabled = true; status.textContent = "A enviar…";
    addBubble(message, "visitor"); input.value = "";
    try {
      const response = await fetch(api.replace(/\/$/, "") + "/contact-ai/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          visitor_id: visitorId, message,
          email: panel.querySelector(".email").value || null,
          consent_to_followup: panel.querySelector(".consent").checked
        })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Não foi possível enviar a mensagem.");
      addBubble(result.reply, "bot"); status.textContent = "Mensagem recebida.";
    } catch (error) {
      addBubble(error.message || "Erro de ligação. Tente novamente.", "bot");
      status.textContent = "Não foi possível contactar o serviço.";
    } finally { submit.disabled = false; }
  });
})();
