    try {
      const [leadsResponse, dashboardResponse] = await Promise.all([
        apiFetch('/leads'),
        apiFetch('/dashboard'),
      ]);

      if (!leadsResponse.ok) {
        throw new Error(`Não foi possível carregar os leads (${leadsResponse.status})`);
      }
      if (!dashboardResponse.ok) {
        throw new Error(`Não foi possível carregar o dashboard (${dashboardResponse.status})`);
      }

      const leadsData = await leadsResponse.json();
      const dashboardData = await dashboardResponse.json();

      setLeads(Array.isArray(leadsData) ? leadsData : (leadsData.items ?? []));
      setDash(dashboardData);
    } catch (error) {
      console.error('Dashboard loading failed:', error);
    }
  }, [token, apiFetch]);

  useEffect(() => {
    if (token) void load();
  }, [token, load]);

  async function signIn(event: FormEvent) {
    event.preventDefault(); setLoginError('');
    try {
      const result = await cognitoSignIn({ username: email.trim(), password });
      if (!result.isSignedIn) {
        if (result.nextStep.signInStep === 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED') {
          setNeedsNewPassword(true);
          setLoginError('Defina uma nova palavra-passe para concluir o primeiro acesso.');
          return;
        }
        setLoginError(`A autenticação exige uma etapa adicional (${result.nextStep.signInStep}). Configure o respetivo desafio Cognito.`);
        return;
      }
      await loadCognitoUser();
      setPassword('');
    } catch (error: any) {
      setLoginError(error?.message || 'Não foi possível iniciar sessão');
    }
  }

  async function signOut() {
    try { await cognitoSignOut(); } finally { setToken(''); setUser(null); setLeads([]); setDash(null); }
  }

  async function completeFirstLogin(event: FormEvent) {
    event.preventDefault(); setLoginError('');
    try {
      const result = await cognitoConfirmSignIn({ challengeResponse: challengePassword });
      if (result.isSignedIn) {
        setNeedsNewPassword(false); setChallengePassword(''); setPassword('');
        await loadCognitoUser();
      } else {
        setLoginError(`Cognito exige outra etapa: ${result.nextStep.signInStep}`);
      }
    } catch (error: any) {
      setLoginError(error?.message || 'Não foi possível concluir o primeiro acesso');
    }
  }

  useEffect(() => { document.title = `${branding.product_name} | ${branding.customer_name}`; document.documentElement.style.setProperty('--brand-primary', branding.primary_color); document.documentElement.style.setProperty('--brand-accent', branding.accent_color); }, [branding]);

  async function research() {
    setBusy(true);
    try {
      const response = await apiFetch(`/research?query=${encodeURIComponent(query)}`, { method: 'POST' });
      const contentType = response.headers.get('content-type') || '';
      const data = contentType.includes('application/json')
        ? await response.json()
        : { detail: `Resposta inesperada do servidor (${response.status}). Verifique VITE_API_URL e o backend.` };
      if (!response.ok) throw new Error(data.detail || `Erro HTTP ${response.status}`);
      setReport(data.text || data.detail || 'Sem resultados');
    } catch (error: any) {
      setReport(error?.message || 'Não foi possível concluir a pesquisa.');
    } finally { setBusy(false); }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault(); setPasswordMessage('');
    try {
      await updatePassword({ oldPassword: currentPassword, newPassword });
      setPasswordMessage('Palavra-passe alterada com sucesso.');
      setCurrentPassword(''); setNewPassword('');
    } catch (error: any) {
      setPasswordMessage(error?.message || 'Não foi possível alterar a palavra-passe');
    }
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
    setSellerResult(data.message || `Convite Cognito enviado para ${data.user.email}.`);
    setSellerName(''); setSellerEmail(''); setSellerTerritory('');
  }

  if (booting) return <div className="auth-page"><div className="auth-card">A validar sessão…</div></div>;
  if (needsNewPassword) return <div className="auth-page"><form className="auth-card" onSubmit={completeFirstLogin}><div className="auth-brand"><Building2 size={34}/><b>ThinkSmart AI</b></div><h1>Primeiro acesso</h1><p>Defina uma nova palavra-passe para concluir o convite da sua conta.</p><label>Nova palavra-passe</label><input type="password" minLength={12} required autoComplete="new-password" value={challengePassword} onChange={e => setChallengePassword(e.target.value)}/>{loginError && <div className="auth-error">{loginError}</div>}<button className="auth-submit" type="submit">Guardar palavra-passe</button></form></div>;
  if (!user || !token) return <div className="auth-page"><form className="auth-card" onSubmit={signIn}><div className="auth-brand">{branding.logo_url ? <img src={branding.logo_url} alt="Company logo"/> : <Building2 size={34}/>}<div>{branding.product_name}<br/><b>{branding.customer_name}</b></div></div><small className="eyebrow">REAL ESTATE INTELLIGENCE · PORTUGAL</small><h1>Iniciar sessão</h1><p>Aceda ao espaço seguro da sua equipa imobiliária.</p><label>Email profissional</label><input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} placeholder="nome@empresa.pt"/><label>Palavra-passe</label><input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} placeholder="A sua palavra-passe"/>{loginError && <div className="auth-error">{loginError}</div>}<button className="auth-submit" type="submit"><LockKeyhole size={16}/> Entrar</button><small className="auth-note">Acesso individual · Registo de auditoria · Sessão protegida</small></form></div>;

  if (user.must_change_password) return <div className="auth-page"><form className="auth-card" onSubmit={changePassword}><div className="auth-brand"><LockKeyhole size={32}/><b>Alterar palavra-passe</b></div><h1>Primeiro acesso</h1><p>Por segurança, defina uma palavra-passe nova antes de continuar. Use pelo menos 12 caracteres.</p><label>Palavra-passe temporária / atual</label><input type="password" required value={currentPassword} onChange={e => setCurrentPassword(e.target.value)}/><label>Nova palavra-passe</label><input type="password" minLength={12} required value={newPassword} onChange={e => setNewPassword(e.target.value)}/>{passwordMessage && <div className="auth-error">{passwordMessage}</div>}<button className="auth-submit" type="submit">Guardar nova palavra-passe</button></form></div>;

  return <div className="shell"><aside><div className="brand">{branding.logo_url ? <img src={branding.logo_url} alt="Company logo"/> : <Building2/>}<span>{branding.product_name}<br/><b>{branding.customer_name}</b></span></div><nav><a className="active"><ChartNoAxesCombined/> Dashboard</a><a><Users/> Leads & Sellers</a><a><Search/> AI Discovery</a><a><Mail/> Email Intelligence</a><a><CalendarClock/> Follow-ups</a><a><ShieldCheck/> Approvals & GDPR</a></nav><div className="sidefoot">Portugal · Europe/Lisbon<br/>AI-assisted CRM</div></aside><main><header><div><small>{branding.tagline.toUpperCase()}</small><h1>Sales overview</h1><p>Descobrir oportunidades. Qualificar leads. Ajudar os vendedores.</p></div><div className="user-menu"><div><b>{user.full_name}</b><small>{user.role === 'admin' ? 'Administrador' : 'Vendedor'} · {user.territory || user.email}</small></div><button className="secondary" onClick={signOut}><LogOut size={15}/> Sair</button></div></header><section className="stats"><Stat title="Total leads" value={dash?.total_leads??'—'} icon={<Users/>}/><Stat title="New leads" value={dash?.by_status?.new??'—'} icon={<Search/>}/><Stat title="Pending follow-ups" value={dash?.pending_followups??'—'} icon={<CalendarClock/>}/><Stat title="Drafts to review" value={dash?.pending_drafts??'—'} icon={<Mail/>}/></section><section className="panel"><div className="panelhead"><div><h2>AI property discovery</h2><p>Pesquisar oportunidades em fontes públicas e permitidas.</p></div><span className="pill">OpenAI web search</span></div><div className="searchrow"><input value={query} onChange={e=>setQuery(e.target.value)}/><button disabled={busy} onClick={research}>{busy?'A pesquisar…':<><Search size={16}/> Research</>}</button></div>{report&&<pre className="report">{report}</pre>}</section>{user.role === 'admin' && <section className="panel branding-panel"><div className="panelhead"><div><h2><Palette size={18}/> Identidade visual</h2><p>Altere o nome do produto, o cliente, o logótipo e as cores sem novo deploy.</p></div></div><form className="branding-form" onSubmit={saveBranding}><label>Nome do produto<input required maxLength={100} value={branding.product_name} onChange={e=>setBranding({...branding, product_name:e.target.value})}/></label><label>Nome do cliente<input required maxLength={160} value={branding.customer_name} onChange={e=>setBranding({...branding, customer_name:e.target.value})}/></label><label>Subtítulo<input maxLength={240} value={branding.tagline} onChange={e=>setBranding({...branding, tagline:e.target.value})}/></label><label>URL do logótipo (HTTPS ou caminho /)<input value={branding.logo_url || ''} onChange={e=>setBranding({...branding, logo_url:e.target.value || null})} placeholder="https://.../logo.svg"/></label><label>Cor principal<div className="color-field"><input type="color" value={branding.primary_color} onChange={e=>setBranding({...branding, primary_color:e.target.value})}/><code>{branding.primary_color}</code></div></label><label>Cor de destaque<div className="color-field"><input type="color" value={branding.accent_color} onChange={e=>setBranding({...branding, accent_color:e.target.value})}/><code>{branding.accent_color}</code></div></label><div className="branding-preview" style={{borderColor:branding.primary_color}}><b style={{color:branding.primary_color}}>{branding.product_name}</b><span>{branding.customer_name}</span><small>{branding.tagline}</small></div><button type="submit" disabled={brandingBusy}>{brandingBusy?'A guardar…':'Guardar identidade visual'}</button>{brandingMessage && <p className="branding-message">{brandingMessage}</p>}</form></section>}{user.role === 'admin' && <section className="panel"><div className="panelhead"><div><h2>Contas da equipa</h2><p>Criar acessos individuais para os cinco vendedores.</p></div><UserPlus/></div><form className="seller-form" onSubmit={createSeller}><input required placeholder="Nome completo" value={sellerName} onChange={e=>setSellerName(e.target.value)}/><input required type="email" placeholder="Email profissional" value={sellerEmail} onChange={e=>setSellerEmail(e.target.value)}/><input placeholder="Território (ex.: Lisboa)" value={sellerTerritory} onChange={e=>setSellerTerritory(e.target.value)}/><button type="submit">Criar vendedor</button></form>{sellerResult && <pre className="report">{sellerResult}</pre>}</section>}<section className="panel"><div className="panelhead"><div><h2>Latest leads</h2><p>Oportunidades identificadas e registadas.</p></div><button className="secondary" onClick={load}><RefreshCw size={15}/> Refresh</button></div><div className="tablewrap"><table><thead><tr><th>Opportunity</th><th>Location</th><th>Score</th><th>Status</th><th>Owner contact</th></tr></thead><tbody>{leads.map(l=><tr key={l.id}><td><b>{l.title}</b><small>{l.source_name||'Source pending'}</small></td><td>{l.municipality||l.address||'—'}</td><td><span className="score">{l.score}/100</span></td><td><span className="status">{l.status}</span></td><td>{l.owner_name||'Not verified'}<small>{l.owner_email||'No email'}</small></td></tr>)}{!leads.length&&<tr><td colSpan={5} className="empty">Ainda não existem leads atribuídos a esta conta.</td></tr>}</tbody></table></div></section><footer>{branding.product_name} | {branding.customer_name} · Human approval required · Dados pessoais tratados com controlo de acesso</footer></main></div>;
}
function Stat({title,value,icon}:{title:string,value:any,icon:any}){return <div className="stat"><div className="staticon">{icon}</div><small>{title}</small><strong>{value}</strong></div>}
