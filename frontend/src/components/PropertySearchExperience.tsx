import { FormEvent, useMemo, useState } from 'react';
import { MapContainer, Marker, Popup, TileLayer } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Search, LoaderCircle, Images, MapPin, ExternalLink, Sparkles, Scale, LayoutGrid, Map as MapIcon, AlertCircle } from 'lucide-react';

type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;
type Property = {
  title: string; url: string; description?: string; image_url?: string | null;
  price?: string | null; currency?: string | null; address?: string | null;
  latitude?: number | null; longitude?: number | null; source_name?: string | null;
};
type SearchResponse = { text?: string; properties?: Property[]; sources?: Array<{title:string;url:string}>; result_count?: number };
type Props = { apiFetch: ApiFetch; aiStatus?: {web_search_enabled:boolean;web_search_reason?:string|null}|null; aiStatusError?:string };
type View = 'grid' | 'map';
const markerIcon = L.divIcon({className:'ts-property-marker',html:'<span></span>',iconSize:[26,26],iconAnchor:[13,13]});

function formatPrice(price?: string | null, currency?: string | null) {
  if (!price) return 'Preço não indicado';
  const amount = Number(price.replace(/[^\d,.]/g, '').replace(',', '.'));
  if (!Number.isFinite(amount)) return price;
  try { return new Intl.NumberFormat('pt-PT',{style:'currency',currency:currency || 'EUR',maximumFractionDigits:0}).format(amount); }
  catch { return price; }
}

