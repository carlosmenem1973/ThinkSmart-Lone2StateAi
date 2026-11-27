import { Bot, CheckCircle2, CircleAlert, Clock3, Search, ShieldCheck } from 'lucide-react';

type DashboardCounts = {
  by_status?: Record<string, number | undefined>;
};

type AiStatus = {
  internal_search_enabled: boolean;
  web_search_enabled: boolean;
  agents_enabled: boolean;
};

type Props = {
  dashboard: DashboardCounts | null;
  aiStatus: AiStatus | null;
  aiStatusError?: string;
};

const PIPELINE_STAGES = [
  { key: 'new', label: 'Novas', tone: 'new' },
  { key: 'review', label: 'Em análise', tone: 'review' },
  { key: 'qualified', label: 'Qualificadas', tone: 'qualified' },
  { key: 'contacted', label: 'Em contacto', tone: 'contacted' },
  { key: 'replied', label: 'Com resposta', tone: 'replied' },
  { key: 'listed', label: 'Angariadas', tone: 'listed' },
];

export default function DashboardInsights({ dashboard, aiStatus, aiStatusError }: Props) {
  const counts = dashboard?.by_status;
  const total = PIPELINE_STAGES.reduce((sum, stage) => sum + (counts?.[stage.key] ?? 0), 0);
  const hasCounts = Boolean(counts);
  const capabilities = [
    { label: 'Pesquisa interna', enabled: aiStatus?.internal_search_enabled },
    { label: 'Pesquisa Web', enabled: aiStatus?.web_search_enabled },
    { label: 'Agentes IA', enabled: aiStatus?.agents_enabled },
  ];

  return (
    <section className="dashboard-insights" aria-label="Resumo operacional">
      <article className="panel dashboard-insight-panel">
        <div className="panelhead">
          <div>
            <h2><Clock3 size={17} /> Resumo do pipeline</h2>
            <p>Distribuição das oportunidades pelos estados atuais.</p>
          </div>
          <span className="dashboard-total">{hasCounts ? total : '—'} <small>leads</small></span>
        </div>
        {hasCounts ? (
          <div className="pipeline-list">
            {PIPELINE_STAGES.map(stage => {
              const count = counts?.[stage.key] ?? 0;
              const percentage = total > 0 ? (count / total) * 100 : 0;
              return (
                <div className="pipeline-row" key={stage.key}>
                  <div className="pipeline-label"><span className={`pipeline-dot ${stage.tone}`} /><span>{stage.label}</span><b>{count}</b></div>
                  <div className="pipeline-track" role="progressbar" aria-label={stage.label} aria-valuenow={count} aria-valuemin={0} aria-valuemax={total || 1}>
                    <span className={`pipeline-fill ${stage.tone}`} style={{ width: `${percentage}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="empty dashboard-insight-empty">A carregar os estados dos leads…</p>
        )}
      </article>

      <article className="panel dashboard-insight-panel">
        <div className="panelhead">
          <div>
            <h2><Bot size={17} /> Inteligência artificial</h2>
            <p>Disponibilidade das capacidades configuradas para esta conta.</p>
          </div>
          <span className="dashboard-ai-icon"><ShieldCheck size={19} /></span>
        </div>
        {aiStatusError ? (
          <div className="dashboard-ai-message"><CircleAlert size={16} /> {aiStatusError}</div>
        ) : aiStatus ? (
          <div className="dashboard-capabilities">
            {capabilities.map(item => (
              <div className="dashboard-capability" key={item.label}>
                <span>{item.label}</span>
                <span className={item.enabled ? 'capability-state enabled' : 'capability-state disabled'}>
                  {item.enabled ? <CheckCircle2 size={14} /> : <CircleAlert size={14} />}
                  {item.enabled ? 'Disponível' : 'Indisponível'}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="empty dashboard-insight-empty"><Search size={15} /> A verificar as capacidades de IA…</p>
        )}
        <p className="dashboard-insight-note">O estado é consultado à API. A execução de ações externas continua sujeita a autorização e revisão humana.</p>
      </article>
    </section>
  );
}
