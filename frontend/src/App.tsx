import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import ContactAIPanel from './components/ContactAIPanel';
import {
  fetchAuthSession,
  signIn as cognitoSignIn,
  confirmSignIn as cognitoConfirmSignIn,
  resetPassword as cognitoResetPassword,
  confirmResetPassword as cognitoConfirmResetPassword,
  signOut as cognitoSignOut,
  updatePassword,
} from 'aws-amplify/auth';
import {
  Building2, Users, Search, Mail, CalendarClock, ChartNoAxesCombined,
  RefreshCw, ShieldCheck, LogOut, LockKeyhole, UserPlus, Palette,
  Bot, Globe2, Database, Play, CheckCircle2, LoaderCircle, MapPin, MessageCircle,
  TrendingUp, UserSearch, ClipboardCheck, Menu, X,
} from 'lucide-react';

function normaliseApiBase(configured?: string): string {
  const value = (configured || '/api/v1').trim().replace(/\/+$/, '');
  if (!value) return '/api/v1';
  if (/\/api\/v1$/i.test(value)) return value;
  if (/\/api$/i.test(value)) return `${value}/v1`;
  return `${value}/api/v1`;
}

const API = normaliseApiBase(import.meta.env.VITE_API_URL);

type User = {
  id: number;
  email: string;
  full_name: string;
  role: 'super_admin' | 'admin' | 'manager' | 'seller' | 'viewer';
  territory?: string | null;
  must_change_password: boolean;
};

type Branding = {
  product_name: string;
  customer_name: string;
  tagline: string;
  logo_url: string | null;
  primary_color: string;
  accent_color: string;
};

type Lead = {
  id: number | string;
  title?: string;
  source_name?: string;
  municipality?: string;
  address?: string;
  score?: number;
  status?: string;
  owner_name?: string;
  owner_email?: string;
};

type Dashboard = {
  total_leads?: number;
  by_status?: { new?: number };
  pending_followups?: number;
  pending_drafts?: number;
};

type SearchMode = 'web' | 'internal';

type AiStatus = {
  bedrock_configured: boolean;
  internal_search_enabled: boolean;
  internal_search_reason?: string | null;
  web_search_enabled: boolean;
  web_search_reason?: string | null;
  agents_enabled: boolean;
  agents_reason?: string | null;
};
type Section = 'dashboard' | 'procura' | 'agents' | 'contact-ai' | 'team' | 'settings';

type Agent = {
  id: string;
  name: string;
  description: string;
  purpose: string;
  icon: typeof Search;
};

const AGENTS: Agent[] = [
  {
    id: 'property-discovery',
    name: 'Agente de Descoberta',
    description: 'Descobre oportunidades imobiliárias em fontes públicas autorizadas.',
    purpose: 'Descoberta de imóveis',
    icon: Search,
  },
  {
    id: 'market-analyst',
    name: 'Agente de Mercado',
    description: 'Analisa preços, zonas, tendências e posicionamento.',
    purpose: 'Análise de mercado',
    icon: TrendingUp,
  },
  {
    id: 'lead-qualifier',
    name: 'Agente de Qualificação',
    description: 'Organiza e classifica oportunidades para a equipa comercial.',
    purpose: 'Qualificação de leads',
    icon: ClipboardCheck,
  },
  {
    id: 'owner-intelligence',
    name: 'Agente de Informação Pública',
    description: 'Analisa evidência pública fornecida sobre anúncios, sem inferir a identidade de proprietários.',
    purpose: 'Análise de anúncios',
    icon: UserSearch,
  },
  {
    id: 'email-intelligence',
    name: 'Agente de Email',
    description: 'Ajuda a organizar pedidos, mensagens e potenciais oportunidades.',
    purpose: 'Inteligência de email',
    icon: Mail,
  },
  {
    id: 'follow-up-assistant',
    name: 'Agente de Seguimento',
    description: 'Prepara próximos passos e sugestões de acompanhamento.',
    purpose: 'Seguimento comercial',
    icon: CalendarClock,
  },
];

const DEFAULT_BRANDING: Branding = {
  product_name: 'ThinkSmart AI',
  customer_name: 'Loft2 Real Estate',
  tagline: 'Real Estate Intelligence',
  logo_url: null,
  primary_color: '#2563EB',
  accent_color: '#16866C',
};

