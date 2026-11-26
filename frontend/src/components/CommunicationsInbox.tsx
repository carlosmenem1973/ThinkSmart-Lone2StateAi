import { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Inbox, MessageCircle, Mail, RefreshCw, ShieldCheck } from 'lucide-react';

type Props = { apiFetch: (path: string, init?: RequestInit) => Promise<Response>; role: string };
type Thread = {
  id: number; contact_id: number | null; contact_name: string | null; contact_type: string | null;
  channel: 'whatsapp' | 'sms' | 'email'; subject: string | null; status: string;
  last_message_at: string; last_message: string | null; last_message_status: string | null;
};
type Message = {
  id: number; direction: string; actor_type: string; body: string; status: string;
  requires_approval: boolean; approved_by: number | null; approved_at: string | null;
  sent_at: string | null; created_at: string;
};
type PendingDraft = {
  message_id: number; thread_id: number; contact_id: number | null; contact_name: string | null;
  channel: string; subject: string | null; body: string; created_at: string; requires_approval: boolean;
};
type Tab = 'all' | 'whatsapp' | 'email' | 'approvals';

async function read<T>(response: Response): Promise<T> {
  const body = await response.json();
  if (!response.ok) {
    const detail = body?.detail ?? body?.message;
    throw new Error(typeof detail === 'string' ? detail : 'Não foi possível carregar as comunicações.');
  }
  return body as T;
}

function dateLabel(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('pt-PT');
}