export default function PropertySearchExperience({apiFetch,aiStatus,aiStatusError}:Props) {
  const [query,setQuery] = useState('Apartamentos T2 em Lisboa até 350000 euros com varanda e estacionamento');
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const [result,setResult] = useState<SearchResponse|null>(null);
  const [view,setView] = useState<View>('grid');
  const [compare,setCompare] = useState<string[]>([]);
  const [analysis,setAnalysis] = useState<Record<string,string>>({});
  const [analysing,setAnalysing] = useState<string|null>(null);
  const properties = result?.properties || [];
  const comparable = useMemo(()=>properties.filter(p=>compare.includes(p.url)).slice(0,3),[properties,compare]);
  const mapped = properties.filter(p=>Number.isFinite(p.latitude)&&Number.isFinite(p.longitude));
  const center:[number,number] = mapped.length
    ? [mapped.reduce((n,p)=>n+Number(p.latitude),0)/mapped.length,mapped.reduce((n,p)=>n+Number(p.longitude),0)/mapped.length]
    : [38.7223,-9.1393];

  async function search(event:FormEvent) {
    event.preventDefault(); if(!query.trim()) return;
    setBusy(true);setError('');setCompare([]);setAnalysis({});
    try {
      const params=new URLSearchParams({query:query.trim(),source:'web'});
      const response=await apiFetch('/research?'+params.toString(),{method:'POST'});
      const payload=await response.json();
      if(!response.ok) throw new Error(payload?.detail||'Pesquisa falhou (HTTP '+response.status+').');
      setResult(payload as SearchResponse);
      if(!(payload?.properties||[]).length) setError('Foram encontradas fontes, mas não foi possível extrair pré-visualizações de anúncios. Consulte as fontes originais.');
    } catch(e) {setError(e instanceof Error?e.message:'Não foi possível concluir a pesquisa.');}
    finally {setBusy(false);}
  }

  async function analyse(property:Property) {
    if(!property.image_url) return;
    setAnalysing(property.url);setError('');
    try {
      const response=await apiFetch('/research/visual-analysis',{method:'POST',body:JSON.stringify({image_url:property.image_url,context:property.title})});
      const payload=await response.json();
      if(!response.ok) throw new Error(payload?.detail||'Análise visual falhou (HTTP '+response.status+').');
      setAnalysis(old=>({...old,[property.url]:payload.analysis}));
    } catch(e) {setError(e instanceof Error?e.message:'Não foi possível analisar a fotografia.');}
    finally {setAnalysing(null);}
  }

  function toggleCompare(url:string) {
    setCompare(old=>old.includes(url)?old.filter(x=>x!==url):old.length<3?[...old,url]:old);
  }

  return <section className="property-search">
    <div className="property-search-hero"><div>
      <span className="property-eyebrow"><Sparkles size={14}/> PROCURA IA · INTELIGÊNCIA IMOBILIÁRIA</span>
      <h2>Encontre o imóvel certo.</h2><p>Pesquise anúncios públicos, compare oportunidades e analise fotografias reais com IA.</p>
    </div><div className="property-hero-mark"><Search size={30}/></div></div>
    <form className="property-query" onSubmit={search}>
      <Search size={19}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Ex.: T2 em Lisboa até 350.000 €, com varanda" aria-label="Pesquisa de imóveis"/>
      <button disabled={busy||!query.trim()||(aiStatus!==null&&aiStatus!==undefined&&!aiStatus.web_search_enabled)}>
        {busy?<><LoaderCircle className="spin" size={16}/> A pesquisar</>:'Pesquisar imóveis'}
      </button>
    </form>
    {aiStatus&&!aiStatus.web_search_enabled&&<p className="property-hint"><AlertCircle size={15}/>{aiStatus.web_search_reason||'Pesquisa Web indisponível.'}</p>}
    {aiStatusError&&<p className="property-hint">{aiStatusError}</p>}
    {error&&<p className="property-hint property-error"><AlertCircle size={15}/>{error}</p>}
    {result&&<>
      <div className="property-results-head"><div><span className="property-eyebrow">RESULTADOS</span><h3>{properties.length} anúncios com pré-visualização</h3><p>{result.result_count??result.sources?.length??0} fontes consultadas · Fotografias obtidas dos anúncios originais</p></div>
        <div className="property-view-switch"><button type="button" className={view==='grid'?'active':''} onClick={()=>setView('grid')}><LayoutGrid size={15}/> Grelha</button><button type="button" className={view==='map'?'active':''} onClick={()=>setView('map')}><MapIcon size={15}/> Mapa</button></div>
      </div>
      {view==='grid'&&<div className="property-grid">{properties.map((p,i)=><article className="property-card" key={p.url}>
        <div className="property-photo">{p.image_url?<img src={p.image_url} alt={'Fotografia do anúncio: '+p.title} loading="lazy" referrerPolicy="no-referrer"/>:<div className="property-no-photo"><Images size={27}/><span>Fotografia não disponibilizada pela fonte</span></div>}<span className="property-index">#{i+1}</span></div>
        <div className="property-card-body"><div className="property-card-price">{formatPrice(p.price,p.currency)}</div><h3>{p.title}</h3><p>{p.address||p.description||'Consulte o anúncio original para mais detalhes.'}</p><small>{p.source_name||'Fonte pública'}</small>
          <div className="property-card-actions"><a href={p.url} target="_blank" rel="noreferrer"><ExternalLink size={14}/> Anúncio</a><button type="button" className={compare.includes(p.url)?'selected':''} onClick={()=>toggleCompare(p.url)} disabled={!compare.includes(p.url)&&compare.length>=3}><Scale size={14}/> Comparar</button></div>
          {p.image_url&&<button type="button" className="property-analyse" onClick={()=>void analyse(p)} disabled={analysing!==null}>{analysing===p.url?<><LoaderCircle className="spin" size={14}/> A analisar</>:<><Sparkles size={14}/> Analisar fotografia com IA</>}</button>}
          {analysis[p.url]&&<div className="property-analysis"><b>Análise visual IA</b><p>{analysis[p.url]}</p><small>Descrição visual assistida por IA; não constitui avaliação ou inspeção técnica.</small></div>}
        </div></article>)}</div>}
      {view==='map'&&<div className="property-map-panel">
        {mapped.length?<MapContainer center={center} zoom={10} scrollWheelZoom={false} className="property-map"><TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>{mapped.map(p=><Marker key={p.url} position={[Number(p.latitude),Number(p.longitude)]} icon={markerIcon}><Popup><b>{p.title}</b><br/>{formatPrice(p.price,p.currency)}<br/><a href={p.url} target="_blank" rel="noreferrer">Abrir anúncio</a></Popup></Marker>)}</MapContainer>:<div className="property-map-empty"><MapPin size={30}/><b>Sem coordenadas verificadas</b><span>As fontes não publicaram coordenadas. Não vamos inventar localizações.</span></div>}
        <div className="property-map-list">{properties.map(p=><a key={p.url} href={'https://www.openstreetmap.org/search?query='+encodeURIComponent(p.address||p.title)} target="_blank" rel="noreferrer"><MapPin size={14}/><span>{p.title}<small>{p.address||'Localização por confirmar'}</small></span></a>)}</div>
        <small className="property-map-attribution">OpenStreetMap · Coordenadas apenas quando publicadas na fonte.</small>
      </div>}
      {comparable.length>0&&<section className="property-compare"><div><h3><Scale size={17}/> Comparação de imóveis</h3><p>Selecionou {comparable.length} de 3 imóveis.</p></div><div className="property-compare-grid">{comparable.map(p=><article key={p.url}><b>{p.title}</b><strong>{formatPrice(p.price,p.currency)}</strong><span>{p.address||'Localização não indicada'}</span><a href={p.url} target="_blank" rel="noreferrer">Ver anúncio original</a></article>)}</div></section>}
      <section className="property-sources"><h3>Fontes originais</h3>{(result.sources||[]).map((s,i)=><a key={s.url} href={s.url} target="_blank" rel="noreferrer"><span>[{i+1}] {s.title}</span><ExternalLink size={13}/></a>)}</section>
      {result.text&&<details className="property-report"><summary>Ver síntese da pesquisa</summary><pre>{result.text}</pre></details>}
    </>}
  </section>;
}