async function readResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    if (response.status === 404) {
      throw new Error(`A API respondeu 404. URL base utilizada: ${API}. Confirme se o backend foi atualizado e se VITE_API_URL aponta para a API, não para o alojamento estático.`);
    }
    throw new Error(`Resposta inesperada do servidor (${response.status}). Confirme VITE_API_URL e o backend.`);
  }
  const payload = await response.json();
  if (!response.ok) {
    const detail = payload?.detail || payload?.message;
    if (response.status === 404 && (!detail || detail === 'Not Found')) {
      throw new Error(`A rota não existe na versão da API em execução (${API}). O backend precisa de ser publicado com as rotas de Procura IA e Agentes IA.`);
    }
    throw new Error(detail || `Erro HTTP ${response.status}`);
  }
  return payload as T;
}

export default function App() {
  const [token, setToken] = useState('');
  const [user, setUser] = useState<User | null>(null);
  const [booting, setBooting] = useState(true);
  const [hasCognitoSession, setHasCognitoSession] = useState(false);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState('');
  const [needsNewPassword, setNeedsNewPassword] = useState(false);
  const [challengePassword, setChallengePassword] = useState('');
  const [resetMode, setResetMode] = useState(false);
  const [resetCode, setResetCode] = useState('');
  const [resetNewPassword, setResetNewPassword] = useState('');
  const [authBusy, setAuthBusy] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [passwordMessage, setPasswordMessage] = useState('');

  const [section, setSection] = useState<Section>('dashboard');
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const [leads, setLeads] = useState<Lead[]>([]);
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [dashboardBusy, setDashboardBusy] = useState(false);
  const [dashboardError, setDashboardError] = useState('');

  const [searchMode, setSearchMode] = useState<SearchMode>('web');
  const [query, setQuery] = useState('Imóveis anunciados por proprietários particulares em Lisboa e arredores');
  const [report, setReport] = useState('');
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [aiStatusError, setAiStatusError] = useState('');

  const [agentBusy, setAgentBusy] = useState<string | null>(null);
  const [agentResults, setAgentResults] = useState<Record<string, string>>({});
  const [agentError, setAgentError] = useState('');
  const [agentInput, setAgentInput] = useState('');

  const [sellerName, setSellerName] = useState('');
  const [sellerEmail, setSellerEmail] = useState('');
  const [sellerTerritory, setSellerTerritory] = useState('');
  const [sellerResult, setSellerResult] = useState('');

  const [branding, setBranding] = useState<Branding>(DEFAULT_BRANDING);
  const [brandingMessage, setBrandingMessage] = useState('');
  const [brandingBusy, setBrandingBusy] = useState(false);

  const apiFetch = useCallback(async (path: string, init: RequestInit = {}) => {
    const request = async (forceRefresh: boolean) => {
      const session = await fetchAuthSession({ forceRefresh });
      const access = session.tokens?.accessToken?.toString();
      if (!access) throw new Error('Sessão expirada. Inicie sessão novamente.');

      const headers = new Headers(init.headers);
      headers.set('Authorization', `Bearer ${access}`);
      if (init.body && !headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
      }

      return fetch(`${API}${path}`, { ...init, headers });
    };

    let response = await request(false);
    if (response.status === 401) response = await request(true);

    if (response.status === 401) {
      try { await cognitoSignOut(); } finally {
        setToken('');
        setUser(null);
        setLeads([]);
        setDash(null);
      }
    }
    return response;
  }, []);

  const loadCognitoUser = useCallback(async () => {
    const session = await fetchAuthSession({ forceRefresh: true });
    const access = session.tokens?.accessToken?.toString();
    if (!access) {
      setHasCognitoSession(false);
      throw new Error('Sessão Cognito não encontrada.');
    }
    setHasCognitoSession(true);

    const response = await fetch(`${API}/auth/me`, {
      headers: { Authorization: `Bearer ${access}` },
    });
    const profile = await readResponse<User>(response);
    setToken(access);
    setUser(profile);
  }, []);

  const loadDashboard = useCallback(async () => {
    if (!user) return;
    setDashboardBusy(true);
    setDashboardError('');
    try {
      const [leadsResponse, dashboardResponse] = await Promise.all([
        apiFetch('/leads'),
        apiFetch('/dashboard'),
      ]);
      const [leadsData, dashboardData] = await Promise.all([
        readResponse<Lead[] | { items?: Lead[] }>(leadsResponse),
        readResponse<Dashboard>(dashboardResponse),
      ]);
      setLeads(Array.isArray(leadsData) ? leadsData : (leadsData.items || []));
      setDash(dashboardData);
    } catch (error) {
      setDashboardError(error instanceof Error ? error.message : 'Não foi possível carregar o dashboard.');
    } finally {
      setDashboardBusy(false);
    }
  }, [apiFetch, user]);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const session = await fetchAuthSession();
        const access = session.tokens?.accessToken?.toString();

        if (!access) {
          if (active) setHasCognitoSession(false);
          return;
        }

        if (active) setHasCognitoSession(true);

        // A sessão Cognito pode estar válida mesmo que a API esteja temporariamente
        // indisponível. Não terminar a sessão automaticamente por erros HTTP/API.
        const response = await fetch(`${API}/auth/me`, {
          headers: { Authorization: `Bearer ${access}` },
        });
        const profile = await readResponse<User>(response);

        if (active) {
          setToken(access);
          setUser(profile);
          setLoginError('');
        }
      } catch (error) {
        console.error('Session/profile initialization failed:', error);
        if (active) {
          setLoginError(
            error instanceof Error
              ? `A sessão Cognito existe ou não pôde ser validada pela API: ${error.message}`
              : 'Não foi possível validar a sessão. Verifique a API.'
          );
        }
      } finally {
        if (active) setBooting(false);
      }
    })();

    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    fetch(`${API}/settings/branding`)
      .then(async response => {
        if (!response.ok) return null;
        return response.json();
      })
      .then(data => { if (active && data) setBranding({ ...DEFAULT_BRANDING, ...data }); })
      .catch(error => console.warn('Branding could not be loaded:', error));

    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!user) {
      setAiStatus(null);
      setAiStatusError('');
      return;
    }
    let active = true;
    apiFetch('/ai/status')
      .then(response => readResponse<AiStatus>(response))
      .then(status => { if (active) setAiStatus(status); })
      .catch(error => {
        if (active) setAiStatusError(error instanceof Error ? error.message : 'Não foi possível verificar a configuração de IA.');
      });
    return () => { active = false; };
  }, [apiFetch, user]);

  useEffect(() => {
    document.title = `${branding.product_name} | ${branding.customer_name}`;
    document.documentElement.style.setProperty('--brand-primary', branding.primary_color);
    document.documentElement.style.setProperty('--brand-accent', branding.accent_color);
  }, [branding]);

  useEffect(() => {
    if (user && token) void loadDashboard();
  }, [user, token, loadDashboard]);

  const navItems = useMemo(() => [
    { id: 'dashboard' as const, label: 'Dashboard', icon: ChartNoAxesCombined },
    { id: 'procura' as const, label: 'Procura IA', icon: Search },
    { id: 'agents' as const, label: 'Agentes IA', icon: Bot },
    { id: 'contact-ai' as const, label: 'Contact AI', icon: MessageCircle },
    { id: 'team' as const, label: 'Equipa', icon: Users },
    { id: 'settings' as const, label: 'Definições', icon: ShieldCheck },
  ], []);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setLoginError('');
    setAuthBusy(true);

    try {
      // Evita chamar Cognito signIn() quando já existe uma sessão ativa.
      const currentSession = await fetchAuthSession();
      const currentAccessToken = currentSession.tokens?.accessToken?.toString();

      if (currentAccessToken) {
        setHasCognitoSession(true);
        await loadCognitoUser();
        setPassword('');
        return;
      }

      const result = await cognitoSignIn({
        username: email.trim(),
        password,
      });

      if (!result.isSignedIn) {
        if (result.nextStep.signInStep === 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED') {
          setNeedsNewPassword(true);
          setLoginError('Defina uma nova palavra-passe para concluir o primeiro acesso.');
          return;
        }
        setLoginError(`A autenticação exige uma etapa adicional: ${result.nextStep.signInStep}.`);
        return;
      }

      setHasCognitoSession(true);
      await loadCognitoUser();
      setPassword('');
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : 'Não foi possível iniciar sessão.');
    } finally {
      setAuthBusy(false);
    }
  }

  async function completeFirstLogin(event: FormEvent) {
    event.preventDefault();
    setLoginError('');
    setAuthBusy(true);
    try {
      const result = await cognitoConfirmSignIn({ challengeResponse: challengePassword });
      if (!result.isSignedIn) {
        setLoginError(`Cognito exige outra etapa: ${result.nextStep.signInStep}`);
        return;
      }
      setNeedsNewPassword(false);
      setChallengePassword('');
      setPassword('');
      await loadCognitoUser();
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : 'Não foi possível concluir o primeiro acesso.');
    } finally {
      setAuthBusy(false);
    }
  }

  async function startPasswordReset() {
    setLoginError('');
    if (!email.trim()) {
      setLoginError('Introduza primeiro o seu email profissional.');
      return;
    }
    setAuthBusy(true);
    try {
      const result = await cognitoResetPassword({ username: email.trim() });
      if (result.nextStep.resetPasswordStep === 'CONFIRM_RESET_PASSWORD_WITH_CODE') {
        setResetMode(true);
        setResetCode('');
        setResetNewPassword('');
        setLoginError('Enviámos um código de recuperação para o email associado à conta.');
      } else {
        setLoginError('O Cognito concluiu o processo de recuperação. Tente iniciar sessão.');
      }
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : 'Não foi possível iniciar a recuperação da palavra-passe.');
    } finally {
      setAuthBusy(false);
    }
  }

  async function finishPasswordReset(event: FormEvent) {
    event.preventDefault();
    setLoginError('');
    setAuthBusy(true);
    try {
      await cognitoConfirmResetPassword({
        username: email.trim(),
        confirmationCode: resetCode.trim(),
        newPassword: resetNewPassword,
      });
      setResetMode(false);
      setResetCode('');
      setResetNewPassword('');
      setPassword('');
      setLoginError('Palavra-passe redefinida. Já pode iniciar sessão com a nova palavra-passe.');
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : 'Não foi possível confirmar a recuperação da palavra-passe.');
    } finally {
      setAuthBusy(false);
    }
  }

  async function signOut() {
    try {
      await cognitoSignOut();
    } finally {
      setToken('');
      setUser(null);
      setHasCognitoSession(false);
      setLeads([]);
      setDash(null);
      setSection('dashboard');
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    setPasswordMessage('');
    try {
      await updatePassword({ oldPassword: currentPassword, newPassword });
      setPasswordMessage('Palavra-passe alterada com sucesso.');
      setCurrentPassword('');
      setNewPassword('');
      const refreshed = await loadCognitoUser();
      void refreshed;
    } catch (error) {
      setPasswordMessage(error instanceof Error ? error.message : 'Não foi possível alterar a palavra-passe.');
    }
  }

  async function runSearch(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) {
      setSearchError('Introduza uma pesquisa.');
      return;
    }

    setSearchBusy(true);
    setSearchError('');
    setReport('');
    try {
      // API contract: POST /research?query=...&source=web|internal
      const params = new URLSearchParams({ query: query.trim(), source: searchMode });
      const response = await apiFetch(`/research?${params.toString()}`, { method: 'POST' });
      const data = await readResponse<{ text?: string; detail?: string; items?: unknown[] }>(response);
      setReport(data.text || data.detail || JSON.stringify(data.items || data, null, 2));
    } catch (error) {
      setSearchError(error instanceof Error ? error.message : 'A pesquisa não foi concluída.');
    } finally {
      setSearchBusy(false);
    }
  }

  async function runAgent(agent: Agent) {
    if (!['property-discovery', 'market-analyst'].includes(agent.id) && !agentInput.trim()) {
      setAgentError('Introduza o contexto ou os dados que o agente deve analisar.');
      return;
    }
    setAgentBusy(agent.id);
    setAgentError('');
    try {
      // API contract: POST /agents/{agent_id}/run
      const response = await apiFetch(`/agents/${encodeURIComponent(agent.id)}/run`, {
        method: 'POST',
        body: JSON.stringify({ input: agentInput.trim() }),
      });
      const data = await readResponse<{ text?: string; result?: unknown; message?: string }>(response);
      const result = data.text || data.message || (
        typeof data.result === 'string' ? data.result : JSON.stringify(data.result ?? data, null, 2)
      );
      setAgentResults(previous => ({ ...previous, [agent.id]: result }));
    } catch (error) {
      setAgentError(error instanceof Error ? error.message : `Não foi possível executar ${agent.name}.`);
    } finally {
      setAgentBusy(null);
    }
  }

  async function saveBranding(event: FormEvent) {
    event.preventDefault();
    setBrandingBusy(true);
    setBrandingMessage('');
    try {
      const response = await apiFetch('/settings/branding', {
        method: 'PUT',
        body: JSON.stringify(branding),
      });
      const data = await readResponse<Branding>(response);
      setBranding({ ...DEFAULT_BRANDING, ...data });
      setBrandingMessage('Identidade visual guardada.');
    } catch (error) {
      setBrandingMessage(error instanceof Error ? error.message : 'Não foi possível guardar a identidade visual.');
    } finally {
      setBrandingBusy(false);
    }
  }

  async function createSeller(event: FormEvent) {
    event.preventDefault();
    setSellerResult('');
    try {
      const response = await apiFetch('/auth/users', {
        method: 'POST',
        body: JSON.stringify({
          email: sellerEmail.trim(),
          full_name: sellerName.trim(),
          territory: sellerTerritory.trim() || null,
          role: 'seller',
        }),
      });
      const data = await readResponse<{ message?: string; user?: { email?: string } }>(response);
      setSellerResult(data.message || `Convite enviado para ${data.user?.email || sellerEmail}.`);
      setSellerName('');
      setSellerEmail('');
      setSellerTerritory('');
    } catch (error) {
      setSellerResult(error instanceof Error ? error.message : 'Não foi possível criar o vendedor.');
    }
  }

  function navigate(next: Section) {
    setSection(next);
    setMobileNavOpen(false);
  }

  if (booting) {
    return <div className="auth-page"><div className="auth-card">A validar sessão…</div></div>;
  }

  if (needsNewPassword) {
    return (
      <div className="auth-page">
        <form className="auth-card" onSubmit={completeFirstLogin}>
          <div className="auth-brand"><Building2 size={34} /><b>ThinkSmart AI</b></div>
          <h1>Primeiro acesso</h1>
          <p>Defina uma nova palavra-passe para concluir o convite da sua conta.</p>
          <label>Nova palavra-passe</label>
          <input type="password" minLength={12} required autoComplete="new-password"
            value={challengePassword} onChange={event => setChallengePassword(event.target.value)} />
          {loginError && <div className="auth-error">{loginError}</div>}
          <button className="auth-submit" type="submit" disabled={authBusy}>
            {authBusy ? 'A guardar…' : 'Guardar palavra-passe'}
          </button>
        </form>
      </div>
    );
  }

  if (resetMode) {
    return (
      <div className="auth-page">
        <form className="auth-card" onSubmit={finishPasswordReset}>
          <div className="auth-brand"><Building2 size={34} /><b>ThinkSmart AI</b></div>
          <h1>Recuperar palavra-passe</h1>
          <p>Introduza o código enviado para o seu email e escolha uma nova palavra-passe.</p>
          <label>Email profissional</label>
          <input type="email" value={email} readOnly />
          <label>Código de verificação</label>
          <input value={resetCode} onChange={event => setResetCode(event.target.value)}
            autoComplete="one-time-code" required />
          <label>Nova palavra-passe</label>
          <input type="password" minLength={12} required autoComplete="new-password"
            value={resetNewPassword} onChange={event => setResetNewPassword(event.target.value)} />
          {loginError && <div className="auth-error">{loginError}</div>}
          <button className="auth-submit" type="submit" disabled={authBusy}>
            {authBusy ? 'A confirmar…' : 'Redefinir palavra-passe'}
          </button>
          <button className="secondary" type="button" onClick={() => { setResetMode(false); setLoginError(''); }}>
            Voltar ao login
          </button>
        </form>
      </div>
    );
  }

  if (!user || !token) {
    return (
      <div className="auth-page">
        <form className="auth-card" onSubmit={signIn}>
          <div className="auth-brand">
            {branding.logo_url ? <img src={branding.logo_url} alt="Logótipo" /> : <Building2 size={34} />}
            <div>{branding.product_name}<br /><b>{branding.customer_name}</b></div>
          </div>
          <small className="eyebrow">REAL ESTATE INTELLIGENCE · PORTUGAL</small>
          <h1>Iniciar sessão</h1>
          <p>Aceda ao espaço seguro da sua equipa imobiliária.</p>
          <label>Email profissional</label>
          <input type="email" autoComplete="username" required value={email}
            onChange={event => setEmail(event.target.value)} placeholder="nome@empresa.pt" />
          <label>Palavra-passe</label>
          <input type="password" autoComplete="current-password" required value={password}
            onChange={event => setPassword(event.target.value)} placeholder="A sua palavra-passe" />
          {loginError && <div className="auth-error">{loginError}</div>}
          <button className="auth-submit" type="submit" disabled={authBusy}>
            {authBusy ? <><LoaderCircle className="spin" size={16} /> A autenticar…</> : <><LockKeyhole size={16} /> Entrar</>}
          </button>
          <button className="secondary" type="button" disabled={authBusy} onClick={() => void startPasswordReset()}>
            Esqueci-me da palavra-passe
          </button>
          {hasCognitoSession && (
            <button
              className="secondary"
              type="button"
              onClick={async () => {
                try {
                  await cognitoSignOut();
                } finally {
                  setHasCognitoSession(false);
                  setToken('');
                  setUser(null);
                  setLoginError('Sessão terminada. Pode iniciar sessão com outra conta.');
                }
              }}
            >
              Terminar sessão Cognito e usar outra conta
            </button>
          )}
          <small className="auth-note">Acesso individual · Sessão protegida</small>
        </form>
      </div>
    );
  }

  if (user.must_change_password) {
    return (
      <div className="auth-page">
        <form className="auth-card" onSubmit={changePassword}>
          <div className="auth-brand"><LockKeyhole size={32} /><b>Alterar palavra-passe</b></div>
          <h1>Primeiro acesso</h1>
          <p>Por segurança, defina uma nova palavra-passe antes de continuar.</p>
          <label>Palavra-passe atual</label>
          <input type="password" required autoComplete="current-password" value={currentPassword}
            onChange={event => setCurrentPassword(event.target.value)} />
          <label>Nova palavra-passe</label>
          <input type="password" minLength={12} required autoComplete="new-password" value={newPassword}
            onChange={event => setNewPassword(event.target.value)} />
          {passwordMessage && <div className="auth-error">{passwordMessage}</div>}
          <button className="auth-submit" type="submit">Guardar nova palavra-passe</button>
        </form>
      </div>
    );
  }

  return (
    <div className="shell">
      <aside className={mobileNavOpen ? 'sidebar open' : 'sidebar'}>
        <div className="brand">
          {branding.logo_url ? <img src={branding.logo_url} alt="Logótipo" /> : <Building2 />}
          <span>{branding.product_name}<br /><b>{branding.customer_name}</b></span>
          <button className="mobile-close" onClick={() => setMobileNavOpen(false)} aria-label="Fechar menu"><X /></button>
        </div>
        <nav>
          {navItems.map(item => {
            const Icon = item.icon;
            return (
              <button key={item.id} className={section === item.id ? 'nav-link active' : 'nav-link'}
                onClick={() => navigate(item.id)}>
                <Icon size={18} /> {item.label}
              </button>
            );
          })}
        </nav>
        <div className="sidefoot">Portugal · Europe/Lisbon<br />Apoio à decisão imobiliária</div>
      </aside>

      <main>
        <header>
          <button className="mobile-menu" onClick={() => setMobileNavOpen(true)} aria-label="Abrir menu"><Menu /></button>
          <div>
            <small>{branding.tagline.toUpperCase()}</small>
            <h1>{section === 'procura' ? 'Procura IA' : section === 'agents' ? 'Agentes IA' : section === 'contact-ai' ? 'Contact AI' : section === 'team' ? 'Equipa' : section === 'settings' ? 'Definições' : 'Dashboard'}</h1>
            <p>Descobrir oportunidades. Qualificar leads. Apoiar a equipa.</p>
          </div>
          <div className="user-menu">
            <div><b>{user.full_name}</b><small>{user.role === 'super_admin' || user.role === 'admin' ? 'Administrador' : user.role === 'manager' ? 'Gestor' : user.role === 'viewer' ? 'Consulta' : 'Vendedor'} · {user.territory || user.email}</small></div>
            <button className="secondary" onClick={signOut}><LogOut size={15} /> Sair</button>
          </div>
        </header>

        {section === 'dashboard' && (
          <>
            <section className="stats">
              <Stat title="Total de leads" value={dash?.total_leads ?? '—'} icon={<Users />} />
              <Stat title="Novos leads" value={dash?.by_status?.new ?? '—'} icon={<Search />} />
              <Stat title="Seguimentos pendentes" value={dash?.pending_followups ?? '—'} icon={<CalendarClock />} />
              <Stat title="Rascunhos para rever" value={dash?.pending_drafts ?? '—'} icon={<Mail />} />
            </section>
            <section className="panel">
              <div className="panelhead">
                <div><h2>Últimas oportunidades</h2><p>Oportunidades identificadas e registadas.</p></div>
                <button className="secondary" disabled={dashboardBusy} onClick={() => void loadDashboard()}>
                  {dashboardBusy ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />} Atualizar
                </button>
              </div>
              {dashboardError && <div className="auth-error">{dashboardError}</div>}
              <LeadTable leads={leads} />
            </section>
          </>
        )}

        {section === 'procura' && (
          <section className="panel">
            <div className="panelhead">
              <div><h2><Search size={19} /> Pesquisa imobiliária</h2><p>Pesquise oportunidades na web ou na informação interna da plataforma.</p></div>
            </div>
            <div className="ai-capability" role="status">
              <span><b>Pesquisa interna:</b> {aiStatus ? (aiStatus.internal_search_enabled ? 'disponível' : 'indisponível') : 'a verificar'}</span>
              <span>
                <b>Pesquisa Web:</b> {aiStatus ? (aiStatus.web_search_enabled ? 'disponível' : 'indisponível') : 'a verificar'}
              </span>
              {aiStatus && searchMode === 'internal' && !aiStatus.internal_search_enabled && aiStatus.internal_search_reason && (
                <small>{aiStatus.internal_search_reason}</small>
              )}
              {aiStatus && searchMode === 'web' && !aiStatus.web_search_enabled && aiStatus.web_search_reason && (
                <small>{aiStatus.web_search_reason}</small>
              )}
              {aiStatusError && <small>{aiStatusError}</small>}
            </div>
            <div className="mode-switch" role="group" aria-label="Origem da pesquisa">
              <button type="button" className={searchMode === 'web' ? 'mode-option selected' : 'mode-option'} onClick={() => setSearchMode('web')}>
                <Globe2 size={17} /> Pesquisa Web
              </button>
              <button type="button" className={searchMode === 'internal' ? 'mode-option selected' : 'mode-option'} onClick={() => setSearchMode('internal')}>
                <Database size={17} /> Pesquisa Interna
              </button>
            </div>
            <form className="searchrow" onSubmit={runSearch}>
              <input value={query} onChange={event => setQuery(event.target.value)}
                placeholder="Ex.: apartamentos T2 em Lisboa até 350.000 €" />
              <button disabled={searchBusy || !query.trim() || (searchMode === 'web' && aiStatus !== null && !aiStatus.web_search_enabled) || (searchMode === 'internal' && aiStatus !== null && !aiStatus.internal_search_enabled)} type="submit">
                {searchBusy ? <><LoaderCircle className="spin" size={16} /> A pesquisar…</> : <><Search size={16} /> Procurar</>}
              </button>
            </form>
            {searchError && <div className="auth-error">{searchError}</div>}
            {report && <pre className="report">{report}</pre>}
            {!report && !searchError && <div className="empty-state"><MapPin size={25} /><b>Encontre a próxima oportunidade</b><span>Escolha a origem, descreva o imóvel e inicie a pesquisa.</span></div>}
          </section>
        )}

        {section === 'agents' && (
          <>
            <section className="panel">
              <div className="panelhead">
                <div><h2><Bot size={19} /> Os seis agentes da plataforma</h2><p>Execute tarefas especializadas. Os resultados ficam visíveis para revisão humana.</p></div>
              </div>
              {aiStatus && !aiStatus.agents_enabled && (
                <div className="auth-error">
                  {aiStatus.agents_reason || 'Os agentes necessitam de acesso IAM ao Amazon Bedrock na ECS Task Role.'}
                </div>
              )}
              {aiStatusError && <div className="auth-error">{aiStatusError}</div>}
              {agentError && <div className="auth-error">{agentError}</div>}
              <div className="agent-input">
                <label htmlFor="agent-context">Contexto ou dados para os agentes</label>
                <textarea
                  id="agent-context"
                  value={agentInput}
                  onChange={event => setAgentInput(event.target.value)}
                  rows={4}
                  maxLength={12000}
                  placeholder="Ex.: Analisa este anúncio T2 em Oeiras, anunciado por 295.000 €, e identifica riscos, pontos fortes e próximos passos. Para o Agente de Email, cola apenas uma mensagem que estejas autorizado a analisar."
                />
                <small>Até 12.000 caracteres. O conteúdo é enviado ao backend autenticado; não são enviados emails nem realizadas ações externas.</small>
              </div>
              <div className="agent-grid">
                {AGENTS.map(agent => {
                  const Icon = agent.icon;
                  const running = agentBusy === agent.id;
                  return (
                    <article className="agent-card" key={agent.id}>
                      <div className="agent-icon"><Icon size={21} /></div>
                      <h3>{agent.name}</h3>
                      <p>{agent.description}</p>
                      <small>{agent.purpose}</small>
                      <button disabled={!!agentBusy || (aiStatus !== null && !aiStatus.agents_enabled)} onClick={() => void runAgent(agent)}>
                        {running ? <><LoaderCircle className="spin" size={15} /> A executar…</> : <><Play size={15} /> Executar agente</>}
                      </button>
                      {agentResults[agent.id] && <pre className="report agent-result">{agentResults[agent.id]}</pre>}
                    </article>
                  );
                })}
              </div>
            </section>
          </>
        )}

        {section === 'contact-ai' && <ContactAIPanel apiFetch={apiFetch} role={user.role} />}

        {section === 'team' && (
          <>
            {user.role === 'admin' ? (
              <section className="panel">
                <div className="panelhead"><div><h2><UserPlus size={19} /> Criar conta de vendedor</h2><p>Convide um membro da equipa para a plataforma.</p></div></div>
                <form className="seller-form" onSubmit={createSeller}>
                  <input required placeholder="Nome completo" value={sellerName} onChange={event => setSellerName(event.target.value)} />
                  <input required type="email" placeholder="Email profissional" value={sellerEmail} onChange={event => setSellerEmail(event.target.value)} />
                  <input placeholder="Território (ex.: Lisboa)" value={sellerTerritory} onChange={event => setSellerTerritory(event.target.value)} />
                  <button type="submit">Criar vendedor</button>
                </form>
                {sellerResult && <pre className="report">{sellerResult}</pre>}
              </section>
            ) : (
              <section className="panel"><h2>Área da equipa</h2><p>Esta operação está disponível para administradores.</p></section>
            )}
            <section className="panel"><div className="panelhead"><div><h2>Oportunidades atribuídas</h2><p>Leads visíveis para a sua conta.</p></div></div><LeadTable leads={leads} /></section>
          </>
        )}

        {section === 'settings' && (
          <>
            <section className="panel">
              <div className="panelhead"><div><h2><ShieldCheck size={19} /> Segurança da conta</h2><p>A palavra-passe é gerida pela sua conta de autenticação.</p></div></div>
              <form className="seller-form" onSubmit={changePassword}>
                <input type="password" required placeholder="Palavra-passe atual" autoComplete="current-password"
                  value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} />
                <input type="password" required minLength={12} placeholder="Nova palavra-passe" autoComplete="new-password"
                  value={newPassword} onChange={event => setNewPassword(event.target.value)} />
                <button type="submit">Alterar palavra-passe</button>
              </form>
              {passwordMessage && <p className="branding-message">{passwordMessage}</p>}
            </section>

            {(user.role === 'admin' || user.role === 'super_admin') && (
              <section className="panel branding-panel">
                <div className="panelhead"><div><h2><Palette size={19} /> Identidade visual</h2><p>Personalize a marca sem alterar a configuração de autenticação.</p></div></div>
                <form className="branding-form" onSubmit={saveBranding}>
                  <label>Nome do produto<input required maxLength={100} value={branding.product_name} onChange={event => setBranding({ ...branding, product_name: event.target.value })} /></label>
                  <label>Nome do cliente<input required maxLength={160} value={branding.customer_name} onChange={event => setBranding({ ...branding, customer_name: event.target.value })} /></label>
                  <label>Subtítulo<input maxLength={240} value={branding.tagline} onChange={event => setBranding({ ...branding, tagline: event.target.value })} /></label>
                  <label>URL do logótipo<input type="url" value={branding.logo_url || ''} onChange={event => setBranding({ ...branding, logo_url: event.target.value || null })} placeholder="https://..." /></label>
                  <label>Cor principal<div className="color-field"><input type="color" value={branding.primary_color} onChange={event => setBranding({ ...branding, primary_color: event.target.value })} /><code>{branding.primary_color}</code></div></label>
                  <label>Cor de destaque<div className="color-field"><input type="color" value={branding.accent_color} onChange={event => setBranding({ ...branding, accent_color: event.target.value })} /><code>{branding.accent_color}</code></div></label>
                  <div className="branding-preview" style={{ borderColor: branding.primary_color }}>
                    <b style={{ color: branding.primary_color }}>{branding.product_name}</b><span>{branding.customer_name}</span><small>{branding.tagline}</small>
                  </div>
                  <button type="submit" disabled={brandingBusy}>{brandingBusy ? 'A guardar…' : 'Guardar identidade visual'}</button>
                  {brandingMessage && <p className="branding-message">{brandingMessage}</p>}
                </form>
              </section>
            )}
          </>
        )}

        <footer>{branding.product_name} | {branding.customer_name} · Revisão humana antes de ações externas · Dados sujeitos a controlo de acesso</footer>
      </main>
    </div>
  );
}

function Stat({ title, value, icon }: { title: string; value: string | number; icon: React.ReactNode }) {
  return <div className="stat"><div className="staticon">{icon}</div><small>{title}</small><strong>{value}</strong></div>;
}

function LeadTable({ leads }: { leads: Lead[] }) {
  return (
    <div className="tablewrap">
      <table>
        <thead><tr><th>Oportunidade</th><th>Localização</th><th>Score</th><th>Estado</th><th>Contacto</th></tr></thead>
        <tbody>
          {leads.map(lead => (
            <tr key={lead.id}>
              <td><b>{lead.title || 'Oportunidade sem título'}</b><small>{lead.source_name || 'Fonte por confirmar'}</small></td>
              <td>{lead.municipality || lead.address || '—'}</td>
              <td><span className="score">{lead.score == null ? '—' : `${lead.score}/100`}</span></td>
              <td><span className="status">{lead.status || 'Por classificar'}</span></td>
              <td>{lead.owner_name || 'Não verificado'}<small>{lead.owner_email || 'Sem email'}</small></td>
            </tr>
          ))}
          {!leads.length && <tr><td colSpan={5} className="empty">Ainda não existem leads atribuídos a esta conta.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
