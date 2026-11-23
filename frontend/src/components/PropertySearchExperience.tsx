import { FormEvent, useMemo, useState } from 'react';
import { Search, LoaderCircle, Images, MapPin, ExternalLink, Sparkles, Scale, LayoutGrid, Map as MapIcon, AlertCircle, Globe2, Database, Mic } from 'lucide-react';
import './PropertySearchExperience.css';

type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;
type SearchMode = 'web' | 'internal';
type Property = {
  title: string; url: string; description?: string; image_url?: string | null; image_urls?: string[];
  price?: string | null; currency?: string | null; address?: string | null;
  latitude?: number | null; longitude?: number | null; location_precision?: string | null; map_location_source?: string | null; source_name?: string | null;
};
type InternalItem = {
  id: number; title: string; address?: string | null; municipality?: string | null; district?: string | null;
  source_name?: string | null; source_url?: string | null; score?: number | null; status?: string | null;
};
type SearchResponse = {
  source?: SearchMode; text?: string; properties?: Property[]; items?: InternalItem[];
  sources?: Array<{title:string;url:string}>; result_count?: number; count?: number;
};
type Props = {
  apiFetch: ApiFetch;
  aiStatus?: {web_search_enabled:boolean;web_search_reason?:string|null;internal_search_enabled:boolean;internal_search_reason?:string|null;vision_analysis_configured?:boolean}|null;
  aiStatusError?:string;
};
type View = 'grid' | 'map';

function formatPrice(price?: string | null, currency?: string | null) {
  if (!price) return 'Preço não indicado';
  const amount = Number(price.replace(/[^\d,.]/g, '').replace(',', '.'));
  if (!Number.isFinite(amount)) return price;
  try { return new Intl.NumberFormat('pt-PT',{style:'currency',currency:currency || 'EUR',maximumFractionDigits:0}).format(amount); }
  catch { return price; }
}

function readableError(value: unknown): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(readableError).filter(Boolean).join('; ');
  if (value && typeof value === 'object') {
    const item = value as Record<string, unknown>;
    if (typeof item.msg === 'string') return item.msg;
    for (const key of ['detail','message','error','reason']) {
      if (item[key] !== undefined) return readableError(item[key]);
    }
    return Object.entries(item).map(([key, entry]) => key + ': ' + readableError(entry)).join('; ');
  }
  return value == null ? '' : String(value);
}


function startPropertyDictation(onText:(text:string)=>void) {
  const browser=window as unknown as {SpeechRecognition?:new()=>any;webkitSpeechRecognition?:new()=>any};
  const Recognition=browser.SpeechRecognition||browser.webkitSpeechRecognition;
  if(!Recognition){window.alert('O reconhecimento de voz não é suportado neste navegador.');return;}
  const recognition=new Recognition();recognition.lang='pt-PT';recognition.interimResults=false;recognition.maxAlternatives=1;
  recognition.onresult=(event:any)=>{const text=event.results?.[0]?.[0]?.transcript;if(typeof text==='string'&&text.trim())onText(text.trim());};
  recognition.onerror=()=>window.alert('Não foi possível reconhecer a voz. Pode escrever a pesquisa.');
  recognition.start();
}