export default function CommunicationsInbox({ apiFetch, role }: Props) {
  const [tab, setTab] = useState<Tab>('all');
  const [threads, setThreads] = useState<Thread[]>([]);
  const [pending, setPending] = useState<PendingDraft[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const admin = role === 'admin' || role === 'super_admin';

  const loadInbox = useCallback(async () => {
    setBusy(true); setError('');
    try {
      const rows = await read<Thread[]>(await apiFetch('/communications/inbox'));
      setThreads(rows);
      setSelected(current => current && rows.some(row => row.id === current) ? current : rows[0]?.id ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Não foi possível carregar a caixa de entrada.');
    } finally { setBusy(false); }
  }, [apiFetch]);

  const loadPending = useCallback(async () => {
    try { setPending(await read<PendingDraft[]>(await apiFetch('/communications/drafts/pending'))); }
    catch (e) { setError(e instanceof Error ? e.message : 'Não foi possível carregar as aprovações.'); }
  }, [apiFetch]);

  const loadMessages = useCallback(async (threadId: number) => {
    try { setMessages(await read<Message[]>(await apiFetch(`/communications/inbox/${threadId}/messages`))); }
    catch (e) { setMessages([]); setError(e instanceof Error ? e.message : 'Não foi possível carregar a conversa.'); }
  }, [apiFetch]);

  useEffect(() => { void loadInbox(); void loadPending(); }, [loadInbox, loadPending]);
  useEffect(() => {
    if (selected !== null) void loadMessages(selected);
    else setMessages([]);
  }, [selected, loadMessages]);

  const visibleThreads = useMemo(() => {
    if (tab === 'whatsapp') return threads.filter(thread => thread.channel === 'whatsapp');
    if (tab === 'email') return threads.filter(thread => thread.channel === 'email');
    if (tab === 'approvals') return threads.filter(thread => pending.some(draft => draft.thread_id === thread.id));
    return threads;
  }, [tab, threads, pending]);

  async function approve(messageId: number) {
    setBusy(true); setError(''); setNotice('');
    try {
      await read(await apiFetch(`/communications/drafts/${messageId}/approve`, { method: 'POST' }));
      setNotice('Aprovação registada. A mensagem não foi enviada.');
      await Promise.all([loadPending(), loadInbox()]);
      if (selected !== null) await loadMessages(selected);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Não foi possível aprovar o rascunho.');
    } finally { setBusy(false); }
  }

  const selectedThread = threads.find(thread => thread.id === selected) ?? null;
  return <section className="panel comm-panel">
    <div className="panelhead">
      <div><h2><Inbox size={19}/> Caixa de entrada omnichannel</h2><p>Conversas recebidas, WhatsApp, Email e respostas preparadas para aprovação.</p></div>
      <button className="secondary" onClick={() => { void loadInbox(); void loadPending(); }} disabled={busy}><RefreshCw size={15}/> Atualizar</button>
    </div>
    <div className="comm-tabs" role="tablist" aria-label="Filtros da caixa de entrada">
      <button className={tab === 'all' ? 'comm-tab active' : 'comm-tab'} onClick={() => setTab('all')}><Inbox size={15}/> Conversas</button>
      <button className={tab === 'whatsapp' ? 'comm-tab active' : 'comm-tab'} onClick={() => setTab('whatsapp')}><MessageCircle size={15}/> WhatsApp</button>
      <button className={tab === 'email' ? 'comm-tab active' : 'comm-tab'} onClick={() => setTab('email')}><Mail size={15}/> Email</button>
      <button className={tab === 'approvals' ? 'comm-tab active' : 'comm-tab'} onClick={() => { setTab('approvals'); void loadPending(); }}><ShieldCheck size={15}/> Aprovações <span>{pending.length}</span></button>
    </div>
    {error && <div className="auth-error">{error}</div>}
    {notice && <p className="branding-message">{notice}</p>}
    <div className="comm-layout">
      <div className="comm-thread-list">
        <div className="comm-list-heading">{tab === 'approvals' ? 'A aguardar aprovação' : 'Conversas recentes'} <small>{visibleThreads.length}</small></div>
        {visibleThreads.map(thread => (
          <button key={thread.id} className={selected === thread.id ? 'comm-thread selected' : 'comm-thread'} onClick={() => setSelected(thread.id)}>
            <span className="comm-thread-top"><b>{thread.contact_name || 'Contacto não identificado'}</b><small>{dateLabel(thread.last_message_at)}</small></span>
            <span className="comm-thread-meta">{thread.channel.toUpperCase()} · {thread.contact_type || 'Sem ligação CRM'}</span>
            <span className="comm-thread-preview">{thread.last_message || 'Sem conteúdo de mensagem'}</span>
            {pending.some(draft => draft.thread_id === thread.id) && <span className="comm-pending-label">Aprovação pendente</span>}
          </button>
        ))}
        {!visibleThreads.length && <p className="empty">{tab === 'approvals' ? 'Não existem rascunhos pendentes.' : 'Ainda não existem conversas neste canal.'}</p>}
      </div>
      <div className="comm-conversation">
        {selectedThread ? <>
          <div className="comm-conversation-head"><div><b>{selectedThread.contact_name || 'Contacto não identificado'}</b><small>{selectedThread.channel.toUpperCase()} · {selectedThread.contact_id ? `Contacto #${selectedThread.contact_id}` : 'Sem correspondência CRM'}</small></div><span className="pill">{selectedThread.status}</span></div>
          <div className="comm-messages">
            {messages.map(item => <article key={item.id} className={item.direction === 'outbound' ? 'comm-message outbound' : 'comm-message inbound'}>
              <div className="comm-message-meta"><b>{item.direction === 'outbound' ? 'Resposta preparada' : 'Mensagem recebida'}</b><span>{dateLabel(item.created_at)}</span></div>
              <p>{item.body}</p>
              <small>Estado: {item.status.replace(/_/g, ' ')}</small>
              {item.status === 'pending_approval' && admin && <button disabled={busy} onClick={() => void approve(item.id)}><CheckCircle2 size={15}/> Aprovar resposta</button>}
            </article>)}
            {!messages.length && <p className="empty">Seleciona uma conversa para consultar as mensagens.</p>}
          </div>
        </> : <p className="empty">Seleciona uma conversa na lista.</p>}
      </div>
    </div>
    <div className="comm-safety-note"><ShieldCheck size={15}/> A aprovação fica registada para auditoria. O envio externo continua desativado; aprovar não envia WhatsApp nem Email.</div>
    {!admin && <p className="comm-role-note">A aprovação de respostas está reservada a administradores. Podes consultar as conversas dentro das tuas permissões.</p>}
  </section>;
}
