import { useCallback, useEffect, useState } from 'react';
import { Activity, RefreshCw, Users, CalendarClock, MousePointerClick, Search } from 'lucide-react';

type Overview = {
  period_days:number; active_users:number; active_today:number; total_users:number; inactive_users:number;
  events:number; sessions:number; features:{feature:string;events:number}[];
  users:{id:number;name:string;email:string;role:string;last_active:string;events:number}[];
};
type Props={apiFetch:(path:string,init?:RequestInit)=>Promise<Response>};
const labels:Record<string,string>={dashboard:'Dashboard',procura:'Procura IA',agents:'Agentes IA',contact_ai:'Contact AI',team:'Equipa',settings:'Definições',other:'Outros'};
const date=(value:string)=>new Intl.DateTimeFormat('pt-PT',{dateStyle:'short',timeStyle:'short'}).format(new Date(value));

export default function AnalyticsPanel({apiFetch}:Props){
 const [days,setDays]=useState(30);const [data,setData]=useState<Overview|null>(null);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 const load=useCallback(async()=>{setBusy(true);setError('');try{const r=await apiFetch('/analytics/overview?days='+days);const d=await r.json();if(!r.ok)throw new Error(d?.detail||'Não foi possível carregar as métricas.');setData(d);}catch(e){setError(e instanceof Error?e.message:'Erro ao carregar analytics.');}finally{setBusy(false);}},[apiFetch,days]);
 useEffect(()=>{void load();},[load]);
 const max=Math.max(1,...(data?.features||[]).map(x=>x.events));
 return <section className="panel">
  <div className="panelhead"><div><h2><Activity size={19}/> Analytics de utilização</h2><p>Atividade real registada na aplicação por utilizador e funcionalidade.</p></div>
   <div className="mode-switch"><button className={days===7?'selected':''} onClick={()=>setDays(7)}>7 dias</button><button className={days===30?'selected':''} onClick={()=>setDays(30)}>30 dias</button><button className={days===90?'selected':''} onClick={()=>setDays(90)}>90 dias</button></div>
   <button className="secondary" onClick={()=>void load()} disabled={busy}>{busy?<RefreshCw className="spin" size={15}/>:<RefreshCw size={15}/>} Atualizar</button>
  </div>
  {error&&<div className="auth-error">{error}</div>}
  {data&&<>
   <section className="stats">
    <div className="stat"><div className="staticon"><Users/></div><small>Utilizadores ativos ({days} dias)</small><strong>{data.active_users}</strong></div>
    <div className="stat"><div className="staticon"><Activity/></div><small>Ativos nas últimas 24h</small><strong>{data.active_today}</strong></div>
    <div className="stat"><div className="staticon"><CalendarClock/></div><small>Sessões iniciadas</small><strong>{data.sessions}</strong></div>
    <div className="stat"><div className="staticon"><MousePointerClick/></div><small>Eventos registados</small><strong>{data.events}</strong></div>
   </section>
   <section className="panel">
    <div className="panelhead"><div><h3>Utilização por funcionalidade</h3><p>Visualizações e operações concluídas no período selecionado.</p></div></div>
    {data.features.length?data.features.map(item=><div key={item.feature} style={{display:'grid',gridTemplateColumns:'150px 1fr 56px',gap:12,alignItems:'center',margin:'12px 0'}}>
      <span>{labels[item.feature]||item.feature}</span><div style={{height:10,background:'var(--surface-muted, #e8edf5)',borderRadius:8,overflow:'hidden'}}><div style={{height:'100%',width:(item.events/max*100)+'%',background:'var(--brand-primary, #2563eb)',borderRadius:8}}/></div><b>{item.events}</b>
     </div>):<p className="empty">Ainda não existem eventos neste período.</p>}
   </section>
   <section className="panel">
    <div className="panelhead"><div><h3>Atividade por utilizador</h3><p>{data.total_users} contas ativas · {data.inactive_users} sem atividade registada neste período.</p></div><Search size={18}/></div>
    <div className="tablewrap"><table><thead><tr><th>Utilizador</th><th>Perfil</th><th>Última atividade</th><th>Eventos</th></tr></thead><tbody>
     {data.users.map(u=><tr key={u.id}><td><b>{u.name}</b><small>{u.email}</small></td><td>{u.role}</td><td>{u.last_active?date(u.last_active):'—'}</td><td>{u.events}</td></tr>)}
     {!data.users.length&&<tr><td colSpan={4} className="empty">Sem atividade registada. Os eventos começam a ser contabilizados após a publicação desta versão.</td></tr>}
    </tbody></table></div>
   </section>
   <p><small>Os dados representam eventos recolhidos a partir da publicação desta versão; não incluem retroativamente logins ou atividade anteriores.</small></p>
  </>}
 </section>;
}