export default function PropertySearchExperience({apiFetch,aiStatus,aiStatusError}:Props) {
  const [query,setQuery] = useState('Imóveis para venda em Algés');
  const [mode,setMode] = useState<SearchMode>('web');
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const [result,setResult] = useState<SearchResponse|null>(null);
  const [view,setView] = useState<View>('grid');
  const [compare,setCompare] = useState<string[]>([]);
  const [analysis,setAnalysis] = useState<Record<string,string>>({});
  const [analysing,setAnalysing] = useState<string|null>(null);
  const [failedImages,setFailedImages] = useState<string[]>([]);
  const [selectedMapUrl,setSelectedMapUrl] = useState<string|null>(null);
  const properties = result?.properties || [];
  const internalItems = result?.items || [];
  const comparable = useMemo(()=>properties.filter(p=>compare.includes(p.url)).slice(0,3),[properties,compare]);
  const mapped = properties.filter(p=>Number.isFinite(p.latitude)&&Number.isFinite(p.longitude));
  const mapLayout = useMemo(() => {
    if (!mapped.length) return null;
    const project = (lat:number, lon:number, zoom:number) => {
      const scale = 256 * Math.pow(2, zoom);
      const sin = Math.sin(Math.max(-85.0511, Math.min(85.0511, lat)) * Math.PI / 180);
      return {x:(lon + 180) / 360 * scale,y:(0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale};
    };
    const bounds = mapped.map(p=>project(Number(p.latitude),Number(p.longitude),0));
    const minX=Math.min(...bounds.map(p=>p.x)),maxX=Math.max(...bounds.map(p=>p.x));
    const minY=Math.min(...bounds.map(p=>p.y)),maxY=Math.max(...bounds.map(p=>p.y));
    const spanX=Math.max(maxX-minX,0.002),spanY=Math.max(maxY-minY,0.002);
    const zoom=Math.max(4,Math.min(17,Math.floor(Math.min(Math.log2(580/spanX),Math.log2(360/spanY)))));
    const center=project(mapped.reduce((s,p)=>s+Number(p.latitude),0)/mapped.length,mapped.reduce((s,p)=>s+Number(p.longitude),0)/mapped.length,zoom);
    const left=center.x-320,top=center.y-210;
    const xStart=Math.floor(left/256),yStart=Math.floor(top/256);
    const tiles=[];
    for(let x=xStart;x<=Math.floor((left+640)/256);x++) for(let y=yStart;y<=Math.floor((top+420)/256);y++){
      const count=Math.pow(2,zoom);
      if(y>=0&&y<count) tiles.push({key:x+'-'+y,src:'https://tile.openstreetmap.org/'+zoom+'/'+((x%count)+count)%count+'/'+y+'.png',left:x*256-left,top:y*256-top});
    }
    const markers=mapped.map((p)=>{const point=project(Number(p.latitude),Number(p.longitude),zoom);return {...p,left:point.x-left,top:point.y-top};});
    return {tiles,markers,zoom};
  },[mapped]);
  const modeAvailable = mode === 'web' ? aiStatus?.web_search_enabled !== false : aiStatus?.internal_search_enabled !== false;

  async function search(event:FormEvent) {
    event.preventDefault(); if(!query.trim()) return;
    setBusy(true);setError('');setCompare([]);setAnalysis({});setFailedImages([]);setResult(null);
    try {
      const params=new URLSearchParams({query:query.trim(),source:mode});
      const response=await apiFetch('/research?'+params.toString(),{method:'POST'});
      const payload=await response.json();
      if(!response.ok) throw new Error(readableError(payload?.detail)||readableError(payload?.message)||'Pesquisa falhou (HTTP '+response.status+').');
      setResult(payload as SearchResponse);
      if(mode==='web' && !(payload?.properties||[]).length) setError('Foram encontradas fontes, mas não foi possível extrair pré-visualizações de anúncios. Consulte as fontes originais.');
    } catch(e) {setError(e instanceof Error?e.message:'Não foi possível concluir a pesquisa.');}
    finally {setBusy(false);}
  }

  async function analyse(property:Property) {
    if(!property.image_url || aiStatus?.vision_analysis_configured === false) return;
    setAnalysing(property.url);setError('');
    try {
      const response=await apiFetch('/research/visual-analysis',{method:'POST',body:JSON.stringify({image_url:property.image_url,context:property.title})});
      const payload=await response.json();
      if(!response.ok) throw new Error(readableError(payload?.detail)||'Análise visual falhou (HTTP '+response.status+').');
      setAnalysis(old=>({...old,[property.url]:payload.analysis}));
    } catch(e) {setError(e instanceof Error?e.message:'Não foi possível analisar a fotografia.');}
    finally {setAnalysing(null);}
  }

  function toggleCompare(url:string) {
    setCompare(old=>old.includes(url)?old.filter(x=>x!==url):old.length<3?[...old,url]:old);
  }

  return <section className="property-search">
    <div className="panelhead property-panelhead">
      <div><h2><Search size={19}/> Pesquisa imobiliária</h2><p>Pesquise oportunidades na web ou na informação interna da plataforma.</p></div>
    </div>
    <div className="ai-capability" role="status">
      <span><b>Pesquisa interna:</b> {aiStatus ? (aiStatus.internal_search_enabled ? 'disponível' : 'indisponível') : 'a verificar'}</span>
      <span><b>Pesquisa Web:</b> {aiStatus ? (aiStatus.web_search_enabled ? 'disponível' : 'indisponível') : 'a verificar'}</span>
    </div>
    <div className="mode-switch" role="group" aria-label="Origem da pesquisa">
      <button type="button" className={mode==='web'?'mode-option selected':'mode-option'} onClick={()=>{setMode('web');setError('');}}>
        <Globe2 size={17}/> Pesquisa Web
      </button>
      <button type="button" className={mode==='internal'?'mode-option selected':'mode-option'} onClick={()=>{setMode('internal');setError('');}}>
        <Database size={17}/> Pesquisa Interna
      </button>
    </div>
    <form className="property-query" onSubmit={search}>
      <Search size={19}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Ex.: apartamentos T2 em Lisboa até 350.000 €" aria-label="Pesquisa de imóveis"/><button type="button" className="secondary" aria-label="Ditar pesquisa" onClick={()=>startPropertyDictation(text=>setQuery(current=>(current+" "+text).trim()))}><Mic size={16}/> Voz</button>
      <button disabled={busy||!query.trim()||!modeAvailable}>
        {busy?<><LoaderCircle className="spin" size={16}/> A pesquisar…</>:<><Search size={16}/> Procurar</>}
      </button>
    </form>
    {!modeAvailable&&<p className="property-hint"><AlertCircle size={15}/>{mode==='web'?(aiStatus?.web_search_reason||'Pesquisa Web indisponível.'):(aiStatus?.internal_search_reason||'Pesquisa interna indisponível.')}</p>}
    {aiStatusError&&<p className="property-hint">{aiStatusError}</p>}
    {error&&<p className="property-hint property-error"><AlertCircle size={15}/>{error}</p>}
    {result&&mode==='web'&&<>
      <div className="property-results-head"><div><span className="property-eyebrow">RESULTADOS DA PESQUISA WEB</span><h3>{properties.length} resultados</h3><p>{result.result_count??result.sources?.length??0} fontes consultadas · Fotografias apenas quando publicadas no anúncio original</p></div>
        <div className="property-view-switch"><button type="button" className={view==='grid'?'active':''} onClick={()=>setView('grid')}><LayoutGrid size={15}/> Grelha</button><button type="button" className={view==='map'?'active':''} onClick={()=>setView('map')}><MapIcon size={15}/> Mapa</button></div>
      </div>
      {view==='grid'&&<div className="property-grid">{properties.map((p,i)=>{
        const images=(p.image_urls?.length?p.image_urls:(p.image_url?[p.image_url]:[])).filter(image=>!failedImages.includes(image)).slice(0,4);
        return <article className="property-card" key={p.url}>
        <div className={images.length?'property-photo property-photo-gallery':'property-photo'}>{images.map((image,index)=><img key={image} src={image} alt={'Fotografia '+(index+1)+' do anúncio: '+p.title} loading="lazy" referrerPolicy="no-referrer" onError={()=>setFailedImages(old=>old.includes(image)?old:[...old,image])}/>)}{!images.length&&<div className="property-no-photo"><Images size={27}/><span>Fotografia não disponível nesta fonte</span></div>}<span className="property-index">#{i+1}</span></div>
        <div className="property-card-body"><div className="property-card-price">{formatPrice(p.price,p.currency)}</div><h3>{p.title}</h3><p>{p.address||p.description||'Consulte o anúncio original para mais detalhes.'}</p><small>{p.source_name||'Fonte pública'}</small>
          <div className="property-card-actions"><a href={p.url} target="_blank" rel="noreferrer"><ExternalLink size={14}/> Anúncio original</a><button type="button" className={compare.includes(p.url)?'selected':''} onClick={()=>toggleCompare(p.url)} disabled={!compare.includes(p.url)&&compare.length>=3}><Scale size={14}/> Comparar</button></div>
          {p.image_url&&images.length>0&&aiStatus?.vision_analysis_configured!==false&&<button type="button" className="property-analyse" onClick={()=>void analyse(p)} disabled={analysing!==null}>{analysing===p.url?<><LoaderCircle className="spin" size={14}/> A analisar</>:<><Sparkles size={14}/> Analisar fotografia com IA</>}</button>}
          {analysis[p.url]&&<div className="property-analysis"><b>Análise visual IA</b><p>{analysis[p.url]}</p><small>Descrição visual assistida por IA; não constitui avaliação ou inspeção técnica.</small></div>}
        </div></article>;
      })}</div>}
      {view==='map'&&<div className="property-map-panel">
        {mapLayout?<div className="property-map" role="region" aria-label="Mapa com todos os imóveis geolocalizados">
          <div className="property-map-canvas">{mapLayout.tiles.map(tile=><img key={tile.key} className="property-map-tile" src={tile.src} alt="" style={{left:tile.left,top:tile.top}} loading="lazy"/>)}{mapLayout.markers.map((p,index)=><button key={p.url} type="button" className={'property-map-pin'+(selectedMapUrl===p.url?' selected':'')} style={{left:p.left,top:p.top}} title={p.title+' — '+formatPrice(p.price,p.currency)} onClick={()=>setSelectedMapUrl(p.url)}><span>{index+1}</span></button>)}</div>
          <div className="property-map-zoom"><a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a> · Zoom {mapLayout.zoom}</div>
        </div>:<div className="property-map-empty"><MapPin size={30}/><b>Sem coordenadas verificadas</b><span>As fontes não publicaram coordenadas. Os imóveis sem coordenadas continuam disponíveis na lista, sem pins inventados.</span></div>}
        <div className="property-map-list">{properties.map((p,index)=><button type="button" className={'property-map-item'+(selectedMapUrl===p.url?' selected':'')} key={p.url} onClick={()=>{setSelectedMapUrl(p.url);if(!Number.isFinite(p.latitude)||!Number.isFinite(p.longitude))window.open('https://www.openstreetmap.org/search?query='+encodeURIComponent(p.address||p.title),'_blank','noopener,noreferrer');}}><MapPin size={14}/><span><b>{index+1}. {p.title}</b><small>{p.address||'Localização por confirmar'}</small><strong>{formatPrice(p.price,p.currency)}</strong>{p.location_precision==='address_geocoded'&&<em className="property-map-precision">Localização aproximada por morada</em>}{p.location_precision==='listing_coordinates'&&<em className="property-map-precision verified">Coordenadas do anúncio</em>}</span></button>)}</div>
        <small className="property-map-attribution">Mapa OpenStreetMap com marcadores para todos os anúncios que fornecem coordenadas verificáveis. Os restantes mantêm pesquisa externa por endereço.</small>
      </div>}
      {comparable.length>0&&<section className="property-compare"><div><h3><Scale size={17}/> Comparação de imóveis</h3><p>Selecionou {comparable.length} de 3 imóveis.</p></div><div className="property-compare-grid">{comparable.map(p=><article key={p.url}><b>{p.title}</b><strong>{formatPrice(p.price,p.currency)}</strong><span>{p.address||'Localização não indicada'}</span><a href={p.url} target="_blank" rel="noreferrer">Ver anúncio original</a></article>)}</div></section>}
      <section className="property-sources"><h3>Fontes originais</h3>{(result.sources||[]).map((s,i)=><a key={s.url} href={s.url} target="_blank" rel="noreferrer"><span>[{i+1}] {s.title}</span><ExternalLink size={13}/></a>)}</section>
      {result.text&&<details className="property-report"><summary>Ver síntese da pesquisa</summary><pre>{result.text}</pre></details>}
    </>}
    {result&&mode==='internal'&&<>
      <div className="property-results-head"><div><span className="property-eyebrow">RESULTADOS DA PLATAFORMA</span><h3>{result.count??internalItems.length} oportunidades encontradas</h3><p>Registos internos a que a tua conta tem acesso.</p></div></div>
      {internalItems.length>0?<div className="property-grid">{internalItems.map(item=><article className="property-card property-internal-card" key={item.id}>
        <div className="property-card-body"><div className="property-card-price">{typeof item.score==='number'?'Score '+item.score+'/100':'Oportunidade interna'}</div><h3>{item.title}</h3><p>{[item.address,item.municipality,item.district].filter(Boolean).join(' · ')||'Localização não indicada'}</p><small>{item.source_name||'Registo interno'} · {item.status||'Por classificar'}</small>
          {item.source_url&&<div className="property-card-actions"><a href={item.source_url} target="_blank" rel="noreferrer"><ExternalLink size={14}/> Fonte original</a></div>}
        </div></article>)}</div>:<div className="property-map-empty"><Database size={28}/><b>Não foram encontradas oportunidades</b><span>Experimenta alterar os termos da pesquisa ou verifica os registos disponíveis.</span></div>}
      {result.text&&<details className="property-report"><summary>Ver detalhe da pesquisa interna</summary><pre>{result.text}</pre></details>}
    </>}
  </section>;
}
