import { useCallback, useEffect, useState } from 'react';
import { Bot, Pause, Play, Trash2, RefreshCw, MessageCircle, ShieldCheck } from 'lucide-react';

type Props = { apiFetch: (path: string, init?: RequestInit) => Promise<Response>; role: string };
type Settings = { enabled: boolean; mode: 'approval' | 'autonomous'; interval_minutes: number; channel: string; paused: boolean };
type Conversation = { id: number; name?: string | null; email?: string | null; consent_to_followup: boolean; status: string; last_message_at: string };

async function payload<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || 'Não foi possível concluir a operação.');
  return data as T;
}

export default function ContactAIPanel({ apiFetch, role }: Props) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const [s, c] = await Promise.all([
        apiFetch('/contact-ai/settings'),
        apiFetch('/contact-ai/conversations'),
      ]);
      setSettings(await payload<Settings>(s));
      setConversations(await payload<Conversation[]>(c));
    } catch (e) { setError(e instanceof Error ? e.message : 'Erro ao carregar Contact AI.'); }
  }, [apiFetch]);

  useEffect(() => { void load(); }, [load]);

  async function save(next: Partial<Settings>) {
    if (!settings) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const response = await apiFetch('/contact-ai/settings', {
        method: 'PUT',
        body: JSON.stringify({
          enabled: next.enabled ?? settings.enabled,
          mode: next.mode ?? settings.mode,
          interval_minutes: 30,
        }),
      });
      const result = await payload<Settings>(response);
      setSettings({ ...settings, ...result, paused: false });
      setMessage('Configuração guardada.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Erro ao guardar.'); }
    finally { setBusy(false); }
  }

  async function action(path: string, method = 'POST') {
    setBusy(true); setError(''); setMessage('');
    try {
      const response = await apiFetch(path, { method });
      await payload(response);
      await load();
      setMessage('Operação concluída.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Erro na operação.'); }
    finally { setBusy(false); }
  }

  const admin = role === 'admin' || role === 'super_admin';
  return <section className="panel">
    <div className="panelhead">
      <div><h2><Bot size={19} /> Contact AI · Chat do website</h2><p>Assistente de contacto ligado ao Amazon Nova Lite e ao histórico RDS.</p></div>
      <button className="secondary" onClick={() => void load()} disabled={busy}><RefreshCw size={15}/> Atualizar</button>
    </div>
    {!admin && <div className="auth-error">A gestão do agente está disponível apenas para administradores.</div>}
    {error && <div className="auth-error">{error}</div>}
    {message && <p className="branding-message">{message}</p>}
    {settings && <>
      <div className="stats">
        <div className="stat"><small>Estado</small><strong>{settings.paused ? 'Pausado' : settings.enabled ? 'Ativo' : 'Desativado'}</strong></div>
        <div className="stat"><small>Execução</small><strong>30 min</strong></div>
        <div className="stat"><small>Canal</small><strong>Website</strong></div>
      </div>
      <div className="agent-input">
        <label>Modo de operação</label>
        <select value={settings.mode} disabled={!admin || busy} onChange={e => void save({ mode: e.target.value as Settings['mode'] })}>
          <option value="approval">Assistido — sugestões e aprovação humana</option>
          <option value="autonomous">Autónomo — respostas automáticas no chat ativo; seguimento em rascunho</option>
        </select>
        <small>O modo autónomo responde automaticamente durante uma conversa ativa. O ciclo periódico analisa conversas e prepara sugestões; não envia mensagens a visitantes offline.</small>
      </div>
      <div className="mode-switch">
        <button disabled={!admin || busy} onClick={() => void save({ enabled: !settings.enabled })}>{settings.enabled ? 'Desativar agente' : 'Ativar agente'}</button>
        <button className="secondary" disabled={!admin || busy || !settings.enabled} onClick={() => void action(settings.paused ? '/contact-ai/resume' : '/contact-ai/pause')}>{settings.paused ? <><Play size={15}/> Retomar</> : <><Pause size={15}/> Pausar</>}</button>
        <button className="secondary" disabled={!admin || busy} onClick={() => { if (window.confirm('Remover a configuração do Contact AI? O histórico de conversas será preservado.')) void action('/contact-ai/configuration', 'DELETE'); }}><Trash2 size={15}/> Remover configuração</button>
      </div>
    </>}
    <div className="panelhead"><div><h2><MessageCircle size={18}/> Conversas recentes</h2><p>O histórico fica guardado no PostgreSQL.</p></div></div>
    <div className="tablewrap"><table><thead><tr><th>Visitante</th><th>Email</th><th>Consentimento para seguimento</th><th>Última atividade</th></tr></thead>
      <tbody>{conversations.map(c => <tr key={c.id}><td>{c.name || 'Visitante'} <small>#{c.id}</small></td><td>{c.email || 'Não fornecido'}</td><td>{c.consent_to_followup ? 'Sim' : 'Não'}</td><td>{new Date(c.last_message_at).toLocaleString('pt-PT')}</td></tr>)}
      {!conversations.length && <tr><td colSpan={4} className="empty">Ainda não existem conversas.</td></tr>}</tbody></table></div>
    <p className="agent-note"><ShieldCheck size={15}/> O agente não inicia contactos externos nem envia mensagens para visitantes offline. Remover a configuração preserva as conversas e respetivos registos.</p>
  </section>;
}
