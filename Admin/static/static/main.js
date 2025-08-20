const {useState, useEffect, useMemo} = React;

/* ---------------- api helper ---------------- */
async function api(path) {
    const r = await fetch(path);
    const ct = r.headers.get('content-type') || '';
    if (!ct.includes('application/json')) throw new Error(`Expected JSON from ${path}`);
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
}

const slugify = s => (s || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

/* ---------- router ---------- */
function useRouter() {
    const [path, setPath] = useState(window.location.pathname + window.location.search);
    useEffect(() => {
        const onPop = () => setPath(window.location.pathname + window.location.search);
        window.addEventListener('popstate', onPop);
        return () => window.removeEventListener('popstate', onPop);
    }, []);
    const navigate = (to) => {
        window.history.pushState({}, '', to);
        setPath(to);
    };
    return {path, navigate};
}

const RouterCtx = React.createContext();

/* ---------- NEW: link helpers (always make entities clickable) ---------- */
function useGo() {
    const {navigate} = React.useContext(RouterCtx);
    return (e, to, stop = false) => {
        if (e) {
            e.preventDefault();
            if (stop) e.stopPropagation();
        }
        navigate(to);
    };
}

function CategoryLink({name, children, className, stop}) {
    const go = useGo();
    const slug = slugify(name || 'other');
    const to = `/category/${slug}`;
    return <a href={to} className={className} onClick={(e) => go(e, to, !!stop)}>{children || name}</a>;
}

function TopicLink({topic, children, className, stop}) {
    const go = useGo();
    if (!topic) return <span>{children}</span>;
    const to = `/topic/${topic.slug}`;
    return <a href={to} className={className} onClick={(e) => go(e, to, !!stop)}>{children || topic.title}</a>;
}

function TheoLink({theo, id, datasets, children, className, stop}) {
    const go = useGo();
    const t = theo || (datasets?.theologians || []).find(x => x.id === id);
    if (!t) return <span className={className}>{children || id}</span>;
    const to = `/theologian/${t.slug}`;
    return <a href={to} className={className} onClick={(e) => go(e, to, !!stop)}>{children || t.full_name}</a>;
}

function WorkLink({work, id, children, className, stop}) {
    const go = useGo();
    const w = work || {id};
    const to = `/work/${w.id}`;
    return <a href={to} className={className} onClick={(e) => go(e, to, !!stop)}>{children || (w.title || id)}</a>;
}

function workTitleWithSuffix(liveWork = {}, byWork = {}) {
    const title = liveWork.title || byWork.title || '';
    const suffix =
        liveWork.reference ||
        liveWork.title_suffix ||
        liveWork.suffix ||
        byWork.reference ||
        byWork.title_suffix ||
        byWork.suffix ||
        '';
    return title
    // return suffix ? `${title} (${suffix})` : title;
}


function uniq(arr) {
    return Array.from(new Set(arr || []));
}

function featuredTopicsForWork(workId, topics) {
    const out = [];
    for (const t of topics || []) {
        const kw = t.key_works || {};
        const inWts = (kw.wts_old_princeton || []).includes(workId);
        const inRecent = (kw.recent || []).includes(workId);
        if (inWts || inRecent) out.push({
            topic_id: t.id,
            topic_slug: t.slug,
            title: t.title,
            bucket: inWts ? 'WTS' : 'Recent'
        });
    }
    return out;
}

// Resolve authors for a work id → [{display, theo}] where theo is a theologian object or null
function resolveAuthorsForWork(wid, datasets) {
    const live = (datasets.works || []).find(w => w.id === wid) || {};
    const by = datasets.byWork[wid] || {};
    const theos = datasets.theologians || [];

    const out = [];

    const pushTheo = (t) => {
        if (!t) return;
        if (!out.some(o => o.theo?.id === t.id || o.display === t.full_name)) {
            out.push({display: t.full_name, theo: t});
        }
    };

    const pushName = (nm) => {
        if (!nm) return;
        if (!out.some(o => o.display === nm)) {
            const t = theos.find(x => x.full_name === nm || x.name === nm);
            out.push({display: nm, theo: t || null});
        }
    };

    // 1) authors arrays (prefer live, then byWork)
    const authorLists = []
    if (Array.isArray(live.authors) && live.authors.length) authorLists.push(live.authors);
    if (Array.isArray(by.authors) && by.authors.length) authorLists.push(by.authors);

    for (const arr of authorLists) {
        for (const a of arr) {
            if (typeof a === 'string') {
                // string could be a human name OR an ID like "theo_…"
                if (/^theo_[a-f0-9]+$/i.test(a)) {
                    pushTheo(theos.find(x => x.id === a));
                } else {
                    pushName(a);
                }
            } else if (a && typeof a === 'object') {
                const id = a.id || a.theologian_id;
                if (id) {
                    pushTheo(theos.find(x => x.id === id));
                    continue;
                }
                const nm = a.full_name || a.name || a.slug;
                if (nm) pushName(nm);
            }
        }
    }

    // 2) primary/associated theologian IDs
    const candTheoIds = [
        by.primary_author_theologian_id,
        live.primary_author_theologian_id,
        by.theologian_id,
        live.theologian_id,
    ].filter(Boolean);
    for (const tid of candTheoIds) pushTheo(theos.find(x => x.id === tid));

    // 3) name fallbacks from indices/mapping
    const candNames = [
        by.primary_author_name,
        by.author_name,
        by.mapping_author_name,
        by.theologian_name,
    ].filter(Boolean);
    for (const nm of candNames) pushName(nm);

    return out;
}

/* ---------- App ---------- */
function App() {
    const router = useRouter();
    const [datasets, setDatasets] = useState(null);
    useEffect(() => {
        (async () => {
            const [topics, theologians, works, byTopic, byTheo, byWork] = await Promise.all([
                api('/api/topics'),
                api('/api/theologians'),
                api('/api/works'),
                api('/api/indices/by_topic'),
                api('/api/indices/by_theologian'),
                api('/api/indices/by_work'),
            ]);
            setDatasets({topics, theologians, works, byTopic, byTheo, byWork});
        })().catch(console.error);
    }, []);
    if (!datasets) return <div className="container">Loading…</div>;
    return (
        <RouterCtx.Provider value={router}>
            <Header/>
            <div className="container"><Routes datasets={datasets}/></div>
        </RouterCtx.Provider>
    );
}

/* ---------- Header ---------- */
function Header() {
    const go = useGo();
    const [q, setQ] = useState('');
    const [results, setResults] = useState([]);
    useEffect(() => {
        const id = setTimeout(async () => {
            if (!q) return setResults([]);
            try {
                setResults(await api('/api/search?q=' + encodeURIComponent(q)));
            } catch {
                setResults([]);
            }
        }, 180);
        return () => clearTimeout(id);
    }, [q]);

    return (
        <header>
            <a href="/" onClick={(e) => go(e, '/')}>Topics</a>
            <a href="/theologians" onClick={(e) => go(e, '/theologians')}>Theologians</a>
            <input placeholder="Search topics, theologians, works…" value={q} onChange={e => setQ(e.target.value)}/>
            {q && results.length > 0 && (
                <div className="card" style={{
                    position: 'absolute',
                    top: '56px',
                    right: '16px',
                    width: '520px',
                    maxHeight: '60vh',
                    overflow: 'auto',
                    zIndex: 30
                }}>
                    {results.map((r, i) => (
                        <div key={i} style={{padding: '6px 4px', cursor: 'pointer'}} onClick={(e) => {
                            if (r.type === 'theologian') return go(e, `/theologian/${r.slug}`);
                            if (r.type === 'topic') return go(e, `/topic/${r.slug}`);
                            if (r.type === 'work') return go(e, `/work/${r.id}`);
                            if (r.type === 'outline') return go(e, `/outline?path=${encodeURIComponent(r.markdown_path || '')}`);
                        }}>
                            <div><b>{r.name || r.title}</b> <span className="small">({r.type})</span></div>
                            {r.slug && <div className="small">{r.slug}</div>}
                        </div>
                    ))}
                </div>
            )}
        </header>
    );
}

/* ---------- Routes ---------- */
function Routes({datasets}) {
    const {path} = React.useContext(RouterCtx);
    const url = new URL(window.location.origin + path);
    // NEW: normalize route so /theologians, /theologians/, /Theologians all match
    const pathname = url.pathname.replace(/\/+$/, '').toLowerCase();

    if (pathname === '') return <Home datasets={datasets}/>;
    if (pathname === '/theologians') return <TheologiansPage datasets={datasets}/>;
    if (pathname.startsWith('/topic/')) return <TopicPage slug={decodeURIComponent(url.pathname.split('/').pop())}
                                                          datasets={datasets}/>;
    if (pathname.startsWith('/theologian/')) return <TheologianPage
        slug={decodeURIComponent(url.pathname.split('/').pop())} datasets={datasets}/>;
    if (pathname.startsWith('/work/')) return <WorkPage id={decodeURIComponent(url.pathname.split('/').pop())}
                                                        datasets={datasets}/>;
    if (pathname.startsWith('/outline')) return <OutlinePage/>;
    if (pathname.startsWith('/category/')) return <TopicCategoryPage
        slug={decodeURIComponent(url.pathname.split('/').pop())} datasets={datasets}/>;
    return <div>Not found.</div>;
}

/* ---------- Home ---------- */
function Home({datasets}) {
    const {topics} = datasets;
    const byCat = useMemo(() => topics.reduce((m, t) => {
        (m[t.category || 'Other'] ??= []).push(t);
        return m;
    }, {}), [topics]);
    const [open, setOpen] = useState({});
    const toggle = (cat) => setOpen(prev => ({...prev, [cat]: !prev[cat]}));

    return (
        <div>
            {Object.entries(byCat).map(([cat, items]) => (
                <section key={cat} style={{marginBottom: '16px'}}>
                    <div className={'section ' + (open[cat] ? 'open' : '')}>
                        <div className="section-head" onClick={() => toggle(cat)}>
                            <div className="caret">▸</div>
                            <h2><CategoryLink name={cat} stop>{cat}</CategoryLink></h2>
                        </div>
                        {open[cat] && (
                            <div className="grid">
                                {items.map(t => (
                                    <div key={t.id} className="card">
                                        <b><TopicLink topic={t}/></b>
                                        <div className="small"><CategoryLink name={t.category}/></div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </section>
            ))}
        </div>
    );
}

/* ---------- Topic Page ---------- */
function TopicPage({slug, datasets}) {
    const topic = datasets.topics.find(t => t.slug === slug);
    if (!topic) return <div>Topic not found.</div>;

    const [openWts, setOpenWts] = useState(false);
    const [openRecent, setOpenRecent] = useState(false);

    const entry = datasets.byTopic[topic.id] || {theologians: []};
    const [openTheoId, setOpenTheoId] = useState(null);
    const [openOutlinePath, setOpenOutlinePath] = useState(null);
    const [outlineHTML, setOutlineHTML] = useState('');

    const outlinesForTheo = (theologian_id) => {
        const tEntry = datasets.byTheo[theologian_id];
        if (!tEntry) return [];
        const groups = tEntry.outlines_by_topic_category || {};
        return Object.values(groups).flat().filter(o => o.topic_id === topic.id || o.topic_slug === topic.slug);
    };

    const kw = topic.key_works || {};
    const wtsIds = uniq(kw.wts_old_princeton || []);
    const recentIds = uniq(kw.recent || []);
    const liveMap = Object.fromEntries((datasets.works || []).map(w => [w.id, w]));

    function authorsForWork(wid) {
        // prefer live authors; if absent, try byWork.primary_author_theologian_id
        const live = liveMap[wid] || {};
        if (live.authors && live.authors.length) return live.authors;
        const prim = (datasets.byWork[wid] || {}).primary_author_theologian_id;
        if (!prim) return [];
        const t = datasets.theologians.find(x => x.id === prim);
        return t ? [{full_name: t.full_name, slug: t.slug}] : [];
    }

    function WorkCard({wid, bucket}) {
        const w = liveMap[wid] || {id: wid, title: wid};
        const refs = ((datasets.byWork[wid] || {}).referenced_in || []).filter(r => r.topic_id === topic.id);
        const firstOutline = refs[0]?.markdown_path;
        const authors = authorsForWork(wid);

        return (
            <div className="card" onClick={(e) => { /* allow inner links */
                if (e.target.tagName === 'A') return;
                window.history.pushState({}, '', `/work/${wid}`);
                window.dispatchEvent(new PopStateEvent('popstate'));
            }} style={{cursor: 'pointer'}}>
                {(() => {
                    const byW = datasets.byWork[wid] || {};
                    const label = workTitleWithSuffix(w, byW);
                    return <div><b><WorkLink id={wid} work={w}>{label}</WorkLink></b></div>;
                })()}

                {resolveAuthorsForWork(wid, datasets).length ? (
                  <div className="small">
                    {resolveAuthorsForWork(wid, datasets).map((a, i) => (
                      <span key={i}>
                        {i ? ', ' : ''}
                        {a.theo ? <TheoLink theo={a.theo}/> : <span>{a.display}</span>}
                      </span>
                    ))}
                  </div>
                ) : null}
                <div style={{marginTop: 6, display: 'flex', gap: 6, flexWrap: 'wrap'}}>
                    {bucket === 'WTS' ? <span className="chip">WTS</span> : <span className="chip2">Recent</span>}
                    {refs.length > 0 && <span className="count">Cited: {refs.length}</span>}
                    {firstOutline && (
                        <a className="small" href={`/outline?path=${encodeURIComponent(firstOutline)}`}
                           onClick={(e) => {
                               e.preventDefault();
                               window.history.pushState({}, '', `/outline?path=${encodeURIComponent(firstOutline)}`);
                               window.dispatchEvent(new PopStateEvent('popstate'));
                           }}>
                            Open outline
                        </a>
                    )}
                </div>
            </div>
        );
    }

    async function toggleOutline(p) {
        if (openOutlinePath === p) {
            setOpenOutlinePath(null);
            setOutlineHTML('');
            return;
        }
        setOpenOutlinePath(p);
        setOutlineHTML('Loading…');
        try {
            const r = await api('/api/outline?path=' + encodeURIComponent(p));
            setOutlineHTML(r.html);
        } catch (e) {
            setOutlineHTML('<div class="small">' + String(e).replace(/</g, '&lt;') + '</div>');
        }
    }

    async function toggleTheoCard(t) {
        const willOpen = openTheoId !== t.theologian_id;
        setOpenTheoId(willOpen ? t.theologian_id : null);
        if (willOpen) {
            const list = outlinesForTheo(t.theologian_id);
            if (list.length) {
                const p = list[0].markdown_path;
                setOpenOutlinePath(p);
                setOutlineHTML('Loading…');
                try {
                    const r = await api('/api/outline?path=' + encodeURIComponent(p));
                    setOutlineHTML(r.html);
                } catch (e) {
                    setOutlineHTML('<div class="small">' + String(e).replace(/</g, '&lt;') + '</div>');
                }
            } else {
                setOpenOutlinePath(null);
                setOutlineHTML('');
            }
        } else {
            setOpenOutlinePath(null);
            setOutlineHTML('');
        }
    }

    return (
        <div>
            <h1>
                {topic.title}{' '}
                {topic.category && <span className="badge"><CategoryLink name={topic.category}/></span>}
            </h1>

            <div style={{display: 'flex', gap: 8, flexWrap: 'wrap', margin: '4px 0 8px'}}>
                <span className="badge">WTS/Princeton: {wtsIds.length}</span>
                <span className="badge">Recent: {recentIds.length}</span>
                <span className="badge">Cited in outlines: {(topic.work_ids || []).length}</span>
            </div>

            <div className={'section ' + (openWts ? 'open' : '')}>
                <div className="section-head" onClick={() => setOpenWts(!openWts)}>
                    <div className="caret">▸</div>
                    <h3>Key Works — WTS / Old Princeton</h3><span className="count">{wtsIds.length}</span>
                </div>
                {openWts &&
                    <div className="grid two">{wtsIds.map(wid => <WorkCard key={wid} wid={wid} bucket="WTS"/>)}</div>}
            </div>

            <div className={'section ' + (openRecent ? 'open' : '')}>
                <div className="section-head" onClick={() => setOpenRecent(!openRecent)}>
                    <div className="caret">▸</div>
                    <h3>Key Works — Recent Scholarship</h3><span className="count">{recentIds.length}</span>
                </div>
                {openRecent && <div className="grid two">{recentIds.map(wid => <WorkCard key={wid} wid={wid}
                                                                                         bucket="Recent"/>)}</div>}
            </div>

            <div style={{marginTop: 18}}>
                <h3>Outlines</h3>
                <div className="grid" style={{gridTemplateColumns: '1fr'}}>
                    {entry.theologians.map(t => (
                        <div key={t.theologian_id} className="card">
                            <div className="section-head" onClick={(e) => {
                                e.stopPropagation();
                                toggleTheoCard(t);
                            }}>
                                <div className="caret">{openTheoId === t.theologian_id ? '▾' : '▸'}</div>
                                <b><TheoLink id={t.theologian_id} datasets={datasets} stop/></b>
                            </div>
                            {openTheoId === t.theologian_id && (
                                <div className="details">
                                    {outlinesForTheo(t.theologian_id).map((o, i) => {
                                        const tobj = datasets.topics.find(tt => tt.id === o.topic_id);
                                        return (
                                            <div key={i} style={{marginBottom: 12}}>
                                                <div className="toggle" onClick={() => toggleOutline(o.markdown_path)}
                                                     style={{
                                                         display: 'flex',
                                                         justifyContent: 'space-between',
                                                         alignItems: 'center',
                                                         gap: 8
                                                     }}>
                                                    <div>
                                                        <b><TopicLink topic={tobj} stop/></b>
                                                        <div className="small">updated {o.updated_at}</div>
                                                    </div>
                                                    <div
                                                        className="small">{openOutlinePath === o.markdown_path ? '▾' : '▸'}</div>
                                                </div>
                                                {openOutlinePath === o.markdown_path && (
                                                    <div style={{gridColumn: '1 / -1'}}>
                                                        <div className="markdown"
                                                             dangerouslySetInnerHTML={{__html: outlineHTML}}/>
                                                        <div className="small" style={{marginTop: 8}}>
                                                            <a href={`/outline?path=${encodeURIComponent(o.markdown_path || '')}`}
                                                               onClick={(e) => {
                                                                   e.preventDefault();
                                                                   window.history.pushState({}, '', `/outline?path=${encodeURIComponent(o.markdown_path || '')}`);
                                                                   window.dispatchEvent(new PopStateEvent('popstate'));
                                                               }}>
                                                                Open full page
                                                            </a>
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

/* ---------- Theologian Page ---------- */
function TheologianPage({slug, datasets}) {
    const theo = datasets.theologians.find(x => x.slug === slug);
    if (!theo) return <div>Theologian not found.</div>;

    const [openWorks, setOpenWorks] = useState(false);
    const [openCats, setOpenCats] = useState({});
    const [openOutlinePath, setOpenOutlinePath] = useState(null);
    const [outlineHTML, setOutlineHTML] = useState('');

    const entry = datasets.byTheo[theo.id] || {};
    const groups = entry.outlines_by_topic_category || {};

    const worksByTheo = useMemo(() => {
        const liveMap = Object.fromEntries((datasets.works || []).map(w => [w.id, w]));

        // A) from outlines (as before)
        const groups = (datasets.byTheo[theo.id]?.outlines_by_topic_category) || {};
        const allOutlines = Object.values(groups).flat();
        const idsFromOutlines = new Set(allOutlines.flatMap(o => o.key_work_ids || []));

        // Helper: does this work belong to this theologian?
        const isByTheo = (wid) => {
            const live = liveMap[wid] || {};
            const by = datasets.byWork[wid] || {};
            if (by.primary_author_theologian_id && by.primary_author_theologian_id === theo.id) return true;
            if (live.primary_author_theologian_id && live.primary_author_theologian_id === theo.id) return true;
            const authors = live.authors || by.authors || [];
            return authors.some(a =>
                a?.slug === theo.slug ||
                a?.id === theo.id ||
                a?.full_name === theo.full_name ||
                a?.name === theo.full_name
            );
        };

        // B) from topic key_works where this theologian is author
        const idsFromTopics = new Set();
        for (const t of datasets.topics || []) {
            const kw = t.key_works || {};
            for (const wid of [...(kw.wts_old_princeton || []), ...(kw.recent || [])]) {
                if (isByTheo(wid)) idsFromTopics.add(wid);
            }
        }

        // Union & dedupe by title for nicer display
        const ids = Array.from(new Set([...idsFromOutlines, ...idsFromTopics]));
        const byTitle = new Map();
        for (const wid of ids) {
            const byWork = datasets.byWork[wid] || {};
            const live = liveMap[wid] || {};
            const merged = {id: wid, ...byWork, ...live};
            const title = merged.title || wid;
            if (!byTitle.has(title)) byTitle.set(title, merged);
        }
        return Array.from(byTitle.values())
            .sort((a, b) => (a.title || '').localeCompare(b.title || ''));
    }, [datasets.byTheo, datasets.byWork, datasets.works, datasets.topics, theo.id, theo.slug, theo.full_name]);


    function WorkCardTheo({w}) {
        const topicsFeaturing = featuredTopicsForWork(w.id, datasets.topics);
        const authors = (w.authors && w.authors.length) ? w.authors : (
            (w.primary_author_theologian_id)
                ? [{...datasets.theologians.find(t => t.id === w.primary_author_theologian_id)}].filter(Boolean)
                : []
        );
        return (
            <div className="card">
                {(() => {
                  const byW = datasets.byWork[w.id] || {};
                  const label = workTitleWithSuffix(w, byW);
                  return <div><b><WorkLink id={w.id} work={w}>{label}</WorkLink></b></div>;
                })()}
                {resolveAuthorsForWork(w.id, datasets).length ? (
                  <div className="small">
                    {resolveAuthorsForWork(w.id, datasets).map((a, i) => (
                      <span key={i}>
                        {i ? ', ' : ''}
                        {a.theo ? <TheoLink theo={a.theo}/> : <span>{a.display}</span>}
                      </span>
                    ))}
                  </div>
                ) : null}

                {/*{authors.length ? <div className="small">{authors.map((a, i) => <span key={i}>{i ? ', ' : ''}<TheoLink*/}
                {/*    theo={a}/></span>)}</div> : null}*/}
                <div style={{marginTop: 6, display: 'flex', gap: 6, flexWrap: 'wrap'}}>
                    {topicsFeaturing.slice(0, 2).map((t, i) => (
                        <a key={i} className={t.bucket === 'WTS' ? 'chip' : 'chip2'} href={`/topic/${t.topic_slug}`}
                           onClick={(e) => {
                               e.preventDefault();
                               window.history.pushState({}, '', `/topic/${t.topic_slug}`);
                               window.dispatchEvent(new PopStateEvent('popstate'));
                           }}>
                            {t.bucket}: {t.title}
                        </a>
                    ))}
                    {topicsFeaturing.length > 2 && <span className="count">+{topicsFeaturing.length - 2} topics</span>}
                </div>
            </div>
        );
    }

    async function toggleTheoOutline(p) {
        if (openOutlinePath === p) {
            setOpenOutlinePath(null);
            setOutlineHTML('');
            return;
        }
        setOpenOutlinePath(p);
        setOutlineHTML('Loading…');
        try {
            const r = await api('/api/outline?path=' + encodeURIComponent(p));
            setOutlineHTML(r.html);
        } catch (e) {
            setOutlineHTML('<div className="small">' + String(e).replace(/</g, '&lt;') + '</div>');
        }
    }

    return (
        <div>
            <h1>{theo.full_name || theo.name} {theo.dates ? <span className="small">{theo.dates}</span> : null}</h1>
            {(theo.era_category || theo.eras || []).map((e, i) => <span key={i} className="badge"
                                                                        style={{marginRight: 6}}>{e}</span>)}
            {(theo.traditions || []).map((e, i) => <span key={'tr' + i} className="badge"
                                                         style={{marginRight: 6}}>{e}</span>)}

            <div className={'section ' + (openWorks ? 'open' : '')} style={{marginTop: 18}}>
                <div className="section-head" onClick={() => setOpenWorks(!openWorks)}>
                    <div className="caret">▸</div>
                    <h3>Key Works</h3>{worksByTheo.length ? <span className="count">{worksByTheo.length}</span> : null}
                </div>
                {openWorks && <div className="grid two">
                    {worksByTheo.length === 0 ? <div className="small">No works found.</div> : worksByTheo.map(w =>
                        <WorkCardTheo key={w.id} w={w}/>)}
                </div>}
            </div>

            <div style={{marginTop: 18}}>
                <h3>Outlines</h3>
                {Object.entries(groups).map(([cat, items]) => {
                    const open = !!openCats[cat];
                    const catSlug = slugify(cat);
                    return (
                        <div key={cat} className={'card section ' + (open ? 'open' : '')} style={{marginBottom: 12}}>
                            <div className="section-head"
                                 onClick={() => setOpenCats(prev => ({...prev, [cat]: !open}))}>
                                <div className="caret">▸</div>
                                <div className="small"><b><a href={`/category/${catSlug}`} onClick={(e) => {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    window.history.pushState({}, '', `/category/${catSlug}`);
                                    window.dispatchEvent(new PopStateEvent('popstate'));
                                }}>{cat}</a></b></div>
                            </div>
                            {open && items.map((it, i) => {
                                const tRec = datasets.topics.find(tt => tt.id === it.topic_id);
                                const tSlug = tRec?.slug || '';
                                return (
                                    <div key={i}
                                         style={{padding: '8px 0', borderTop: i ? '1px solid #f0f0f0' : 'none'}}>
                                        <div className="toggle" onClick={() => toggleTheoOutline(it.markdown_path)}
                                             style={{
                                                 display: 'flex',
                                                 justifyContent: 'space-between',
                                                 alignItems: 'center',
                                                 gap: 8
                                             }}>
                                            <div>
                                                {tRec ? <a href={`/topic/${tSlug}`} onClick={(e) => {
                                                    e.preventDefault();
                                                    e.stopPropagation();
                                                    window.history.pushState({}, '', `/topic/${tSlug}`);
                                                    window.dispatchEvent(new PopStateEvent('popstate'));
                                                }}><b>{tRec.title}</b></a> : <b>Untitled topic</b>}
                                                <div className="small">updated {it.updated_at}</div>
                                            </div>
                                            <div
                                                className="small">{openOutlinePath === it.markdown_path ? '▾' : '▸'}</div>
                                        </div>
                                        {openOutlinePath === it.markdown_path && (
                                            <div className="markdown" style={{marginTop: 8}}
                                                 dangerouslySetInnerHTML={{__html: outlineHTML}}/>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

/* ---------- Work Page ---------- */
function WorkPage({id, datasets}) {
    const live = (datasets.works || []).find(x => x.id === id) || {};
    const by = datasets.byWork[id] || {};
    const w = {...by, ...live, title: (live.title || by.title || id)};
    const title = workTitleWithSuffix(live, by) || w.title || id;

    const featured = featuredTopicsForWork(id, datasets.topics);
    const refs = (by.referenced_in || []);

    // resolve authors → names
    let authors = (w.authors && w.authors.length) ? w.authors : [];
    if (!authors.length && w.primary_author_theologian_id) {
        const t = datasets.theologians.find(x => x.id === w.primary_author_theologian_id);
        if (t) authors = [{full_name: t.full_name, slug: t.slug}];
    }

    return (
        <div>
            <h1>{title}</h1>
            {authors.length ? (
                <div className="small">
                    {authors.map((a, i) => <span key={i}>{i ? ', ' : ''}<TheoLink
                        theo={{slug: a.slug, full_name: a.full_name}}/></span>)}
                </div>
            ) : null}

            <h3 style={{marginTop: 16}}>Featured in Topics</h3>
            {!featured.length ? <div className="small">Not listed as a key work in any topic.</div> : (
                <div className="grid">
                    {featured.map((t, i) => (
                        <div key={i} className="card">
                            <div><b><a href={`/topic/${t.topic_slug}`} onClick={(e) => {
                                e.preventDefault();
                                window.history.pushState({}, '', `/topic/${t.topic_slug}`);
                                window.dispatchEvent(new PopStateEvent('popstate'));
                            }}>{t.title}</a></b></div>
                            <div style={{marginTop: 6}}><span
                                className={t.bucket === 'WTS' ? 'chip' : 'chip2'}>{t.bucket}</span></div>
                        </div>
                    ))}
                </div>
            )}

            <h3 style={{marginTop: 16}}>Referenced in Outlines</h3>
            {!refs.length ? <div className="small">No references yet.</div> : (
                <div className="grid">
                    {refs.map((ref, i) => {
                        const tRec = datasets.topics.find(t => t.id === ref.topic_id);
                        const tSlug = tRec?.slug;
                        return (
                            <div className="card" key={i}>
                                <div className="small">
                                    Topic: {tSlug ? <a href={`/topic/${tSlug}`} onClick={(e) => {
                                    e.preventDefault();
                                    window.history.pushState({}, '', `/topic/${tSlug}`);
                                    window.dispatchEvent(new PopStateEvent('popstate'));
                                }}>{tRec.title}</a> : ref.topic_id}
                                </div>
                                <div className="small">Theologian: <TheoLink id={ref.theologian_id}
                                                                             datasets={datasets}/></div>
                                {ref.outline_id && (
                                    <a className="small"
                                       href={`/outline?path=${encodeURIComponent(ref.markdown_path || '')}`}
                                       onClick={(e) => {
                                           e.preventDefault();
                                           window.history.pushState({}, '', `/outline?path=${encodeURIComponent(ref.markdown_path || '')}`);
                                           window.dispatchEvent(new PopStateEvent('popstate'));
                                       }}>
                                        Open outline
                                    </a>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

/* ---------- Outline standalone ---------- */
function OutlinePage() {
    const [html, setHtml] = useState('');
    useEffect(() => {
        (async () => {
            const url = new URL(window.location.href);
            const rel = url.searchParams.get('path');
            if (rel) {
                const r = await api('/api/outline?path=' + encodeURIComponent(rel));
                setHtml(r.html);
            }
        })();
    }, []);
    return <div className="markdown" dangerouslySetInnerHTML={{__html: html}}/>;
}

/* ---------- Topic Category ---------- */
function TopicCategoryPage({slug, datasets}) {
    const {topics} = datasets;
    const go = useGo();
    const {catName, items} = React.useMemo(() => {
        const sample = topics.find(t => slugify(t.category || 'Other') === slug);
        const name = sample ? sample.category : slug;
        return {catName: name, items: topics.filter(t => slugify(t.category || 'Other') === slug)};
    }, [slug, topics]);
    return (
        <div>
          <h1>{catName}</h1>
          <div className="grid">
            {items.map(t => (
              <div
                key={t.id}
                className="card"
                style={{cursor: "pointer"}}
                onClick={(e) => go(e, `/topic/${t.slug}`)}
              >
                <b>{t.title}</b>
              </div>
            ))}
          </div>
        </div>

        // <div>
        //     <h1>{catName}</h1>
        //     <div className="grid">
        //         {items.map(t => (
        //             <div key={t.id} className="card">
        //                 <b><TopicLink topic={t}/></b>
        //             </div>
        //         ))}
        //     </div>
        // </div>
    );
}

/* ---------- Theologians index ---------- */
function TheologiansPage({datasets}) {
    const list = useMemo(() => [...(datasets.theologians || [])].sort((a, b) => (a.full_name || '').localeCompare(b.full_name || '')), [datasets.theologians]);
    return (
        <div>
            <h1>Theologians</h1>
            <div className="grid two">
                {list.map(t => (
                    <div key={t.id} className="card">
                        <b><TheoLink theo={t}/></b>
                        {t.dates ? <div className="small">{t.dates}</div> : null}
                    </div>
                ))}
            </div>
        </div>
    );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
