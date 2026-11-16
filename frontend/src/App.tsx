import { FormEvent, useCallback, useEffect, useState } from 'react';
import { Building2, Users, Search, Mail, CalendarClock, ChartNoAxesCombined, RefreshCw, ShieldCheck, LogOut, LockKeyhole, UserPlus, Palette } from 'lucide-react';

const API = import.meta.env.VITE_API_URL || '/api/v1';
let refreshInFlight: Promise<string | null> | null = null;
type User = { id: number; email: string; full_name: string; role: 'admin' | 'seller'; territory?: string | null; must_change_password: boolean };
type AuthResult = { access_token: string; user: User };
type Branding = { product_name: string; customer_name: string; tagline: string; logo_url: string | null; primary_color: string; accent_color: string };

export default function App() {
  const [token, setToken] = useState('');
  const [user, setUser] = useState<User | null>(null);
  const [booting, setBooting] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState('');
  const [query, setQuery] = useState('Imóveis anunciados por proprietários particulares em Lisboa e arredores');
  const [leads, setLeads] = useState<any[]>([]);
  const [dash, setDash] = useState<any>(null);
  const [report, setReport] = useState('');
  const [busy, setBusy] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [passwordMessage, setPasswordMessage] = useState('');
  const [sellerName, setSellerName] = useState('');
  const [sellerEmail, setSellerEmail] = useState('');
  const [sellerTerritory, setSellerTerritory] = useState('');
  const [sellerResult, setSellerResult] = useState('');
  const [branding, setBranding] = useState<Branding>({ product_name: 'ThinkSmart AI', customer_name: 'Loft2 Real Estate', tagline: 'Real Estate Intelligence', logo_url: null, primary_color: '#2563EB', accent_color: '#16866C' });
  const [brandingMessage, setBrandingMessage] = useState('');
  const [brandingBusy, setBrandingBusy] = useState(false);

  const acceptAuth = (data: AuthResult) => { setToken(data.access_token); setUser(data.user); };

  const refreshSession = useCallback(async (): Promise<string | null> => {
    if (refreshInFlight) return refreshInFlight;
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${API}/auth/refresh`, { method: 'POST', credentials: 'include' });
        if (!response.ok) { setToken(''); setUser(null); return null; }
        const data = await response.json(); acceptAuth(data); return data.access_token as string;
      } catch { setToken(''); setUser(null); return null; }
    })();
    try { return await refreshInFlight; } finally { refreshInFlight = null; }
  }, []);

  useEffect(() => { refreshSession().finally(() => setBooting(false)); }, [refreshSession]);
  useEffect(() => { fetch(`${API}/settings/branding`).then(async r => { if (r.ok) setBranding(await r.json()); }).catch(console.error); }, []);

  const apiFetch = useCallback(async (path: string, init: RequestInit = {}) => {
    const makeRequest = (access: string) => {
      const headers = new Headers(init.headers);
      headers.set('Content-Type', 'application/json');
      if (access) headers.set('Authorization', `Bearer ${access}`);
      return fetch(`${API}${path}`, { ...init, credentials: 'include', headers });
    };
    let response = await makeRequest(token);
    if (response.status === 401 && path !== '/auth/refresh') {
      const refreshedToken = await refreshSession();
      if (refreshedToken) response = await makeRequest(refreshedToken);
    }
    return response;
  }, [token, refreshSession]);

  async function signIn(event: FormEvent) {
    event.preventDefault(); setLoginError('');
    try {
      const response = await fetch(`${API}/auth/login`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Não foi possível iniciar sessão');
      acceptAuth(data);
      setPassword('');
    } catch (error: any) { setLoginError(error.message || 'Erro de autenticação'); }
  }

  async function signOut() {
    await fetch(`${API}/auth/logout`, { method: 'POST', credentials: 'include' }).catch(() => undefined);
    setToken(''); setUser(null); setLeads([]); setDash(null);
  }

  const load = useCallback(async () => {
    if (!token) return;
    const [leadResponse, dashboardResponse] = await Promise.all([apiFetch('/leads'), apiFetch('/dashboard')]);
    if (leadResponse.ok) setLeads(await leadResponse.json());
    if (dashboardResponse.ok) setDash(await dashboardResponse.json());
  }, [token, apiFetch]);
  useEffect(() => { if (token) load().catch(console.error); }, [token, load]);
  useEffect(() => { document.title = `${branding.product_name} | ${branding.customer_name}`; document.documentElement.style.setProperty('--brand-primary', branding.primary_color); document.documentElement.style.setProperty('--brand-accent', branding.accent_color); }, [branding]);

  async function research() {
    setBusy(true);
    try {
      const response = await apiFetch(`/research?query=${encodeURIComponent(query)}`, { method: 'POST' });
      const data = await response.json(); setReport(data.text || data.detail || 'Sem resultados');
    } finally { setBusy(false); }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault(); setPasswordMessage('');
    const response = await apiFetch('/auth/change-password', { method: 'POST', body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) });
    const data = await response.json();
    if (!response.ok) { setPasswordMessage(data.detail || 'Não foi possível alterar a palavra-passe'); return; }
    setPasswordMessage('Palavra-passe alterada. Inicie sessão novamente.');
    setTimeout(signOut, 900);
  }

  async function saveBranding(event: FormEvent) {
    event.preventDefault(); setBrandingBusy(true); setBrandingMessage('');
    try {
      const response = await apiFetch('/settings/branding', { method: 'PUT', body: JSON.stringify(branding) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Não foi possível guardar a identidade visual');
      setBranding(data); setBrandingMessage('Identidade visual guardada. A alteração já está aplicada.');
    } catch (error: any) { setBrandingMessage(error.message || 'Erro ao guardar'); } finally { setBrandingBusy(false); }
  }

  async function createSeller(event: FormEvent) {
    event.preventDefault(); setSellerResult('');
    const response = await apiFetch('/auth/users', { method: 'POST', body: JSON.stringify({ email: sellerEmail, full_name: sellerName, territory: sellerTerritory || null, role: 'seller' }) });
    const data = await response.json();
    if (!response.ok) { setSellerResult(data.detail || 'Erro ao criar vendedor'); return; }
    setSellerResult(`Conta criada: ${data.user.email}\nPalavra-passe temporária: ${data.temporary_password}\nEntregue-a por canal seguro. O vendedor terá de a alterar no primeiro acesso.`);
    setSellerName(''); setSellerEmail(''); setSellerTerritory('');
  }

  if (booting) return <div className="auth-page"><div className="auth-card">A validar sessão…</div></div>;
  if (!user || !token) return <div className="auth-page"><form className="auth-card" onSubmit={signIn}><div className="auth-brand">{branding.logo_url ? <img src={branding.logo_url} alt="Company logo"/> : <Building2 size={34}/>}<div>{branding.product_name}<br/><b>{branding.customer_name}</b></div></div><small className="eyebrow">REAL ESTATE INTELLIGENCE · PORTUGAL</small><h1>Iniciar sessão</h1><p>Aceda ao espaço seguro da sua equipa imobiliária.</p><label>Email profissional</label><input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} placeholder="nome@empresa.pt"/><label>Palavra-passe</label><input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} placeholder="A sua palavra-passe"/>{loginError && <div className="auth-error">{loginError}</div>}<button className="auth-submit" type="submit"><LockKeyhole size={16}/> Entrar</button><small className="auth-note">Acesso individual · Registo de auditoria · Sessão protegida</small></form></div>;

  if (user.must_change_password) return <div className="auth-page"><form className="auth-card" onSubmit={changePassword}><div className="auth-brand"><LockKeyhole size={32}/><b>Alterar palavra-passe</b></div><h1>Primeiro acesso</h1><p>Por segurança, defina uma palavra-passe nova antes de continuar. Use pelo menos 12 caracteres.</p><label>Palavra-passe temporária / atual</label><input type="password" required value={currentPassword} onChange={e => setCurrentPassword(e.target.value)}/><label>Nova palavra-passe</label><input type="password" minLength={12} required value={newPassword} onChange={e => setNewPassword(e.target.value)}/>{passwordMessage && <div className="auth-error">{passwordMessage}</div>}<button className="auth-submit" type="submit">Guardar nova palavra-passe</button></form></div>;

  return <div className="shell"><aside><div className="brand">{branding.logo_url ? <img src={branding.logo_url} alt="Company logo"/> : <Building2/>}<span>{branding.product_name}<br/><b>{branding.customer_name}</b></span></div><nav><a className="active"><ChartNoAxesCombined/> Dashboard</a><a><Users/> Leads & Sellers</a><a><Search/> AI Discovery</a><a><Mail/> Email Intelligence</a><a><CalendarClock/> Follow-ups</a><a><ShieldCheck/> Approvals & GDPR</a></nav><div className="sidefoot">Portugal · Europe/Lisbon<br/>AI-assisted CRM</div></aside><main><header><div><small>{branding.tagline.toUpperCase()}</small><h1>Sales overview</h1><p>Descobrir oportunidades. Qualificar leads. Ajudar os vendedores.</p></div><div className="user-menu"><div><b>{user.full_name}</b><small>{user.role === 'admin' ? 'Administrador' : 'Vendedor'} · {user.territory || user.email}</small></div><button className="secondary" onClick={signOut}><LogOut size={15}/> Sair</button></div></header><section className="stats"><Stat title="Total leads" value={dash?.total_leads??'—'} icon={<Users/>}/><Stat title="New leads" value={dash?.by_status?.new??'—'} icon={<Search/>}/><Stat title="Pending follow-ups" value={dash?.pending_followups??'—'} icon={<CalendarClock/>}/><Stat title="Drafts to review" value={dash?.pending_drafts??'—'} icon={<Mail/>}/></section><section className="panel"><div className="panelhead"><div><h2>AI property discovery</h2><p>Pesquisar oportunidades em fontes públicas e permitidas.</p></div><span className="pill">OpenAI web search</span></div><div className="searchrow"><input value={query} onChange={e=>setQuery(e.target.value)}/><button disabled={busy} onClick={research}>{busy?'A pesquisar…':<><Search size={16}/> Research</>}</button></div>{report&&<pre className="report">{report}</pre>}</section>{user.role === 'admin' && <section className="panel branding-panel"><div className="panelhead"><div><h2><Palette size={18}/> Identidade visual</h2><p>Altere o nome do produto, o cliente, o logótipo e as cores sem novo deploy.</p></div></div><form className="branding-form" onSubmit={saveBranding}><label>Nome do produto<input required maxLength={100} value={branding.product_name} onChange={e=>setBranding({...branding, product_name:e.target.value})}/></label><label>Nome do cliente<input required maxLength={160} value={branding.customer_name} onChange={e=>setBranding({...branding, customer_name:e.target.value})}/></label><label>Subtítulo<input maxLength={240} value={branding.tagline} onChange={e=>setBranding({...branding, tagline:e.target.value})}/></label><label>URL do logótipo (HTTPS ou caminho /)<input value={branding.logo_url || ''} onChange={e=>setBranding({...branding, logo_url:e.target.value || null})} placeholder="https://.../logo.svg"/></label><label>Cor principal<div className="color-field"><input type="color" value={branding.primary_color} onChange={e=>setBranding({...branding, primary_color:e.target.value})}/><code>{branding.primary_color}</code></div></label><label>Cor de destaque<div className="color-field"><input type="color" value={branding.accent_color} onChange={e=>setBranding({...branding, accent_color:e.target.value})}/><code>{branding.accent_color}</code></div></label><div className="branding-preview" style={{borderColor:branding.primary_color}}><b style={{color:branding.primary_color}}>{branding.product_name}</b><span>{branding.customer_name}</span><small>{branding.tagline}</small></div><button type="submit" disabled={brandingBusy}>{brandingBusy?'A guardar…':'Guardar identidade visual'}</button>{brandingMessage && <p className="branding-message">{brandingMessage}</p>}</form></section>}{user.role === 'admin' && <section className="panel"><div className="panelhead"><div><h2>Contas da equipa</h2><p>Criar acessos individuais para os cinco vendedores.</p></div><UserPlus/></div><form className="seller-form" onSubmit={createSeller}><input required placeholder="Nome completo" value={sellerName} onChange={e=>setSellerName(e.target.value)}/><input required type="email" placeholder="Email profissional" value={sellerEmail} onChange={e=>setSellerEmail(e.target.value)}/><input placeholder="Território (ex.: Lisboa)" value={sellerTerritory} onChange={e=>setSellerTerritory(e.target.value)}/><button type="submit">Criar vendedor</button></form>{sellerResult && <pre className="report">{sellerResult}</pre>}</section>}<section className="panel"><div className="panelhead"><div><h2>Latest leads</h2><p>Oportunidades identificadas e registadas.</p></div><button className="secondary" onClick={load}><RefreshCw size={15}/> Refresh</button></div><div className="tablewrap"><table><thead><tr><th>Opportunity</th><th>Location</th><th>Score</th><th>Status</th><th>Owner contact</th></tr></thead><tbody>{leads.map(l=><tr key={l.id}><td><b>{l.title}</b><small>{l.source_name||'Source pending'}</small></td><td>{l.municipality||l.address||'—'}</td><td><span className="score">{l.score}/100</span></td><td><span className="status">{l.status}</span></td><td>{l.owner_name||'Not verified'}<small>{l.owner_email||'No email'}</small></td></tr>)}{!leads.length&&<tr><td colSpan={5} className="empty">Ainda não existem leads atribuídos a esta conta.</td></tr>}</tbody></table></div></section><footer>{branding.product_name} | {branding.customer_name} · Human approval required · Dados pessoais tratados com controlo de acesso</footer></main></div>;
}
function Stat({title,value,icon}:{title:string,value:any,icon:any}){return <div className="stat"><div className="staticon">{icon}</div><small>{title}</small><strong>{value}</strong></div>}
