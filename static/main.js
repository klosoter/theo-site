const {useState, useEffect, useMemo} = React;

/* ---------------- api helper ---------------- */
async function api(path) {
    const r = await fetch(path);
    const ct = r.headers.get("content-type") || "";
    if (!ct.includes("application/json")) throw new Error(`Expected JSON from ${path}`);
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
}

const slugify = (s) =>
    (s || "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-") // non-alnum -> -
        .replace(/^-+|-+$/g, "") // trim leading/trailing -
        .replace(/\.+$/g, "");

/* ---------- router ---------- */
function useRouter() {
    const [path, setPath] = useState(window.location.pathname + window.location.search);
    useEffect(() => {
        const onPop = () => setPath(window.location.pathname + window.location.search);
        window.addEventListener("popstate", onPop);
        return () => window.removeEventListener("popstate", onPop);
    }, []);
    const navigate = (to) => {
        window.history.pushState({}, "", to);
        setPath(to);
    };
    return {path, navigate};
}

const RouterCtx = React.createContext();

/* ---------- NEW: link helpers (always canonical) ---------- */
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
    const slug = slugify(name || "other");
    const to = `/category/${slug}`;
    return (
        <a href={to} className={className} onClick={(e) => go(e, to, !!stop)}>
            {children || name}
        </a>
    );
}

function TopicLink({topic, children, className, stop}) {
    const go = useGo();
    if (!topic) return <span>{children}</span>;
    const to = `/topic/${topic.slug}`;
    return (
        <a href={to} className={className} onClick={(e) => go(e, to, !!stop)}>
            {children || topic.title}
        </a>
    );
}

function TheoLink({theo, id, datasets, children, className, stop}) {
    const go = useGo();
    const t = theo || (datasets?.theologians || []).find((x) => x.id === id);
    if (!t) return <span className={className}>{children || id}</span>;
    const to = `/theologian/${t.slug}`;
    return (
        <a href={to} className={className} onClick={(e) => go(e, to, !!stop)}>
            {children || t.full_name}
        </a>
    );
}

function WorkLink({work, id, datasets, children, className, stop}) {
    const go = useGo();
    const canonMap = datasets?.canonMap || {};
    const wid = work?.id || id;
    const cid = canonMap[wid] || wid; // always link to canonical id
    const w = (datasets?.works || []).find((x) => x.id === cid) || work || {id: cid};
    const to = `/work/${cid}`;
    return (
        <a href={to} className={className} onClick={(e) => go(e, to, !!stop)}>
            {children || w.title || cid}
        </a>
    );
}

function workTitleWithSuffix(liveWork = {}, byWork = {}) {
    const title = liveWork.title || byWork.title || "";
    const suffix =
        liveWork.reference ||
        liveWork.title_suffix ||
        liveWork.suffix ||
        byWork.reference ||
        byWork.title_suffix ||
        byWork.suffix ||
        "";
    return title; // suffix kept for future if you want to display it
}

function enhanceKeyWorks(html, keyWorkIds, datasets) {
    if (!html || !Array.isArray(keyWorkIds) || keyWorkIds.length === 0) return html;

    const parser = new DOMParser();
    const doc = parser.parseFromString(html, "text/html");

    // Find a "Key Works" header (H2/H3/H4 or a bold 'Key Works')
    const isKW = (el) => /key\s*works/i.test(el.textContent || "");
    let header = [...doc.querySelectorAll("h1,h2,h3,h4,strong,b")].find(isKW);
    if (!header) return html;

    // The list immediately after the header
    let list = header.nextElementSibling;
    if (!list || !/^(UL|OL)$/i.test(list.tagName)) return html;

    const canonMap = datasets?.canonMap || {};
    const lis = [...list.querySelectorAll("li")];
    const n = Math.min(lis.length, keyWorkIds.length);

    for (let i = 0; i < n; i++) {
        const li = lis[i];
        const wid = keyWorkIds[i];
        const cid = canonMap[wid] || wid;

        const title = (li.textContent || "").trim();
        li.textContent = "";

        const a = doc.createElement("a");
        a.href = `/work/${cid}`;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = title + " ↗";     // new-tab indicator
        li.appendChild(a);
    }

    return doc.body.innerHTML;
}

/* ---------- featured topics for a work (canonical-aware) ---------- */
function featuredTopicsForWork(canonId, topics, reverseCanonMap) {
    const aliasIds = new Set([canonId, ...(reverseCanonMap?.[canonId] || [])]);

    const out = [];
    for (const t of topics || []) {
        const kw = t.key_works || {};
        const wtsSet = new Set(kw.wts_old_princeton || []);
        const recentSet = new Set(kw.recent || []);

        let inWts = false,
            inRecent = false;
        for (const id of aliasIds) {
            if (wtsSet.has(id)) inWts = true;
            if (recentSet.has(id)) inRecent = true;
            if (inWts && inRecent) break;
        }

        if (inWts || inRecent) {
            out.push({
                topic_id: t.id,
                topic_slug: t.slug,
                title: t.title,
                bucket: inWts && inRecent ? ["WTS", "Recent"] : inWts ? ["WTS"] : ["Recent"],
            });
        }
    }
    return out;
}

/* ---------- ordering helpers for categories/topics ---------- */
const parseCategoryKey = (name = "") => {
    const m = String(name).match(/^\s*(\d+)\s*\./);
    return m ? parseInt(m[1], 10) : Number.MAX_SAFE_INTEGER;
};

// "5.A Nature and origin of sin" -> [5, "A"]
const parseTopicKey = (topicTitle = "") => {
    const m = String(topicTitle).match(/^\s*(\d+)\s*\.\s*([A-Z])/i);
    if (!m) return [Number.MAX_SAFE_INTEGER, ""];
    return [parseInt(m[1], 10), m[2].toUpperCase()];
};

function parseTopicKeyFromSlug(slug) {
    // e.g., "5-b-original-sin-and-imputation" -> [5, "b"]
    const m = /^(\d+)-([a-z])\b/.exec(slug || "");
    return [parseInt(m?.[1] || "0", 10), m?.[2] || ""];
}

/* ---------- Resolve authors for a work ---------- */
function resolveAuthorsForWork(wid, datasets) {
    const live = (datasets.works || []).find((w) => w.id === wid) || {};
    const by = datasets.byWork[wid] || {};
    const theos = datasets.theologians || [];
    const out = [];

    const pushTheo = (t) => {
        if (!t) return;
        if (!out.some((o) => o.theo?.id === t.id || o.display === t.full_name)) {
            out.push({display: t.full_name, theo: t});
        }
    };

    const pushName = (nm) => {
        if (!nm) return;
        if (!out.some((o) => o.display === nm)) {
            const t = theos.find((x) => x.full_name === nm || x.name === nm);
            out.push({display: nm, theo: t || null});
        }
    };

    // authors arrays (prefer live, then byWork)
    const authorLists = [];
    if (Array.isArray(live.authors) && live.authors.length) authorLists.push(live.authors);
    if (Array.isArray(by.authors) && by.authors.length) authorLists.push(by.authors);

    for (const arr of authorLists) {
        for (const a of arr) {
            if (typeof a === "string") {
                if (/^theo_[a-f0-9]+$/i.test(a)) {
                    pushTheo(theos.find((x) => x.id === a));
                } else {
                    pushName(a);
                }
            } else if (a && typeof a === "object") {
                const id = a.id || a.theologian_id;
                if (id) {
                    pushTheo(theos.find((x) => x.id === id));
                    continue;
                }
                const nm = a.full_name || a.name || a.slug;
                if (nm) pushName(nm);
            }
        }
    }

    // primary/associated theologian IDs
    const candTheoIds = [
        by.primary_author_theologian_id,
        live.primary_author_theologian_id,
        by.theologian_id,
        live.theologian_id,
    ].filter(Boolean);
    for (const tid of candTheoIds) pushTheo(theos.find((x) => x.id === tid));

    // name fallbacks
    const candNames = [by.primary_author_name, by.author_name, by.mapping_author_name, by.theologian_name].filter(Boolean);
    for (const nm of candNames) pushName(nm);

    return out;
}

function WorkRow({wid, datasets, badge, count}) {
    const go = useGo();
    const w = (datasets.works || []).find(x => x.id === wid) || {id: wid, title: wid};
    const byW = datasets.byWork[wid] || {};
    const label = workTitleWithSuffix(w, byW);
    const authors = resolveAuthorsForWork(wid, datasets);

    return (
        <div className="work-row" onClick={(e) => go(e, `/work/${wid}`)}>
            <div className="work-main">
                <b>
                    <WorkLink id={wid} work={w} datasets={datasets}>
                        {label}
                    </WorkLink>
                </b>
                {authors.length ? (
                    <span className="muted">
            {" — "}
                        {authors.map((a, i) => (
                            <span key={i}>
                                {i ? ", " : ""}
                                <TheoLink theo={a.theo}></TheoLink>
                            </span>
                        ))}
          </span>
                ) : null}
            </div>
            <div className="work-meta">
                {badge ? <span className={badge === "WTS" ? "chip" : "chip2"}>{badge}</span> : null}
                <span className="badge">{count || 0}</span>
            </div>
        </div>
    );
}

/* ---------- Reusable Outline list (identical item markup) ---------- */
function OutlineList({items, datasets}) {
    const [openPath, setOpenPath] = React.useState(null);
    const [html, setHtml] = React.useState("");

    async function toggleOutline(item) {
        const p = item?.markdown_path;
        if (!p) return;

        if (openPath === p) {
            setOpenPath(null);
            setHtml("");
            return;
        }
        setOpenPath(p);
        setHtml("Loading…");
        try {
            const r = await api("/api/outline?path=" + encodeURIComponent(p));
            const keyIds = (item && item.key_work_ids && item.key_work_ids.length)
                ? item.key_work_ids
                : (r.meta && r.meta.key_work_ids) || [];
            const enhanced = enhanceKeyWorks(r.html, keyIds, datasets);
            setHtml(enhanced);
        } catch (e) {
            setHtml('<div class="small">' + String(e).replace(/</g, "&lt;") + "</div>");
        }
    }

    return (
        <div>
            {items.map((it, i) => {
                const topic =
                    (it.topic_slug && (datasets.topics || []).find(t => t.slug === it.topic_slug)) ||
                    (it.topic_id && (datasets.topics || []).find(t => t.id === it.topic_id)) ||
                    null;
                const topicSlug = topic?.slug || it.topic_slug || "";
                const topicTitle = topic?.title || it.topic_title || "Untitled topic";

                return (
                    <div key={i} style={{marginBottom: 12}}>
                        <div
                            className="toggle"
                            onClick={() => toggleOutline(it)}   // <-- pass whole item
                            style={{display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8}}
                        >
                            <div>
                                {topic ? (
                                    <a
                                        href={`/topic/${topicSlug}`}
                                        onClick={(e) => {
                                            e.preventDefault();
                                            e.stopPropagation();
                                            window.history.pushState({}, "", `/topic/${topicSlug}`);
                                            window.dispatchEvent(new PopStateEvent("popstate"));
                                        }}
                                    >
                                        <b>{topicTitle}</b>
                                    </a>
                                ) : (
                                    <b>{topicTitle}</b>
                                )}
                                {it.updated_at ? <div className="small">updated {it.updated_at}</div> : null}
                            </div>
                            <div className="small">{openPath === it.markdown_path ? "▾" : "▸"}</div>
                        </div>

                        {openPath === it.markdown_path && (
                            <div style={{gridColumn: "1 / -1"}}>
                                <div className="markdown" dangerouslySetInnerHTML={{__html: html}}/>
                                <div className="small" style={{marginTop: 8}}>
                                    <a
                                        href={`/outline?path=${encodeURIComponent(it.markdown_path || "")}`}
                                        onClick={(e) => {
                                            e.preventDefault();
                                            window.history.pushState({}, "", `/outline?path=${encodeURIComponent(it.markdown_path || "")}`);
                                            window.dispatchEvent(new PopStateEvent("popstate"));
                                        }}
                                    >
                                        Open full page
                                    </a>
                                </div>
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}

/* ---------- THEO HELPERS + badges ---------- */
const SUFFIXES = new Set(["jr.", "sr.", "ii", "iii", "iv", "v"]);

function lastNameKey(full = "") {
    const parts = String(full).trim().split(/\s+/);
    if (parts.length === 0) return "";
    const last = parts[parts.length - 1];
    const maybeSuffix = last.replace(/\.$/, "").toLowerCase();
    const idx = SUFFIXES.has(maybeSuffix) && parts.length >= 2 ? parts.length - 2 : parts.length - 1;
    return parts[idx].toLowerCase();
}

function getEra(theo = {}) {
    if (theo.era && (theo.era.label || theo.era.slug)) {
        return {label: theo.era.label || theo.era.slug, start: theo.era.start ?? 99999, end: theo.era.end ?? 99999};
    }
    const label = (theo.era_category || (theo.eras || [])[0] || "").toString();
    return {label, start: 99999, end: 99999};
}

function getTraditionLabel(theo = {}) {
    if (theo.tradition && (theo.tradition.label || theo.tradition.slug)) return theo.tradition.label || theo.tradition.slug;
    return (theo.tradition_label || theo.tradition_slug || (theo.traditions || [])[0] || "Other").toString();
}

function birthYear(theo = {}) {
    return Number.isFinite(theo.birth_year) ? theo.birth_year : 99999;
}

function TheoBadges({theo}) {
    const era = getEra(theo);
    const trad = getTraditionLabel(theo);
    return (
        <>
            {era.label ? <span className="badge" style={{marginRight: 6}}>{era.label}</span> : null}
            {trad ? <span className="badge" style={{marginRight: 6}}>{trad}</span> : null}
        </>
    );
}

function TheoRow({theo, hasClick = true, className = "card", children}) {
    const go = useGo();

    const clickableProps = hasClick
        ? {onClick: (e) => go(e, `/theologian/${theo.slug}`)}
        : {};

    return (
        <div
            className={className}
            style={{
                cursor: hasClick ? "pointer" : "default",
                // padding: "10px 12px"
            }}
            {...clickableProps}
        >
            <div
                style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    justifyContent: "space-between",
                    flexWrap: "wrap"
                }}
            >
                {/* left: name + badges */}
                <div style={{display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap"}}>
                    <b><TheoLink theo={theo}/></b>
                    <div className="small" style={{display: "flex", gap: 6, flexWrap: "wrap"}}>
                        <TheoBadges theo={theo}/>
                    </div>
                </div>

                {/* right: dates + any children (like caret) */}
                <div style={{display: "flex", alignItems: "center", gap: 8}}>
                    {theo.dates ? <div className="small">{theo.dates}</div> : null}
                    {children}
                </div>
            </div>
        </div>
    );
}

function TheoCard({theo, onClick}) {
    return (
        <div className="card" style={{cursor: "pointer"}} onClick={onClick}>
            <b>
                <TheoLink theo={theo} stop/>
            </b>
            {theo.dates ? <div className="small">{theo.dates}</div> : null}
            <div style={{marginTop: 6}}>
                <TheoBadges theo={theo}/>
            </div>
        </div>
    );
}

/* ---------- App ---------- */
function App() {
    const router = useRouter();
    const [datasets, setDatasets] = useState(null);
    useEffect(() => {
        (async () => {
            const [topics, theologians, works, byTopic, byTheo, byWork, canonMap, reverseCanonMap, canonCountsTheo, canonCountsTopic] =
                await Promise.all([
                    api("/api/topics"),
                    api("/api/theologians"),
                    api("/api/works"),
                    api("/api/indices/by_topic"),
                    api("/api/indices/by_theologian"),
                    api("/api/indices/by_work"),
                    api("/api/works/canon_map"),
                    api("/api/works/reverse_canon_map"),
                    api("/api/indices/canon_counts_by_theologian"),
                    api("/api/indices/canon_counts_by_topic"),
                ]);
            setDatasets({
                topics,
                theologians,
                works,
                byTopic,
                byTheo,
                byWork,
                canonMap,
                reverseCanonMap,
                canonCountsTheo, // {theoId: [{id: canonicalWorkId, count}]}
                canonCountsTopic, // {topicId: {WTS: [{id,count}], Recent: [{id,count}]}}
            });
        })().catch(console.error);
    }, []);
    if (!datasets) return <div className="container">Loading…</div>;
    return (
        <RouterCtx.Provider value={router}>
            <Header/>
            <div className="container">
                <Routes datasets={datasets}/>
            </div>
        </RouterCtx.Provider>
    );
}

/* ---------- Header ---------- */
function Header() {
    const go = useGo();
    const [q, setQ] = useState("");
    const [results, setResults] = useState([]);
    const [open, setOpen] = useState(false);        // controls visibility
    const boxRef = React.useRef(null);              // for outside-click

    // debounce search + control "open"
    useEffect(() => {
        const id = setTimeout(async () => {
            const query = q.trim();
            if (!query) {
                setResults([]);
                setOpen(false);
                return;
            }
            try {
                const r = await api("/api/search?q=" + encodeURIComponent(query));
                setResults(r);
                setOpen(r.length > 0);
            } catch {
                setResults([]);
                setOpen(false);
            }
        }, 180);
        return () => clearTimeout(id);
    }, [q]);

    // close on outside click or Esc
    useEffect(() => {
        function onDocClick(e) {
            if (!boxRef.current) return;
            if (!boxRef.current.contains(e.target)) setOpen(false);
        }

        function onKey(e) {
            if (e.key === "Escape") setOpen(false);
        }

        document.addEventListener("mousedown", onDocClick);
        window.addEventListener("keydown", onKey);
        return () => {
            document.removeEventListener("mousedown", onDocClick);
            window.removeEventListener("keydown", onKey);
        };
    }, []);

    // navigate + close dropdown
    const select = (e, to) => {
        setOpen(false);
        setResults([]);
        setQ("");            // also clear the input so it doesn’t re-open
        go(e, to);
    };

    return (
        <header ref={boxRef}>
            <a href="/" onClick={(e) => select(e, "/")}>Topics</a>
            <a href="/theologians" onClick={(e) => select(e, "/theologians")}>Theologians</a>

            <input
                placeholder="Search topics, theologians, works…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onFocus={() => setOpen((results || []).length > 0)}
            />

            {open && results.length > 0 && (
                <div
                    className="card"
                    style={{
                        position: "absolute",
                        top: "56px",
                        right: "16px",
                        width: "520px",
                        maxHeight: "60vh",
                        overflow: "auto",
                        zIndex: 30,
                    }}
                >
                    {results.map((r, i) => {
                        const to =
                            r.type === "theologian" ? `/theologian/${r.slug}` :
                                r.type === "topic" ? `/topic/${r.slug}` :
                                    r.type === "work" ? `/work/${r.id}` :
                                        r.type === "outline" ? `/outline?path=${encodeURIComponent(r.markdown_path || "")}` :
                                            "/";
                        return (
                            <div
                                key={i}
                                style={{padding: "6px 4px", cursor: "pointer"}}
                                onClick={(e) => select(e, to)}
                            >
                                <div><b>{r.name || r.title}</b> <span className="small">({r.type})</span></div>
                                {r.slug && <div className="small">{r.slug}</div>}
                            </div>
                        );
                    })}
                </div>
            )}
        </header>
    );
}

/* ---------- Routes ---------- */
function Routes({datasets}) {
    const {path} = React.useContext(RouterCtx);
    const url = new URL(window.location.origin + path);
    const pathname = url.pathname.replace(/\/+$/, "").toLowerCase();

    if (pathname === "") return <Home datasets={datasets}/>;
    if (pathname === "/theologians") return <TheologiansPage datasets={datasets}/>;
    if (pathname.startsWith("/topic/"))
        return <TopicPage slug={decodeURIComponent(url.pathname.split("/").pop())} datasets={datasets}/>;
    if (pathname.startsWith("/theologian/"))
        return <TheologianPage slug={decodeURIComponent(url.pathname.split("/").pop())} datasets={datasets}/>;
    if (pathname.startsWith("/work/"))
        return <WorkPage id={decodeURIComponent(url.pathname.split("/").pop())} datasets={datasets}/>;
    if (pathname.startsWith("/outline")) return <OutlinePage/>;
    if (pathname.startsWith("/category/"))
        return <TopicCategoryPage slug={decodeURIComponent(url.pathname.split("/").pop())} datasets={datasets}/>;
    return <div>Not found.</div>;
}

/* ---------- Home ---------- */
function Home({datasets}) {
    const {topics} = datasets;
    const byCat = useMemo(() => {
        return topics.reduce((m, t) => {
            (m[t.category || "Other"] ??= []).push(t);
            return m;
        }, {});
    }, [topics]);
    const [open, setOpen] = useState({});
    const toggle = (cat) => setOpen((prev) => ({...prev, [cat]: !prev[cat]}));

    return (
        <div>
            {Object.entries(byCat).map(([cat, items]) => (
                <section key={cat} style={{marginBottom: "16px"}}>
                    <div className={"section " + (open[cat] ? "open" : "")}>
                        <div className="section-head" onClick={() => toggle(cat)}>
                            <div className="caret">▸</div>
                            <h2>
                                <CategoryLink name={cat} stop>
                                    {cat}
                                </CategoryLink>
                            </h2>
                        </div>
                        {open[cat] && (
                            <div className="grid">
                                {items.map((t) => (
                                    <div key={t.id} className="card">
                                        <b>
                                            <TopicLink topic={t}/>
                                        </b>
                                        <div className="small">
                                            <CategoryLink name={t.category}/>
                                        </div>
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

/* ---------- Topic Page (canonical-only) ---------- */

/* ---------- Topic Page (canonical-only) ---------- */
// function TopicPage({slug, datasets}) {
//     const topic = datasets.topics.find(t => t.slug === slug);
//     if (!topic) return <div>Topic not found.</div>;
//
//     const [openWts, setOpenWts] = useState(false);
//     const [openRecent, setOpenRecent] = useState(false);
//
//     const entry = datasets.byTopic[topic.id] || {theologians: []};
//     const [openTheoId, setOpenTheoId] = useState(null);
//
//     // for outline preview
//     const [openOutlinePath, setOpenOutlinePath] = useState(null);
//     const [outlineHTML, setOutlineHTML] = useState('');
//
//     const outlinesForTheo = (theologian_id) => {
//         const tEntry = datasets.byTheo[theologian_id];
//         if (!tEntry) return [];
//         const groups = tEntry.outlines_by_topic_category || {};
//         // these items already include `key_work_ids` (use them!)
//         return Object.values(groups)
//             .flat()
//             .filter(o => o.topic_id === topic.id || o.topic_slug === topic.slug);
//     };
//
//     const canonCounts = datasets.canonCountsTopic[topic.id] || {WTS: [], Recent: []};
//
//     function WorkCard({wid, bucket, compact}) {
//         const w = (datasets.works || []).find(x => x.id === wid) || {id: wid, title: wid};
//         const authorsDisplay = resolveAuthorsForWork(wid, datasets);
//
//         return (
//             <div
//                 className={'card' + (compact ? ' work-row' : '')}
//                 onClick={(e) => {
//                     if (e.target.tagName === 'A') return;
//                     window.history.pushState({}, '', `/work/${wid}`);
//                     window.dispatchEvent(new PopStateEvent('popstate'));
//                 }}
//                 style={{cursor: 'pointer'}}
//             >
//                 {(() => {
//                     const byW = datasets.byWork[wid] || {};
//                     const label = workTitleWithSuffix(w, byW);
//                     return <div><b><WorkLink id={wid} work={w} datasets={datasets}>{label}</WorkLink></b></div>;
//                 })()}
//
//                 {authorsDisplay.length ? (
//                     <div className={compact ? 'meta' : 'small'}>
//                         {authorsDisplay.map((a, i) => (
//                             <span key={i}>
//               {i ? ', ' : ''}
//                                 {a.theo ? <TheoLink theo={a.theo}/> : <span>{a.display}</span>}
//             </span>
//                         ))}
//                     </div>
//                 ) : null}
//
//                 <div style={{
//                     marginTop: compact ? 4 : 6,
//                     display: 'flex',
//                     gap: 6,
//                     flexWrap: 'wrap',
//                     alignItems: 'center'
//                 }}>
//                     <span className={bucket === 'WTS' ? 'chip' : 'chip2'}>{bucket}</span>
//                     <span className="badge">{(canonCounts[bucket] || []).find(x => x.id === wid)?.count || 0}</span>
//                 </div>
//             </div>
//         );
//     }
//
//     // UPDATED: accept the whole outline item so we can use key_work_ids
//     async function toggleOutline(item) {
//         const p = item?.markdown_path;
//         if (!p) return;
//
//         if (openOutlinePath === p) {
//             setOpenOutlinePath(null);
//             setOutlineHTML('');
//             return;
//         }
//
//         setOpenOutlinePath(p);
//         setOutlineHTML('Loading…');
//         try {
//             const r = await api('/api/outline?path=' + encodeURIComponent(p));
//             // prefer item.key_work_ids; fall back to front-matter
//             const keyIds = (item.key_work_ids && item.key_work_ids.length)
//                 ? item.key_work_ids
//                 : (r.meta && r.meta.key_work_ids) || [];
//             const enhanced = enhanceKeyWorks(r.html, keyIds, datasets);
//             setOutlineHTML(enhanced);
//         } catch (e) {
//             setOutlineHTML('<div class="small">' + String(e).replace(/</g, '&lt;') + '</div>');
//         }
//     }
//
//     async function toggleTheoCard(t) {
//         const willOpen = openTheoId !== t.theologian_id;
//         setOpenTheoId(willOpen ? t.theologian_id : null);
//
//         // auto-load first outline when opening
//         if (willOpen) {
//             const list = outlinesForTheo(t.theologian_id);
//             if (list.length) {
//                 const first = list[0];
//                 setOpenOutlinePath(first.markdown_path);
//                 setOutlineHTML('Loading…');
//                 try {
//                     const r = await api('/api/outline?path=' + encodeURIComponent(first.markdown_path));
//                     const keyIds = (first.key_work_ids && first.key_work_ids.length)
//                         ? first.key_work_ids
//                         : (r.meta && r.meta.key_work_ids) || [];
//                     const enhanced = enhanceKeyWorks(r.html, keyIds, datasets);
//                     setOutlineHTML(enhanced);
//                 } catch (e) {
//                     setOutlineHTML('<div class="small">' + String(e).replace(/</g, '&lt;') + '</div>');
//                 }
//             } else {
//                 setOpenOutlinePath(null);
//                 setOutlineHTML('');
//             }
//         } else {
//             setOpenOutlinePath(null);
//             setOutlineHTML('');
//         }
//     }
//
//     return (
//         <div>
//             <h1>
//                 {topic.title}{' '}
//                 {topic.category && <span className="badge"><CategoryLink name={topic.category}/></span>}
//             </h1>
//
//             <div style={{display: 'flex', gap: 8, flexWrap: 'wrap', margin: '4px 0 8px'}}>
//                 <span className="badge">WTS/Princeton: {(canonCounts.WTS || []).length}</span>
//                 <span className="badge">Recent: {(canonCounts.Recent || []).length}</span>
//                 <span className="badge">Cited in outlines: {(topic.work_ids || []).length}</span>
//             </div>
//             {/* Key Works buckets */}
//             {(() => {
//                 const renderBucket = (label, bucketKey, open, setOpen) => (
//                     <div className={'section ' + (open ? 'open' : '')}>
//                         <div className="section-head" onClick={() => setOpen(!open)}>
//                             <div className="caret">▸</div>
//                             <h3>Key Works — {label}</h3>
//                             <span className="count">{(canonCounts[bucketKey] || []).length}</span>
//                         </div>
//                         {open && (
//                             <div className="work-list">
//                                 {(canonCounts[bucketKey] || []).map(({id}) => (
//                                     <WorkCard key={id} wid={id} bucket={bucketKey} compact/>
//                                 ))}
//                             </div>
//                         )}
//
//                     </div>
//                 );
//
//                 return (
//                     <>
//                         {renderBucket('WTS / Old Princeton', 'WTS', openWts, setOpenWts)}
//                         {renderBucket('Recent Scholarship', 'Recent', openRecent, setOpenRecent)}
//                     </>
//                 );
//             })()}
//
//
//             <div style={{marginTop: 18}}>
//                 <h3>Outlines</h3>
//                 <div className="grid" style={{gridTemplateColumns: '1fr'}}>
//                     {entry.theologians.map(t => (
//                         <div key={t.theologian_id} className="card">
//                             <div className="section-head" onClick={(e) => {
//                                 e.stopPropagation();
//                                 toggleTheoCard(t);
//                             }}>
//                                 <div className="caret">{openTheoId === t.theologian_id ? '▾' : '▸'}</div>
//                                 <b><TheoLink id={t.theologian_id} datasets={datasets} stop/></b>
//                             </div>
//
//                             {openTheoId === t.theologian_id && (
//                                 <div className="details">
//                                     {outlinesForTheo(t.theologian_id).map((o, i) => {
//                                         const tobj = datasets.topics.find(tt => tt.id === o.topic_id);
//                                         return (
//                                             <div key={i} style={{marginBottom: 12}}>
//                                                 <div
//                                                     className="toggle"
//                                                     onClick={() => toggleOutline(o)}
//                                                     style={{
//                                                         display: 'flex',
//                                                         justifyContent: 'space-between',
//                                                         alignItems: 'center',
//                                                         gap: 8
//                                                     }}
//                                                 >
//                                                     <div>
//                                                         <b><TopicLink topic={tobj} stop/></b>
//                                                         <div className="small">updated {o.updated_at}</div>
//                                                     </div>
//                                                     <div
//                                                         className="small">{openOutlinePath === o.markdown_path ? '▾' : '▸'}</div>
//                                                 </div>
//
//                                                 {openOutlinePath === o.markdown_path && (
//                                                     <div style={{gridColumn: '1 / -1'}}>
//                                                         <div className="markdown"
//                                                              dangerouslySetInnerHTML={{__html: outlineHTML}}/>
//                                                         <div className="small" style={{marginTop: 8}}>
//                                                             <a
//                                                                 href={`/outline?path=${encodeURIComponent(o.markdown_path || '')}`}
//                                                                 onClick={(e) => {
//                                                                     e.preventDefault();
//                                                                     window.history.pushState({}, '', `/outline?path=${encodeURIComponent(o.markdown_path || '')}`);
//                                                                     window.dispatchEvent(new PopStateEvent('popstate'));
//                                                                 }}
//                                                             >
//                                                                 Open full page
//                                                             </a>
//                                                         </div>
//                                                     </div>
//                                                 )}
//                                             </div>
//                                         );
//                                     })}
//                                 </div>
//                             )}
//                         </div>
//                     ))}
//                 </div>
//             </div>
//         </div>
//     );
// }
//

function TopicPage({slug, datasets}) {
    const topic = datasets.topics.find(t => t.slug === slug);
    if (!topic) return <div>Topic not found.</div>;

    const [openWts, setOpenWts] = useState(false);
    const [openRecent, setOpenRecent] = useState(false);

    const entry = datasets.byTopic[topic.id] || {theologians: []};
    const [openTheoId, setOpenTheoId] = useState(null);

    const [openOutlinePath, setOpenOutlinePath] = useState(null);
    const [outlineHTML, setOutlineHTML] = useState("");

    const outlinesForTheo = (theologian_id) => {
        const tEntry = datasets.byTheo[theologian_id];
        if (!tEntry) return [];
        const groups = tEntry.outlines_by_topic_category || {};
        return Object.values(groups).flat().filter(o => o.topic_id === topic.id || o.topic_slug === topic.slug);
    };

    const canonCounts = datasets.canonCountsTopic[topic.id] || {WTS: [], Recent: []};

    async function toggleOutline(item) {
        const p = item?.markdown_path;
        if (!p) return;
        if (openOutlinePath === p) {
            setOpenOutlinePath(null);
            setOutlineHTML("");
            return;
        }
        setOpenOutlinePath(p);
        setOutlineHTML("Loading…");
        try {
            const r = await api("/api/outline?path=" + encodeURIComponent(p));
            const keyIds = (item.key_work_ids && item.key_work_ids.length) ? item.key_work_ids : (r.meta && r.meta.key_work_ids) || [];
            const enhanced = enhanceKeyWorks(r.html, keyIds, datasets);
            setOutlineHTML(enhanced);
        } catch (e) {
            setOutlineHTML('<div class="small">' + String(e).replace(/</g, "&lt;") + "</div>");
        }
    }

    async function toggleTheoCard(t) {
        const willOpen = openTheoId !== t.theologian_id;
        setOpenTheoId(willOpen ? t.theologian_id : null);
        if (willOpen) {
            const list = outlinesForTheo(t.theologian_id);
            if (list.length) {
                const first = list[0];
                setOpenOutlinePath(first.markdown_path);
                setOutlineHTML("Loading…");
                try {
                    const r = await api("/api/outline?path=" + encodeURIComponent(first.markdown_path));
                    const keyIds = (first.key_work_ids && first.key_work_ids.length) ? first.key_work_ids : (r.meta && r.meta.key_work_ids) || [];
                    const enhanced = enhanceKeyWorks(r.html, keyIds, datasets);
                    setOutlineHTML(enhanced);
                } catch (e) {
                    setOutlineHTML('<div class="small">' + String(e).replace(/</g, "&lt;") + "</div>");
                }
            } else {
                setOpenOutlinePath(null);
                setOutlineHTML("");
            }
        } else {
            setOpenOutlinePath(null);
            setOutlineHTML("");
        }
    }

    const [openEra, setOpenEra] = useState({});
    const theosByEra = useMemo(() => {
        const map = new Map();
        for (const t of entry.theologians || []) {
            const T = (datasets.theologians || []).find(x => x.id === t.theologian_id);
            if (!T) continue;
            const era = getEra(T);
            const key = `${era.start}|||${era.label}`;
            if (!map.has(key)) map.set(key, {label: era.label, start: era.start, items: []});
            map.get(key).items.push(T);
        }
        return [...map.values()].sort((a, b) => a.start - b.start || a.label.localeCompare(b.label));
    }, [entry.theologians, datasets.theologians]);

    return (
        <div>
            <h1>
                {topic.title}{" "}
                {topic.category && <span className="badge"><CategoryLink name={topic.category}/></span>}
            </h1>

            <div style={{display: "flex", gap: 8, flexWrap: "wrap", margin: "4px 0 8px"}}>
                <span className="badge">WTS/Princeton: {(canonCounts.WTS || []).length}</span>
                <span className="badge">Recent: {(canonCounts.Recent || []).length}</span>
                <span className="badge">Cited in outlines: {(topic.work_ids || []).length}</span>
            </div>

            <div className={"section " + (openWts ? "open" : "")}>
                <div className="section-head" onClick={() => setOpenWts(!openWts)}>
                    <div className="caret">▸</div>
                    <h3>Key Works — WTS / Old Princeton</h3>
                    <span className="count">{(canonCounts.WTS || []).length}</span>
                </div>
                {openWts && (
                    <div className="work-list">
                        {(canonCounts.WTS || []).map(({id}) => (
                            <WorkRow
                                key={id}
                                wid={id}
                                datasets={datasets}
                                badge="WTS"
                                count={(canonCounts.WTS || []).find(x => x.id === id)?.count || 0}
                            />
                        ))}
                    </div>
                )}
            </div>

            <div className={"section " + (openRecent ? "open" : "")}>
                <div className="section-head" onClick={() => setOpenRecent(!openRecent)}>
                    <div className="caret">▸</div>
                    <h3>Key Works — Recent Scholarship</h3>
                    <span className="count">{(canonCounts.Recent || []).length}</span>
                </div>
                {openRecent && (
                    <div className="work-list">
                        {(canonCounts.Recent || []).map(({id}) => (
                            <WorkRow
                                key={id}
                                wid={id}
                                datasets={datasets}
                                badge="Recent"
                                count={(canonCounts.Recent || []).find(x => x.id === id)?.count || 0}
                            />
                        ))}
                    </div>
                )}
            </div>

            <div style={{marginTop: 18}}>
                <h3>Outlines</h3>
                <div className="grid" style={{gridTemplateColumns: "1fr", gap: 6}}>
                    {theosByEra.map(era => {
                        const opened = !!openEra[era.label];
                        return (
                            <div key={era.label} className={"section " + (opened ? "open" : "")}
                                 style={{marginBottom: 6}}>
                                <div className="section-head"
                                     onClick={() => setOpenEra(s => ({...s, [era.label]: !opened}))}>
                                    <div className="caret">▸</div>
                                    <div className="small"><b>{era.label}</b></div>
                                    <span className="count">{era.items.length}</span>
                                </div>

                                {opened && (
                                    <div>
                                        {era.items
                                            .sort((a, b) => birthYear(a) - birthYear(b) || lastNameKey(a.full_name).localeCompare(lastNameKey(b.full_name)))
                                            .map(T => {
                                                const outs = outlinesForTheo(T.id);
                                                return (
                                                    <div>

                                                        <div
                                                            className="section-head"
                                                            style={{
                                                                marginLeft: 14,
                                                                display: "flex",
                                                                alignItems: "center",
                                                                gap: 6,
                                                                cursor: "pointer"
                                                            }}
                                                            onClick={(e) => {
                                                                e.stopPropagation();
                                                                toggleTheoCard({theologian_id: T.id});
                                                            }}
                                                        >
                                                            <div className="caret">
                                                                {openTheoId === T.id ? "▾" : "▸"}
                                                            </div>
                                                            <TheoRow key={T.id} theo={T} hasClick={false} className=""/>
                                                        </div>


                                                        {openTheoId === T.id && (
                                                            <div className="details">
                                                                {outs.map((o, i) => {
                                                                    const tobj = datasets.topics.find(tt => tt.id === o.topic_id);
                                                                    return (
                                                                        <div key={i} style={{marginBottom: 12}}>
                                                                            <div
                                                                                className="toggle"
                                                                                onClick={() => toggleOutline(o)}
                                                                                style={{
                                                                                    display: "flex",
                                                                                    justifyContent: "space-between",
                                                                                    alignItems: "center",
                                                                                    gap: 8
                                                                                }}
                                                                            >
                                                                                <div>
                                                                                    <b><TopicLink topic={tobj}
                                                                                                  stop/></b>
                                                                                    <div
                                                                                        className="small">updated {o.updated_at}</div>
                                                                                </div>
                                                                                <div
                                                                                    className="small">{openOutlinePath === o.markdown_path ? "▾" : "▸"}</div>
                                                                            </div>

                                                                            {openOutlinePath === o.markdown_path && (
                                                                                <div style={{gridColumn: "1 / -1"}}>
                                                                                    <div className="markdown"
                                                                                         dangerouslySetInnerHTML={{__html: outlineHTML}}/>
                                                                                    <div className="small"
                                                                                         style={{marginTop: 8}}>
                                                                                        <a
                                                                                            href={`/outline?path=${encodeURIComponent(o.markdown_path || "")}`}
                                                                                            onClick={(e) => {
                                                                                                e.preventDefault();
                                                                                                window.history.pushState({}, "", `/outline?path=${encodeURIComponent(o.markdown_path || "")}`);
                                                                                                window.dispatchEvent(new PopStateEvent("popstate"));
                                                                                            }}
                                                                                        >
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
                                                );
                                            })}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}

/* ---------- Theologian Page (canonical-only) ---------- */
function TheologianPage({slug, datasets}) {
    const theo = datasets.theologians.find((x) => x.slug === slug);
    if (!theo) return <div>Theologian not found.</div>;

    const [openWorks, setOpenWorks] = useState(false);
    const [openCats, setOpenCats] = useState({});
    const [openOutlinePath, setOpenOutlinePath] = useState(null);
    const [outlineHTML, setOutlineHTML] = useState("");
    const [aboutOpen, setAboutOpen] = useState(true);


    const entry = datasets.byTheo[theo.id] || {};
    const groups = entry.outlines_by_topic_category || {};
    const canonList = datasets.canonCountsTheo[theo.id] || []; // [{id,count}]

    function WorkCardTheo({wId, compact}) {
        const w = (datasets.works || []).find(x => x.id === wId) || {id: wId, title: wId};
        const topicsFeaturing = featuredTopicsForWork(w.id, datasets.topics, datasets.reverseCanonMap);
        const authors = resolveAuthorsForWork(w.id, datasets);

        return (
            <div className={'card' + (compact ? ' work-row' : '')}>
                <div><b><WorkLink id={w.id} work={w}
                                  datasets={datasets}>{workTitleWithSuffix(w, datasets.byWork[w.id] || {})}</WorkLink></b>
                </div>
                {authors.length ? (
                    <div className={compact ? 'meta' : 'small'}>
                        {authors.map((a, i) => <span key={i}>{i ? ', ' : ''}{a.theo ?
                            <TheoLink theo={a.theo}/> : a.display}</span>)}
                    </div>
                ) : null}
                <div style={{
                    marginTop: compact ? 4 : 6,
                    display: 'flex',
                    gap: 6,
                    flexWrap: 'wrap',
                    alignItems: 'center'
                }}>
                    <span
                        className="badge">{(datasets.canonCountsTheo[theo.id] || []).find(x => x.id === w.id)?.count || 0}</span>
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
            setOutlineHTML("");
            return;
        }
        setOpenOutlinePath(p);
        setOutlineHTML("Loading…");
        try {
            const r = await api("/api/outline?path=" + encodeURIComponent(p));
            setOutlineHTML(r.html);
        } catch (e) {
            setOutlineHTML('<div className="small">' + String(e).replace(/</g, "&lt;") + "</div>");
        }
    }

    const aboutCounts = {
        timeline: Array.isArray(theo.timeline) ? theo.timeline.length : 0,
        themes: Array.isArray(theo.themes) ? theo.themes.length : 0,
    };

    return (
        <div>
            <h1>
                {theo.full_name || theo.name} {theo.dates ? <span className="small">{theo.dates}</span> : null}
            </h1>
            <TheoBadges theo={theo}/>
            <div className="card" style={{marginTop: 12, padding: 0}}>
                <div className={'section ' + (aboutOpen ? 'open' : '')}>
                    <div className="section-head" onClick={() => setAboutOpen(!aboutOpen)}>
                        <div className="caret">▸</div>
                        <h3 style={{margin: 0}}>About</h3>
                    </div>

                    {aboutOpen && (
                        <div style={{padding: 16}}>
                            {theo.bio ? (
                                <div className="prose" style={{marginBottom: 16}}>{theo.bio}</div>
                            ) : null}

                            {Array.isArray(theo.timeline) && theo.timeline.length ? (
                                <div style={{marginTop: 10}}>
                                    <h4>Timeline</h4>
                                    <ul className="timeline">
                                        {[...theo.timeline]
                                            .sort((a, b) => (a.year ?? 0) - (b.year ?? 0))
                                            .map((evt, i) => (
                                                <li key={i}>
                                                    <span className="yr">{evt.year}</span>
                                                    <span className="evt">{evt.event}</span>
                                                </li>
                                            ))}
                                    </ul>
                                </div>
                            ) : null}

                            {Array.isArray(theo.themes) && theo.themes.length ? (
                                <div style={{marginTop: 10}}>
                                    <h4>Themes</h4>
                                    <ul className="theme-list">
                                        {theo.themes.map((t, i) => (
                                            <li key={i}>
                                                <b>{t.label}.</b> {t.gloss}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            ) : null}
                        </div>
                    )}
                </div>
            </div>


            <div className={"section " + (openWorks ? "open" : "")} style={{marginTop: 18}}>
                <div className="section-head" onClick={() => setOpenWorks(!openWorks)}>
                    <div className="caret">▸</div>
                    <h3>Canonical Works</h3>
                    {canonList.length ? <span className="count">{canonList.length}</span> : null}
                </div>
                {openWorks && (
                    <div className="work-list">
                        {canonList.length === 0 ? (
                            <div className="small">No works found.</div>
                        ) : (
                            canonList.map(({id}) => (
                                <WorkRow
                                    key={id}
                                    wid={id}
                                    datasets={datasets}
                                    count={(datasets.canonCountsTheo[theo.id] || []).find(x => x.id === id)?.count || 0}
                                />
                            ))
                        )}
                    </div>
                )}


            </div>

            <div style={{marginTop: 18}}>
                <h3>Outlines</h3>
                {Object.entries(groups)
                    .sort(([a], [b]) => parseCategoryKey(a) - parseCategoryKey(b))
                    .map(([cat, items]) => {
                        const open = !!openCats[cat];
                        const catSlug = slugify(cat);

                        const normalized = [...items]
                            .sort((a, b) => {
                                const tA = datasets.topics.find((tt) => tt.id === a.topic_id);
                                const tB = datasets.topics.find((tt) => tt.id === b.topic_id);
                                const [na, la] = parseTopicKeyFromSlug(tA?.slug);
                                const [nb, lb] = parseTopicKeyFromSlug(tB?.slug);
                                return na !== nb ? na - nb : la.localeCompare(lb);
                            })
                            .map((it) => {
                                const tRec = datasets.topics.find((tt) => tt.id === it.topic_id);
                                return {
                                    topic_id: it.topic_id,
                                    topic_slug: tRec?.slug || "",
                                    topic_title: tRec?.title || "Untitled topic",
                                    markdown_path: it.markdown_path,
                                    updated_at: it.updated_at,
                                    key_work_ids: it.key_work_ids || [],
                                };
                            });

                        return (
                            <div key={cat} className={"card section " + (open ? "open" : "")}
                                 style={{marginBottom: 12}}>
                                <div className="section-head"
                                     onClick={() => setOpenCats((prev) => ({...prev, [cat]: !open}))}>
                                    <div className="caret">▸</div>
                                    <div className="small">
                                        <b>
                                            <a
                                                href={`/category/${catSlug}`}
                                                onClick={(e) => {
                                                    e.preventDefault();
                                                    e.stopPropagation();
                                                    window.history.pushState({}, "", `/category/${catSlug}`);
                                                    window.dispatchEvent(new PopStateEvent("popstate"));
                                                }}
                                            >
                                                {cat}
                                            </a>
                                        </b>
                                    </div>
                                </div>
                                {open && <OutlineList items={normalized} datasets={datasets}/>}
                            </div>
                        );
                    })}
            </div>
        </div>
    );
};

/* ---------- Work Page (canonical-only; alias redirects) ---------- */
function WorkPage({id, datasets}) {
    const go = useGo();

    // canonicalize id & redirect if needed
    const canonMap = datasets.canonMap || {};
    const canonicalId = canonMap[id] || id;
    React.useEffect(() => {
        if (id !== canonicalId) {
            go(null, `/work/${canonicalId}`, true);
        }
    }, [id, canonicalId]);

    const live = (datasets.works || []).find((x) => x.id === canonicalId) || {};
    const by = datasets.byWork[canonicalId] || {};
    const w = {...by, ...live, id: canonicalId, title: live.title || by.title || canonicalId};
    const title = workTitleWithSuffix(live, by) || w.title || canonicalId;

    const authors = resolveAuthorsForWork(canonicalId, datasets);
    const featured = featuredTopicsForWork(canonicalId, datasets.topics, datasets.reverseCanonMap);

    const [openCats, setOpenCats] = React.useState({});
    const groups = React.useMemo(() => {
        const refs = by.referenced_in || [];
        const tmap = new Map((datasets.topics || []).map((t) => [t.id, t]));

        const byCat = {};
        for (const ref of refs) {
            const t = tmap.get(ref.topic_id) || {};
            const cat = t.category || "Other";
            (byCat[cat] ??= []).push({
                topic_id: t.id,
                topic_slug: t.slug,
                topic_title: t.title || ref.topic_id, // title like "5.A …"
                markdown_path: ref.markdown_path,
                updated_at: ref.updated_at,
            });
        }

        const sortedEntries = Object.entries(byCat).sort(([a], [b]) => parseCategoryKey(a) - parseCategoryKey(b));
        for (const [, items] of sortedEntries) {
            items.sort((ta, tb) => {
                const [na, la] = parseTopicKey(ta.topic_title);
                const [nb, lb] = parseTopicKey(tb.topic_title);
                if (na !== nb) return na - nb;
                return la.localeCompare(lb);
            });
        }
        const out = {};
        for (const [cat, items] of sortedEntries) out[cat] = items;
        return out;
    }, [by.referenced_in, datasets.topics]);

    return (
        <div>
            <h1>{title}</h1>

            {authors.length ? (
                <div className="small">
                    {authors.map((a, i) => (
                        <span key={i}>
              {i ? ", " : ""}
                            {a.theo ? <TheoLink theo={a.theo}/> : <span>{a.display}</span>}
            </span>
                    ))}
                </div>
            ) : null}

            {featured.length ? (
                <div style={{marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap"}}>
                    {featured.slice(0, 4).map((t, i) => (
                        <a
                            key={i}
                            className={t.bucket === "WTS" ? "chip" : "chip2"}
                            href={`/topic/${t.topic_slug}`}
                            onClick={(e) => {
                                e.preventDefault();
                                window.history.pushState({}, "", `/topic/${t.topic_slug}`);
                                window.dispatchEvent(new PopStateEvent("popstate"));
                            }}
                        >
                            {t.bucket}: {t.title}
                        </a>
                    ))}
                    {featured.length > 4 && <span className="count">+{featured.length - 4} topics</span>}
                </div>
            ) : null}

            <div style={{marginTop: 18}}>
                <h3>Outlines</h3>

                {Object.keys(groups).length === 0 ? (
                    <div className="small">No references yet.</div>
                ) : (
                    Object.entries(groups)
                        .sort(([a], [b]) => parseCategoryKey(a) - parseCategoryKey(b))
                        .map(([cat, items]) => {
                            const open = !!openCats[cat];
                            const catSlug = slugify(cat);
                            return (
                                <div key={cat} className={"card section " + (open ? "open" : "")}
                                     style={{marginBottom: 12}}>
                                    <div className="section-head"
                                         onClick={() => setOpenCats((prev) => ({...prev, [cat]: !open}))}>
                                        <div className="caret">▸</div>
                                        <div className="small">
                                            <b>
                                                <a
                                                    href={`/category/${catSlug}`}
                                                    onClick={(e) => {
                                                        e.preventDefault();
                                                        e.stopPropagation();
                                                        window.history.pushState({}, "", `/category/${catSlug}`);
                                                        window.dispatchEvent(new PopStateEvent("popstate"));
                                                    }}
                                                >
                                                    {cat}
                                                </a>
                                            </b>
                                        </div>
                                    </div>
                                    {open && <OutlineList items={items} datasets={datasets}/>}
                                </div>
                            );
                        })
                )}
            </div>
        </div>
    );
}

/* ---------- Outline standalone ---------- */
function OutlinePage() {
    const [html, setHtml] = useState("");
    useEffect(() => {
        (async () => {
            const url = new URL(window.location.href);
            const rel = url.searchParams.get("path");
            if (rel) {
                const r = await api("/api/outline?path=" + encodeURIComponent(rel));
                setHtml(r.html);
            }
        })();
    }, []);
    return <div className="markdown" dangerouslySetInnerHTML={{__html: html}}/>;
}

/* ---------- Topic Category ---------- */
function TopicCategoryPage({slug, datasets}) {
    const go = useGo();
    const {topics} = datasets;
    const {catName, items} = React.useMemo(() => {
        const sample = topics.find((t) => slugify(t.category || "Other") === slug);
        const name = sample ? sample.category : slug;
        return {catName: name, items: topics.filter((t) => slugify(t.category || "Other") === slug)};
    }, [slug, topics]);
    return (
        <div>
            <h1>{catName}</h1>
            <div className="grid">
                {items.map((t) => (
                    <div key={t.id} className="card" style={{cursor: "pointer"}}
                         onClick={(e) => go(e, `/topic/${t.slug}`)}>
                        <b>{t.title}</b>
                    </div>
                ))}
            </div>
        </div>
    );
}

/* ---------- Theologians index (sortable, with badges) ---------- */
function TheologiansPage({datasets}) {
    const go = useGo();

    // remember mode across visits (default: alphabetical)
    const MODE_KEY = "theologians_sort_mode";
    const [mode, setMode] = React.useState(() => {
        try {
            return localStorage.getItem(MODE_KEY) || "alpha";
        } catch {
            return "alpha";
        }
    });
    React.useEffect(() => {
        try {
            localStorage.setItem(MODE_KEY, mode);
        } catch {
        }
    }, [mode]);

    // collapse state for grouped view
    const [openEra, setOpenEra] = React.useState({});
    const [openTrad, setOpenTrad] = React.useState({});

    const list = useMemo(() => [...(datasets.theologians || [])], [datasets.theologians]);

    // helpers
    const cmpAlpha = (a, b) =>
        lastNameKey(a.full_name).localeCompare(lastNameKey(b.full_name)) ||
        (a.full_name || "").localeCompare(b.full_name || "");
    const cmpBirth = (a, b) => birthYear(a) - birthYear(b) || cmpAlpha(a, b);

    // grouped render: Era → Tradition → (rows)
    const renderEraMode = () => {
        // group by era
        const eraGroups = new Map();
        for (const t of list) {
            const era = getEra(t);
            const key = `${era.start}|||${era.label}`;
            if (!eraGroups.has(key)) eraGroups.set(key, []);
            eraGroups.get(key).push(t);
        }
        const sortedEras = [...eraGroups.keys()].sort((A, B) => {
            const [sa, la] = A.split("|||");
            const [sb, lb] = B.split("|||");
            return Number(sa) - Number(sb) || la.localeCompare(lb);
        });

        return (
            <>
                {sortedEras.map((ekey) => {
                    const [, label] = ekey.split("|||");
                    const eraList = eraGroups.get(ekey) || [];

                    // tradition buckets within era
                    const tradGroups = new Map();
                    for (const t of eraList) {
                        const tr = getTraditionLabel(t);
                        if (!tradGroups.has(tr)) tradGroups.set(tr, []);
                        tradGroups.get(tr).push(t);
                    }

                    const sortedTrads =
                        mode === "trad_count"
                            ? [...tradGroups.keys()].sort(
                                (a, b) =>
                                    (tradGroups.get(b)?.length || 0) - (tradGroups.get(a)?.length || 0) ||
                                    a.localeCompare(b)
                            )
                            : [...tradGroups.keys()].sort((a, b) => a.localeCompare(b));

                    const eOpen = !!openEra[label];
                    return (
                        <section key={ekey} style={{marginBottom: 16}}>
                            <div className={"section " + (eOpen ? "open" : "")}>
                                <div
                                    className="section-head"
                                    onClick={() => setOpenEra((s) => ({...s, [label]: !eOpen}))}
                                >
                                    <div className="caret">▸</div>
                                    <h2>{label}</h2>
                                    <span className="count">{eraList.length}</span>
                                </div>

                                {eOpen && (
                                    <div>
                                        {sortedTrads.map((tr) => {
                                            const tid = `${label}:::${tr}`;
                                            const tOpen = !!openTrad[tid];
                                            const items = (tradGroups.get(tr) || []).sort(
                                                (mode === "trad" || mode === "trad_count") ? cmpAlpha : cmpBirth
                                            );

                                            return (
                                                <div key={tid} className={"card section " + (tOpen ? "open" : "")}
                                                     style={{marginBottom: 12}}>
                                                    <div
                                                        className="section-head"
                                                        onClick={() => setOpenTrad((s) => ({...s, [tid]: !tOpen}))}
                                                    >
                                                        <div className="caret">▸</div>
                                                        <div className="small"><b>{tr}</b></div>
                                                        <span className="count">{items.length}</span>
                                                    </div>

                                                    {tOpen && (
                                                        <div>
                                                            {items.map((t) => <TheoRow key={t.id} theo={t}/>)}
                                                        </div>
                                                    )}
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        </section>
                    );
                })}
            </>
        );
    };

    // flat render: simple list of rows
    const renderFlat = (arr) => (
        <div>
            {arr.map((t) => <TheoRow key={t.id} theo={t}/>)}
        </div>
    );

    // choose body
    let body = null;
    if (mode === "era" || mode === "trad" || mode === "trad_count") {
        body = renderEraMode();
    } else if (mode === "alpha") {
        body = renderFlat([...list].sort(cmpAlpha));
    } else if (mode === "birth") {
        body = renderFlat([...list].sort(cmpBirth));
    }

    return (
        <div>
            <h1>Theologians</h1>

            {/* Sort control */}
            <div className="sortbar">
                <label className="sortbar-label" htmlFor="sort-mode">Sort</label>
                <div className="select-wrap">
                    <select
                        id="sort-mode"
                        className="select"
                        value={mode}
                        onChange={(e) => setMode(e.target.value)}
                    >
                        <option value="alpha">Alphabetical (last name)</option>
                        <option value="birth">By Birth Year</option>
                        <option value="era">Era → Tradition → Birth year</option>
                        <option value="trad">Tradition → Alphabetical</option>
                        <option value="trad_count">Tradition → By Count</option>
                    </select>
                </div>
            </div>


            {body}
        </div>
    );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
