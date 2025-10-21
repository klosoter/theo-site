const { useState, useEffect, useMemo, useRef, createContext, useContext } = React;

/* ---------------- api + tiny utils ---------------- */
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
    .replace(/[^a-z0-9&]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/\.+$/g, "");

// Accept dotted/undotted suffixes, case-insensitive.
const SUFFIXES = new Set(["jr","sr","ii","iii","iv","v"]);

function stripSuffix(parts) {
  // parts: array of tokens (already trimmed)
  if (!parts.length) return parts;
  const last = parts[parts.length - 1].replace(/\./g, "").toLowerCase();
  if (SUFFIXES.has(last)) return parts.slice(0, -1);
  return parts;
}

// Alpha key that ignores suffixes and supports "Last, First" and "First Last".
function alphaKey(full = "") {
  const raw = String(full || "").trim();

  // Handle "Last, First Middle" format
  if (raw.includes(",")) {
    const [left, right] = raw.split(",", 2);
    const last = left.trim();
    const rightParts = right.trim().split(/\s+/).filter(Boolean);
    const noSuf = stripSuffix(rightParts);
    const firstRest = noSuf.join(" ").trim();
    return { last: last.toLowerCase(), firstRest: firstRest.toLowerCase() };
  }

  // Handle "First Middle Last [Suffix]" format
  const parts = raw.split(/\s+/).filter(Boolean);
  const noSuf = stripSuffix(parts);
  if (!noSuf.length) return { last: "", firstRest: "" };
  const last = noSuf[noSuf.length - 1];
  const firstRest = noSuf.slice(0, -1).join(" ");
  return { last: last.toLowerCase(), firstRest: firstRest.toLowerCase() };
}

// Use this everywhere you need the sortable last name key (e.g., for section headers).
function lastNameKey(full = "") {
  return alphaKey(full).last || "";
}

function birthYear(theo = {}) {
  return Number.isFinite(theo.birth_year) ? theo.birth_year : 99999;
}
function getEra(theo = {}) {
  if (theo.era && (theo.era.label || theo.era.slug)) {
    return { label: theo.era.label || theo.era.slug, start: theo.era.start ?? 99999, end: theo.era.end ?? 99999 };
  }
  const label = (theo.era_category || (theo.eras || [])[0] || "Other").toString();
  return { label, start: 99999, end: 99999 };
}
function getTraditionLabel(theo = {}) {
  if (theo.tradition && (theo.tradition.label || theo.tradition.slug)) return theo.tradition.label || theo.tradition.slug;
  return (theo.tradition_label || theo.tradition_slug || (theo.traditions || [])[0] || "Other").toString();
}
const parseCategoryKey = (name = "") => {
  const m = String(name).match(/^\s*(\d+)\s*\./);
  return m ? parseInt(m[1], 10) : Number.MAX_SAFE_INTEGER;
};
function parseTopicKeyFromSlug(slug) {
  const m = /^(\d+)-([a-z])\b/.exec(slug || "");
  return [parseInt(m?.[1] || "0", 10), m?.[2] || ""];
}

/* ---------------- router ---------------- */
function useRouter() {
  const [path, setPath] = useState(window.location.pathname + window.location.search);
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname + window.location.search);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const navigate = (to) => {
    if (!to || typeof to !== "string") return;
    window.history.pushState({}, "", to);
    setPath(to);
  };
  return { path, navigate };
}
const RouterCtx = createContext();
function useGo() {
  const { navigate } = useContext(RouterCtx) || {};
  return (e, to, stop = false) => {
    if (e) {
      e.preventDefault();
      if (stop) e.stopPropagation();
    }
    if (to) navigate(to);
  };
}

/* ---------------- links ---------------- */
function CategoryLink({ name, children, className, stop }) {
  const go = useGo();
  const slug = slugify(name || "other");
  const to = `/category/${slug}`;
  return (
    <a href={to} className={className} onClick={(e) => go(e, to, !!stop)}>
      {children || name}
    </a>
  );
}
function TopicLink({ topic, children, className, stop }) {
  const go = useGo();
  if (!topic) return <span>{children}</span>;
  const to = `/topic/${topic.slug}`;
  return (
    <a href={to} className={className} onClick={(e) => go(e, to, !!stop)}>
      {children || topic.title}
    </a>
  );
}
function TheoLink({ theo, id, datasets, children, className, stop }) {
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
function WorkLink({ work, id, datasets, children, className, stop }) {
  const go = useGo();
  const canonMap = datasets?.canonMap || {};
  const wid = work?.id || id;
  const cid = canonMap[wid] || wid;
  const w = (datasets?.works || []).find((x) => x.id === cid) || work || { id: cid };
  const to = `/work/${cid}`;
  return (
    <a href={to} className={className} onClick={(e) => go(e, to, !!stop)}>
      {children || w.title || cid}
    </a>
  );
}

/* ---------------- small data helpers for works/outlines ---------------- */
function workTitleWithSuffix(liveWork = {}, byWork = {}) {
  return liveWork.title || byWork.title || "";
}
function resolveAuthorsForWork(wid, datasets) {
  const live = (datasets.works || []).find((w) => w.id === wid) || {};
  const by = datasets.byWork[wid] || {};
  const theos = datasets.theologians || [];
  const out = [];
  const pushTheo = (t) => {
    if (!t) return;
    if (!out.some((o) => o.theo?.id === t.id || o.display === t.full_name)) {
      out.push({ display: t.full_name, theo: t });
    }
  };
  const pushName = (nm) => {
    if (!nm) return;
    if (!out.some((o) => o.display === nm)) {
      const t = theos.find((x) => x.full_name === nm || x.name === nm);
      out.push({ display: nm, theo: t || null });
    }
  };
  const authorLists = [];
  if (Array.isArray(live.authors) && live.authors.length) authorLists.push(live.authors);
  if (Array.isArray(by.authors) && by.authors.length) authorLists.push(by.authors);
  for (const arr of authorLists) {
    for (const a of arr) {
      if (typeof a === "string") {
        if (/^theo_[a-f0-9]+$/i.test(a)) pushTheo(theos.find((x) => x.id === a));
        else pushName(a);
      } else if (a && typeof a === "object") {
        const id = a.id || a.theologian_id;
        if (id) pushTheo(theos.find((x) => x.id === id));
        else pushName(a.full_name || a.name || a.slug);
      }
    }
  }
  const candTheoIds = [
    by.primary_author_theologian_id,
    live.primary_author_theologian_id,
    by.theologian_id,
    live.theologian_id,
  ].filter(Boolean);
  for (const tid of candTheoIds) pushTheo(theos.find((x) => x.id === tid));
  const candNames = [by.primary_author_name, by.author_name, by.mapping_author_name, by.theologian_name].filter(Boolean);
  for (const nm of candNames) pushName(nm);
  return out;
}
function featuredTopicsForWork(canonId, topics, reverseCanonMap) {
  const aliasIds = new Set([canonId, ...(reverseCanonMap?.[canonId] || [])]);
  const out = [];
  for (const t of topics || []) {
    const kw = t.key_works || {};
    const wtsSet = new Set(kw.wts_old_princeton || []);
    const recentSet = new Set(kw.recent || []);
    let inWts = false, inRecent = false;
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

/* ---------------- HTML enhancer used by outlines ---------------- */
function enhanceKeyWorks(html, keyWorkIds, datasets) {
  if (!html || !Array.isArray(keyWorkIds) || keyWorkIds.length === 0) return html;
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");
  const isKW = (el) => /key\s*works/i.test(el.textContent || "");
  let header = [...doc.querySelectorAll("h1,h2,h3,h4,strong,b")].find(isKW);
  if (!header) return html;
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
    a.textContent = title + " ↗";
    li.appendChild(a);
  }
  return doc.body.innerHTML;
}

/* ---------------- shared UI primitives ---------------- */
function Collapsible({ open, onToggle, title, right, children, sticky = false }) {
  return (
    <div className={"section" + (open ? " open" : "")}>
      <div className={"section-head" + (sticky ? " sticky-head" : "")} onClick={onToggle} role="button" aria-expanded={open ? "true" : "false"}>
        <div className="caret">▸</div>
        <div style={{ flex: 1, minWidth: 0 }}>{title}</div>
        {right}
      </div>
      {open && <div className="details">{children}</div>}
    </div>
  );
}

function SortBar({ value = "birth", onChange, storageKey }) {
  return (
    <div className="sortbar">
      <label className="sortbar-label" htmlFor={storageKey}>Sort</label>
      <div className="select-wrap">
        <select
          id={storageKey}
          className="select"
          value={value}
          onChange={(e) => onChange?.(e.target.value)}
        >
          <option value="birth">By Birth Year</option>
          <option value="alpha">Alphabetical (last name)</option>
          <option value="era">Era → Birth year</option>
          <option value="trad">Tradition → Alphabetical</option>
        </select>
      </div>
    </div>
  );
}

/* ---------------- Outline preview (inline loader) ---------------- */
function OutlinePreview({ item, datasets }) {
  const [open, setOpen] = useState(false);
  const [html, setHtml] = useState("");
  const [loading, setLoading] = useState(false);
  const to = `/outline?path=${encodeURIComponent(item.markdown_path || "")}`;

  async function toggle() {
    const will = !open;
    setOpen(will);
    if (will && !html && !loading) {
      setLoading(true);
      try {
        const r = await api("/api/outline?path=" + encodeURIComponent(item.markdown_path));
        const keyIds = item.key_work_ids?.length ? item.key_work_ids : (r.meta?.key_work_ids || []);
        setHtml(enhanceKeyWorks(r.html, keyIds, datasets));
      } catch (e) {
        setHtml('<div class="small">' + String(e).replace(/</g, "&lt;") + "</div>");
      } finally {
        setLoading(false);
      }
    }
  }

  return (
    <div style={{ marginBottom: 12 }}>
      <div className="section-head sticky-head" onClick={toggle} style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div className="caret">{open ? "▾" : "▸"}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <b>{item.topic_title || item.topic_slug || "Outline"}</b>
        </div>
      </div>
      {open && (
        <div style={{ gridColumn: "1 / -1" }}>
          <div className="markdown" dangerouslySetInnerHTML={{ __html: html }} />
          <div className="small" style={{ marginTop: 8 }}>
            <a
              href={to}
              onClick={(e) => {
                e.preventDefault();
                window.history.pushState({}, "", to);
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
}

/* ---------------- UniversalPage (group → subgroup → rows) ---------------- */

function smartCompareKeys(A, B) {
    const num = (k) => {
      const m = String(k).match(/^\s*(\d+(?:\.\d+)*)/);
      return m ? m[1].split(".").map(n => parseInt(n, 10)) : null;
    };
    const a = num(A), b = num(B);
    if (a && b) {
      const L = Math.max(a.length, b.length);
      for (let i = 0; i < L; i++) {
        const da = a[i] ?? 0, db = b[i] ?? 0;
        if (da !== db) return da - db;
      }
    }
    return String(A).localeCompare(String(B));
  }
function UniversalPage({ title, items, levels, renderRow, emptyText = "No items." }) {
  if (!items || !items.length) {
    return (
      <div>
        {title ? <h1>{title}</h1> : null}
        <div className="small">{emptyText}</div>
      </div>
    );
  }

  function groupBy(arr, keyFn) {
    const map = new Map();
    for (const it of arr) {
      const k = keyFn(it);
      if (!map.has(k)) map.set(k, []);
      map.get(k).push(it);
    }
    return [...map.entries()];
  }

  function Level({ idx, arr }) {
    if (idx >= levels.length) return <div>{arr.map(renderRow)}</div>;

    const cfg = levels[idx] || {};
    const entries = groupBy(arr, cfg.key);

    // If we must preserve incoming order, sort groups by the index of their first appearance.
    if (cfg.preserveOrder) {
      const firstIndex = new Map();
      // record the first index each key appears in original arr
      for (let i = 0; i < arr.length; i++) {
        const k = cfg.key(arr[i]);
        if (!firstIndex.has(k)) firstIndex.set(k, i);
      }
      entries.sort((a, b) => (firstIndex.get(a[0]) ?? 0) - (firstIndex.get(b[0]) ?? 0));
    } else {
      // otherwise, use explicit sort or smartCompareKeys
      entries.sort(cfg.sort || ((a, b) => smartCompareKeys(a[0], b[0])));
    }

    return (
      <>
        {entries.map(([groupKey, groupItems]) => (
          <Group
            key={String(groupKey)}
            idx={idx}
            cfg={cfg}
            groupKey={groupKey}
            groupItems={cfg.itemSort ? [...groupItems].sort(cfg.itemSort) : groupItems}
          />
        ))}
      </>
    );
  }

  function Group({ idx, cfg, groupKey, groupItems }) {
    const [open, setOpen] = React.useState(!!cfg.startOpen);
    const titleEl = cfg.label ? cfg.label(groupKey, groupItems) : <b>{String(groupKey)}</b>;
    const rightEl = cfg.right ? cfg.right(groupKey, groupItems) : null;
    return (
      <section style={{ marginBottom: 12 }}>
        <Collapsible open={open} onToggle={() => setOpen((o) => !o)} title={titleEl} right={rightEl} sticky />
        {open && (
          <div style={{ marginLeft: idx ? 12 : 0 }}>
            <Level idx={idx + 1} arr={groupItems} />
          </div>
        )}
      </section>
    );
  }

  return (
    <div>
      {title ? <h1>{title}</h1> : null}
      <Level idx={0} arr={items} />
    </div>
  );
}

/* ---------------- Search (header) ---------------- */
function GlobalSearch() {
  const go = useGo();
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const boxRef = useRef(null);

  useEffect(() => {
    const id = setTimeout(async () => {
      const query = q.trim();
      if (!query) { setResults([]); setOpen(false); setHighlight(-1); return; }
      try {
        const r = await api("/api/search?q=" + encodeURIComponent(query));
        setResults(r);
        setHighlight(r.length > 0 ? 0 : -1);
        setOpen(r.length > 0);
      } catch {
        setResults([]); setOpen(false); setHighlight(-1);
      }
    }, 180);
    return () => clearTimeout(id);
  }, [q]);

  useEffect(() => {
    function onDoc(e) {
      if (!boxRef.current) return;
      if (!boxRef.current.contains(e.target)) {
        setOpen(false);
        setHighlight(-1);
      }
    }
    function onKey(e) {
      if (e.key === "Escape") { setOpen(false); setHighlight(-1); }
    }
    document.addEventListener("mousedown", onDoc);
    window.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); window.removeEventListener("keydown", onKey); };
  }, []);

  const select = (e, to) => { setOpen(false); setResults([]); setQ(""); go(e, to); };

  const handleKey = (e) => {
    if (!open || results.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => (h + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => (h - 1 + results.length) % results.length);
    } else if (e.key === "Enter" && highlight >= 0) {
      e.preventDefault();
      const r = results[highlight];
      const to =
        r.type === "theologian" ? `/theologian/${r.slug}` :
        r.type === "topic" ? `/topic/${r.slug}` :
        r.type === "work" ? `/work/${r.id}` :
        r.type === "essay" ? `/essay/${r.slug}` :
        r.type === "digest" ? `/digest/${r.slug}` :
        r.type === "outline" ? `/outline?path=${encodeURIComponent(r.markdown_path || "")}` : "/";
      select(e, to);
    }
  };

  return (
    <div ref={boxRef} style={{ position: "relative" }}>
      <input
        placeholder="Search topics, theologians, works, essays…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => setOpen((results || []).length > 0)}
        onKeyDown={handleKey}
      />
      {open && results.length > 0 && (
        <div className="card" style={{ position: "absolute", top: "48px", right: 0, width: "520px", maxHeight: "60vh", overflow: "auto", zIndex: 30 }}>
          {results.map((r, i) => {
            const to =
              r.type === "theologian" ? `/theologian/${r.slug}` :
              r.type === "topic" ? `/topic/${r.slug}` :
              r.type === "work" ? `/work/${r.id}` :
              r.type === "essay" ? `/essay/${r.slug}` :
              r.type === "digest" ? `/digest/${r.slug}` :
              r.type === "outline" ? `/outline?path=${encodeURIComponent(r.markdown_path || "")}` : "/";
            const active = i === highlight;
            return (
              <div
                key={i}
                style={{
                  padding: "6px 4px",
                  cursor: "pointer",
                  background: active ? "#eef" : "transparent",
                }}
                onMouseEnter={() => setHighlight(i)}
                onClick={(e) => select(e, to)}
              >
                <div><b>{r.name || r.title}</b> <span className="small">({r.type})</span></div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ---------------- Header ---------------- */
function Header() {
  const go = useGo();
  const { path } = React.useContext(RouterCtx);

  const [q, setQ] = React.useState("");
  const [results, setResults] = React.useState([]);
  const [open, setOpen] = React.useState(false);
  const [highlight, setHighlight] = React.useState(-1);
  const [switchOpen, setSwitchOpen] = React.useState(false);
  const boxRef = React.useRef(null);

  const current = React.useMemo(() => {
    const p = (new URL(window.location.origin + path)).pathname.replace(/\/+$/, "").toLowerCase();
    if (p === "" || p === "/") return "Topics";
    if (p.startsWith("/theologians")) return "Theologians";
    if (p.startsWith("/works")) return "Works";
    if (p.startsWith("/church-history")) return "Church History";
    if (p.startsWith("/apologetics")) return "Apologetics";
    if (p.startsWith("/digests")) return "Digests";
    if (p.startsWith("/podcasts")) return "Podcast";
    if (p.startsWith("/topic/")) return "Topic";
    if (p.startsWith("/theologian/")) return "Theologian";
    if (p.startsWith("/work/")) return "Work";
    if (p.startsWith("/essay/")) return "Essay";
    if (p.startsWith("/digest/")) return "Digest";
    if (p.startsWith("/outline")) return "Outline";
    return "Browse";
  }, [path]);

  React.useEffect(() => {
    const id = setTimeout(async () => {
      const query = q.trim();
      if (!query) { setResults([]); setOpen(false); setHighlight(-1); return; }
      try {
        const r = await api("/api/search?q=" + encodeURIComponent(query));
        setResults(r);
        setHighlight(r.length > 0 ? 0 : -1);
        setOpen(r.length > 0);
      } catch { setResults([]); setOpen(false); setHighlight(-1); }
    }, 180);
    return () => clearTimeout(id);
  }, [q]);

  React.useEffect(() => {
    function onDoc(e){ if (!boxRef.current) return; if (!boxRef.current.contains(e.target)) { setSwitchOpen(false); setOpen(false); setHighlight(-1); } }
    function onKey(e){ if (e.key === "Escape") { setOpen(false); setSwitchOpen(false); setHighlight(-1); } }
    document.addEventListener("mousedown", onDoc);
    window.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); window.removeEventListener("keydown", onKey); };
  }, []);

  const select = (e, to) => { setOpen(false); setResults([]); setQ(""); go(e, to); };

  const handleKey = (e) => {
    if (!open || results.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => (h + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => (h - 1 + results.length) % results.length);
    } else if (e.key === "Enter" && highlight >= 0) {
      e.preventDefault();
      const r = results[highlight];
      const to =
        r.type === "theologian" ? `/theologian/${r.slug}` :
        r.type === "topic" ? `/topic/${r.slug}` :
        r.type === "work" ? `/work/${r.id}` :
        r.type === "essay" ? `/essay/${r.slug}` :
        r.type === "digest" ? `/digest/${r.slug}` :
        r.type === "outline" ? `/outline?path=${encodeURIComponent(r.markdown_path || "")}` : "/";
      select(e, to);
    }
  };

  const pages = [
    ["Topics", "/"],
    ["Theologians", "/theologians"],
    ["Apologetics", "/apologetics"],
    ["Church History", "/church-history"],
    ["Digests", "/digests"],
    ["Podcast", "/podcasts"],
  ];

  return (
    <header ref={boxRef}>
      <div className="header-inner">
        <div
          className={"page-switch" + (switchOpen ? " open" : "")}
          onClick={() => setSwitchOpen(o => !o)}
          role="button"
          aria-expanded={switchOpen ? "true" : "false"}
          aria-haspopup="true"
        >
          {current} <span className="caret">▾</span>
        </div>

        <input
          placeholder="Search topics, theologians, works, essays…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => setOpen((results || []).length > 0)}
          onKeyDown={handleKey}
        />

        {switchOpen && (
          <div className="page-popover" onClick={(e) => e.stopPropagation()}>
            {pages.map(([label, to]) => (
              <a
                key={label}
                href={to}
                onClick={(e) => {
                  e.preventDefault();
                  setSwitchOpen(false);
                  select(e, to);
                }}
              >
                {label}
              </a>
            ))}
          </div>
        )}
      </div>

      {open && results.length > 0 && (
        <div className="card search-results no-raise">
          {results.map((r, i) => {
            const to =
              r.type === "theologian" ? `/theologian/${r.slug}` :
              r.type === "topic" ? `/topic/${r.slug}` :
              r.type === "work" ? `/work/${r.id}` :
              r.type === "essay" ? `/essay/${r.slug}` :
              r.type === "digest" ? `/digest/${r.slug}` :
              r.type === "outline" ? `/outline?path=${encodeURIComponent(r.markdown_path || "")}` : "/";
            const active = i === highlight;
            return (
              <div
                key={i}
                style={{
                  padding: "6px 4px",
                  cursor: "pointer",
                  background: active ? "#eef" : "transparent",
                }}
                onMouseEnter={() => setHighlight(i)}
                onClick={(e) => select(e, to)}
              >
                <div><b>{r.name || r.title}</b> <span className="small">({r.type})</span></div>
              </div>
            );
          })}
        </div>
      )}
    </header>
  );
}

/* ---------------- Leaf rows reused by pages ---------------- */
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
  const clickableProps = hasClick ? {onClick: (e) => go(e, `/theologian/${theo.slug}`)} : {};
  return (
    <div className={className} style={{cursor: hasClick ? "pointer" : "default"}} {...clickableProps}>
      <div style={{display: "flex", alignItems: "center", gap: 10, justifyContent: "space-between", flexWrap: "wrap"}}>
        <div style={{display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap"}}>
          <b><TheoLink theo={theo}/></b>
          <div className="small" style={{display: "flex", gap: 6, flexWrap: "wrap"}}>
            <TheoBadges theo={theo}/>
          </div>
        </div>
        <div style={{display: "flex", alignItems: "center", gap: 8}}>
          {theo.dates ? <div className="small">{theo.dates}</div> : null}
          {children}
        </div>
      </div>
    </div>
  );
}
function canonCountFor(datasets, { wid, theoId }) {
  const perTheo = (datasets?.canonCountsTheo?.[theoId] || []);
  const hit = perTheo.find((x) => x.id === wid);
  return hit && Number.isFinite(hit.count) ? hit.count : 0;
}
function WorkRowCollapsible({ wid, datasets, badge, count, theoId, defaultOpen = false, compact = true, sticky = true, asCard = true }) {
  const go = useGo();
  const rootRef = useRef(null);
  const works = datasets?.works || [];
  const byWork = datasets?.byWork || {};
  const live = works.find((w) => w.id === wid) || { id: wid };
  const by = byWork[wid] || {};
  const title = workTitleWithSuffix(live, by) || live.title || wid;
  const authors = resolveAuthorsForWork(wid, datasets);
  const topicsFeaturing = featuredTopicsForWork(wid, datasets?.topics || [], datasets?.reverseCanonMap || {});
  const [html, setHtml] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const resolvedCount = Number.isFinite(count) ? count : canonCountFor(datasets, { wid, theoId });
  const [open, setOpen] = useState(!!defaultOpen);
async function onToggle() {
  const willOpen = !open;
  setOpen(willOpen);

  if (willOpen && !html && !loading) {
      setLoading(true);
      try {
        const r = await api(`/api/work_summary/${wid}`);
        setHtml(r.html || "");
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    }
  }
  const titleEl = (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <b>
        <a
          href={`/work/${wid}`}
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); go(e, `/work/${wid}`, true); }}
        >{title}</a>
      </b>
      {authors.length ? (
        <span className={compact ? "meta muted" : "small muted"}>
          {" — "}
          {authors.map((a, i) => (
            <span key={i}>{i ? ", " : ""}{a.theo ? <TheoLink theo={a.theo} /> : <span>{a.display}</span>}</span>
          ))}
        </span>
      ) : null}
    </div>
  );
  const rightEl = (
    <div className="work-meta" style={{ display: "flex", alignItems: "center", gap: 6 }}>
      {badge ? <span className={badge === "WTS" ? "chip" : "chip2"}>{badge}</span> : null}
      <span className="badge">{resolvedCount}</span>
    </div>
  );
  return (
    <div ref={rootRef} className={(asCard ? "card " : "") + (compact ? " work-row" : "")} style={{ gridColumn: "1 / -1", width: "100%" }}>
      <Collapsible open={open} onToggle={onToggle} title={titleEl} right={rightEl} sticky={sticky}>
        <div style={{ marginTop: 8 }}>
          {loading && <div className="small">Loading…</div>}
          {error && <div className="small">{String(error).replace(/</g, "&lt;")}</div>}
          {!loading && !error && html && (
            <div className="markdown" style={{ paddingTop: 6 }}>
              <div dangerouslySetInnerHTML={{ __html: html }} />
            </div>
          )}
          <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            {topicsFeaturing.slice(0, 2).map((t, i) => (
              <a
                key={i}
                className={Array.isArray(t.bucket) ? "chip2" : t.bucket === "WTS" ? "chip" : "chip2"}
                href={`/topic/${t.topic_slug}`}
                onClick={(e) => { e.preventDefault(); window.history.pushState({}, "", `/topic/${t.topic_slug}`); window.dispatchEvent(new PopStateEvent("popstate")); }}
              >
                {Array.isArray(t.bucket) ? t.bucket.join(" / ") : t.bucket}: {t.title}
              </a>
            ))}
            {topicsFeaturing.length > 2 && <span className="count">+{topicsFeaturing.length - 2} topics</span>}
          </div>
        </div>
      </Collapsible>
    </div>
  );
}
function EssayRow({ essay, asCard = true }) {
  const go = useGo();
  const [open, setOpen] = React.useState(false);
  const to = `/essay/${essay.slug}`;

  const titleEl = (
    <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
      <b>
        <a
          href={to}
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); go(e, to, true); }}
        >
          {essay.title}
        </a>
      </b>
    </div>
  );


  return (
    <div
       className={(asCard ? "card " : "")} style={{ gridColumn: "1 / -1", width: "100%" }}>
      <Collapsible
        open={open}
        onToggle={() => setOpen((o) => !o)}
        title={titleEl}
        right={<span className="badge">{essay.category_label}</span>}
        sticky
      >
        <div className="markdown" style={{ paddingTop: 6 }}>
          {essay.preview_html ? (<><h4 style={{ margin: "8px 0 6px" }}>Preview</h4><div dangerouslySetInnerHTML={{ __html: String(essay.preview_html) }} /></>) : null}
          {essay.essay_html ? (<><h4 style={{ margin: "12px 0 6px" }}>Essay</h4><div dangerouslySetInnerHTML={{ __html: String(essay.essay_html) }} /></>) : null}
          {essay.recap_html ? (<><h4 style={{ margin: "12px 0 6px" }}>Recap</h4><div dangerouslySetInnerHTML={{ __html: String(essay.recap_html) }} /></>) : null}
          {!essay.preview_html && !essay.essay_html && !essay.recap_html ? <div className="small muted">(no content yet)</div> : null}
        </div>
      </Collapsible>
    </div>
  );
}
function DigestRow({ digest, asCard = true }) {
  const go = useGo();
  const [open, setOpen] = useState(false);
  const [html, setHtml] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const to = `/digest/${digest.slug}`;

  const titleEl = (
    <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
      <b>
        <a
          href={to}
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); go(e, to, true); }}
        >
          {digest.authors_display}: {digest.title}
        </a>
      </b>
    </div>
  );

  async function onToggle() {
    const willOpen = !open;
    setOpen(willOpen);
    if (willOpen && !html && !loading) {
      setLoading(true); setError("");
      try {
        const r = await api(`/api/digest_html/${encodeURIComponent(digest.slug)}`);
        setHtml(r.html || "");
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    }
  }

  return (
    <div
      className={(asCard ? "card " : "")}
      style={{ gridColumn: "1 / -1" }}
    >
      <Collapsible
        open={open}
        onToggle={onToggle}
        title={titleEl}
        right={<span className="badge">{digest.category}</span>}
        sticky
      >
        <div className="markdown" style={{ paddingTop: 6 }}>
          {loading && <div className="small" style={{ marginTop: 8 }}>Loading…</div>}
          {error && <div className="small" style={{ marginTop: 8 }}>{String(error).replace(/</g, "&lt;")}</div>}
          {!loading && !error && html && (
            <div style={{ marginTop: 8 }} dangerouslySetInnerHTML={{ __html: String(html) }} />
          )}
          {!loading && !error && !html && (
            <div className="small muted" style={{ marginTop: 8 }}>(no content)</div>
          )}
        </div>
      </Collapsible>
    </div>
  );
}
function OutlineRow({ title, path, keyWorkIds = [], datasets, asCard = false, titleHref }) {
  const go = useGo();
  const [open, setOpen] = React.useState(false);
  const [html, setHtml] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");

  const to = path ? `/outline?path=${encodeURIComponent(path)}` : null;

  async function onToggle() {
    const will = !open;
    setOpen(will);
    if (will && !html && !loading && path) {
      setLoading(true); setError("");
      try {
        const r = await api("/api/outline?path=" + encodeURIComponent(path));
        const ids = keyWorkIds.length ? keyWorkIds : (r.meta?.key_work_ids || []);
        setHtml(enhanceKeyWorks(r.html, ids, datasets) || "");
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    }
  }

  const titleEl = (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      {titleHref ? (
        <b>
          <a
            href={titleHref}
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); go(e, titleHref, true); }}
          >
            {title}
          </a>
        </b>
      ) : (
        <b>{title}</b>
      )}
    </div>
  );

  return (
    <div className={asCard ? "card" : ""} style={{ gridColumn: "1 / -1" }}>
      <Collapsible open={open} onToggle={onToggle} title={titleEl} sticky compact>
        <div className="markdown" style={{ paddingTop: 6 }}>
          {loading && <div className="small">Loading…</div>}
          {error && <div className="small">{String(error).replace(/</g, "&lt;")}</div>}
          {!loading && !error && html && <div dangerouslySetInnerHTML={{ __html: html }} />}
          {!loading && !error && !html && <div className="small muted">(no content)</div>}
        </div>
        {to && (
          <div className="small" style={{ marginTop: 6 }}>
            <a
              href={to}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                window.history.pushState({}, "", to);
                window.dispatchEvent(new PopStateEvent("popstate"));
              }}
            >
              Open full page
            </a>
          </div>
        )}
      </Collapsible>
    </div>
  );
}
function OutlineList({ items, datasets, asCard = false }) {
  return (
    <div className="grid" style={{ gridTemplateColumns: "1fr", gap: 6 }}>
      {items.map((it, i) => (
        <OutlineRow
          key={it.markdown_path || i}
          title={it.topic_title || it.topic_slug || "Outline"}
          titleHref={it.topic_slug ? `/topic/${it.topic_slug}` : undefined}
          path={it.markdown_path}
          keyWorkIds={it.key_work_ids || []}
          datasets={datasets}
          asCard={asCard}
        />
      ))}
    </div>
  );
}
function OutlineGroups({ groups, datasets, normalizeItem }) {
  const go = useGo();
  const [openCats, setOpenCats] = React.useState({});

  return Object.entries(groups)
    .sort(([a], [b]) => parseCategoryKey(a) - parseCategoryKey(b))
    .map(([cat, items]) => {
      const open = !!openCats[cat];
      const catSlug = slugify(cat);
      const normalized = (normalizeItem ? items.map(normalizeItem) : items);

      return (
        <div key={cat} className={"card section " + (open ? "open" : "")} style={{ marginBottom: 12 }}>
          <div className="section-head" onClick={() => setOpenCats(p => ({ ...p, [cat]: !open }))}>
            <div className="caret">▸</div>
            <div className="small">
              <b>
                <a
                  href={`/category/${catSlug}`}
                  onClick={(e) => { e.preventDefault(); e.stopPropagation(); go(e, `/category/${catSlug}`, true); }}
                >
                  {cat}
                </a>
              </b>
            </div>
            <span className="count" style={{ marginLeft: "auto" }}>{normalized.length}</span>
          </div>

          {open && <OutlineList items={normalized} datasets={datasets} />}
        </div>
      );
    });
}



/* ---------------- Pages built with UniversalPage ---------------- */
// Topics
function TopicsPage({ datasets }) {
  const go = useGo();
  const items = datasets.topics || [];
  const levels = [
    {
      key: (t) => t.category || "Other",
      label: (cat, arr) => <h2><CategoryLink name={cat} stop>{cat}</CategoryLink></h2>,
      right: (_cat, arr) => <span className="count">{arr.length}</span>,
      startOpen: false
    }
  ];
  const renderRow = (t) => (
     <div
        key={t.id}
        className="card"
        style={{ cursor: "pointer" }}
        onClick={(e) => go(e, `/topic/${t.slug}`)}
        role="link"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") go(e, `/topic/${t.slug}`);
        }}
      >
        <b>{t.title}</b>
      </div>
  );
  return <UniversalPage title={null} items={items} levels={levels} renderRow={renderRow} emptyText="No topics." />;
}

// Theologians
function cmpAlphaTheo(a, b) {
  const A = alphaKey(a.full_name || a.name || "");
  const B = alphaKey(b.full_name || b.name || "");
  return A.last.localeCompare(B.last) ||
         A.firstRest.localeCompare(B.firstRest);
}
function cmpBirthTheo(a, b) {
  return (birthYear(a) - birthYear(b)) || cmpAlphaTheo(a, b);
}
function eraKey(theo) {
  const e = getEra(theo);
  const start = Number.isFinite(e.start) ? e.start : 99999;
  return String(start).padStart(6, "0") + "|||" + (e.label || "Other");
}
function splitEraKey(key) {
  const [padded, label] = String(key).split("|||");
  return { start: parseInt(padded, 10), label };
}

function TheologiansPage({ datasets, showWorks = false, title = "Theologians" }) {
  const theos = React.useMemo(
    () => [...(datasets.theologians || [])],
    [datasets.theologians]
  );

  // parent owns mode + persistence
  const storageKey = showWorks ? "works_sort_mode" : "theologians_sort_mode";
  const [mode, setMode] = React.useState(() => {
    try { return localStorage.getItem(storageKey) || "birth"; } catch { return "birth"; }
  });
  React.useEffect(() => {
    try { localStorage.setItem(storageKey, mode); } catch {}
  }, [mode, storageKey]);

  // Mode → group levels
  const levels = React.useMemo(() => {
    if (mode === "alpha" || mode === "birth") {
      return []; // flat; we pre-sort items below
    }
    if (mode === "era") {
      return [
        {
          key: (t) => eraKey(t),
          label: (k) => <h2>{splitEraKey(k).label}</h2>,
          right: (_k, arr) => <span className="count">{arr.length}</span>,
          sort: (A, B) => splitEraKey(A[0]).start - splitEraKey(B[0]).start, // chronological eras
          itemSort: cmpBirthTheo, // theos in era by birth
          startOpen: false,
        },
      ];
    }
    // mode === "trad"
    return [
      {
        key: (t) => getTraditionLabel(t) || "Other",
        label: (tr) => <div className="small"><b>{tr}</b></div>,
        right: (_tr, arr) => <span className="count">{arr.length}</span>,
        sort: (a, b) => String(a[0]).localeCompare(String(b[0])), // tradition alpha
        itemSort: cmpAlphaTheo, // theos inside tradition alpha
        startOpen: false,
      },
    ];
  }, [mode]);

  // Pre-sort flat items for alpha/birth modes
  const items = React.useMemo(() => {
    const arr = Array.isArray(theos) ? [...theos] : [];
    if (mode === "alpha") return arr.sort(cmpAlphaTheo);
    if (mode === "birth") return arr.sort(cmpBirthTheo);
    return arr;
  }, [theos, mode]);

  // Leaf renderer
  const renderRow = (node) => {
    if (!showWorks) return <TheoRow key={node.id} theo={node} />;

    // show theologian's canonical works as rows under that theologian group
    const canonList = datasets.canonCountsTheo[node.id] || [];
    if (!canonList.length) {
      return <div key={node.id} className="small" style={{ margin: "6px 0" }}>No canonical works.</div>;
    }
    return canonList.map(({ id: wid, count }) => (
      <WorkRowCollapsible
        key={`${node.id}::${wid}`}
        wid={wid}
        datasets={datasets}
        count={count}
        theoId={node.id}
        compact
        sticky
        asCard={false}
      />
    ));
  };

  // If we're showing works, add a final level that groups by theologian
  const levelsWithTheo = React.useMemo(() => {
    if (!showWorks) return levels;
    return [
      ...levels,
      {
        key: (t) => t.id, // unique group per theologian
        label: (_id, arr) => <TheoRow theo={arr[0]} hasClick={false} className="" />,
        right: (_id, arr) => {
          const list = datasets.canonCountsTheo[arr[0].id] || [];
          return <span className="count">{list.length}</span>;
        },
        // keep theologian groups in the same order as the incoming list
        preserveOrder: true,
        startOpen: false,
      },
    ];
  }, [levels, showWorks, datasets.canonCountsTheo]);

  return (
    <div>
      <h1>{title}</h1>
      <SortBar value={mode} onChange={setMode} storageKey={storageKey} />
      <UniversalPage
        title={null}
        items={items}
        levels={levelsWithTheo}
        renderRow={renderRow}
        emptyText={showWorks ? "No works." : "No theologians."}
      />
    </div>
  );
}

// Works = Theologians + final works layer, but same sort modes
function WorksPage({ datasets }) {
  return <TheologiansPage datasets={datasets} showWorks title="Works" />;
}

// Church History / Apologetics (Essays grouped by category)
function DomainPage({ domainId, datasets }) {
  const data = domainId === "CH" ? datasets.chData : datasets.apData;
  if (!data) return <div>Loading…</div>;
  const items = (data.essays || []).map(e => ({...e, group: e.category_key, groupLabel: e.category_label}));

  const levels = [
    {
      key: (e)=> e.group,
      label: (_k, arr)=> <h3>{arr[0]?.groupLabel || "Other"}</h3>,
      right: (_k, arr)=> <span className="count">{arr.length}</span>,
      startOpen: false
    }
  ];

  return (
    <UniversalPage
      title={data.label}
      items={items}
      levels={levels}
      renderRow={(e)=><EssayRow key={e.id} essay={e} asCard={false}/>}
      emptyText="No essays."
    />
  );
}

// Digests (group by category)
function DigestsPage() {
  const [payload, setPayload] = useState(null);
  useEffect(() => { let gone=false; (async()=>{ try { const r = await api("/api/digests"); if(!gone) setPayload(r); } catch { if(!gone) setPayload({digests:[]}); } })(); return ()=>{gone=true;}; }, []);
  if (!payload) return <div>Loading…</div>;

  const items = payload.digests || [];
  const labelFor = (cat) => (cat === "AP" ? "Apologetics" : cat === "ST" ? "Systematic Theology" : "Church History");

  const levels = [
    { key:(d)=> d.category, label:(cat)=> <h3>{labelFor(cat)}</h3>, right:(_c,arr)=> <span className="count">{arr.length}</span>, startOpen:false }
  ];

  return (
    <UniversalPage
      title="Digests"
      items={items}
      levels={levels}
      renderRow={(d) => <DigestRow key={d.slug} digest={d} asCard={false} />}
      emptyText="No digests."
    />
  );
}

/* ---------------- Detail pages kept minimal ---------------- */
function EssayPage(props) {
  const param = props.slug || props.id || decodeURIComponent(window.location.pathname.split("/").pop() || "");
  const [essay, setEssay] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let gone = false;
    async function load() {
      setError(""); setEssay(null);
      try {
        const r = await api(`/api/essay/${encodeURIComponent(param)}`);
        if (!gone) setEssay(r);
      } catch {
        if (!gone) setError("Essay not found.");
      }
    }
    if (param) load();
    return () => { gone = true; };
  }, [param]);
  if (error) return <div className="small">{error}</div>;
  if (!essay) return <div>Loading…</div>;
  return (
    <div>
      <h1>{essay.title}</h1>
      <span className="badge">{essay.domain_label}</span>{" "}
      <span className="badge">{essay.category_label}</span>
      <div className="markdown" style={{ paddingTop: 10 }}>
        {essay.preview_html ? (<><h3>Preview</h3><div dangerouslySetInnerHTML={{ __html: String(essay.preview_html) }} /></>) : null}
        {essay.essay_html ? (<><h3 style={{ marginTop: 16 }}>Essay</h3><div dangerouslySetInnerHTML={{ __html: String(essay.essay_html) }} /></>) : null}
        {essay.recap_html ? (<><h3 style={{ marginTop: 16 }}>Recap</h3><div dangerouslySetInnerHTML={{ __html: String(essay.recap_html) }} /></>) : null}
        {!essay.preview_html && !essay.essay_html && !essay.recap_html ? <div className="small muted">(no content yet)</div> : null}
      </div>
    </div>
  );
}
function DigestPage(props) {
  const param = props.slug || props.id || decodeURIComponent(window.location.pathname.split("/").pop() || "");
  const [digest, setDigest] = useState(null);
  const [html, setHtml] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let gone = false;
    async function load() {
      setError(""); setDigest(null); setHtml("");
      try {
        const meta = await api(`/api/digest/${encodeURIComponent(param)}`);
        if (gone) return;
        setDigest(meta);
        try {
          const r = await api(`/api/digest_html/${encodeURIComponent(param)}`);
          if (!gone) setHtml(r.html || "");
        } catch { if (!gone) setHtml(""); }
      } catch {
        if (!gone) setError("Digest not found.");
      }
    }
    if (param) load();
    return () => { gone = true; };
  }, [param]);
  if (error) return <div className="small">{error}</div>;
  if (!digest) return <div>Loading…</div>;
  return (
    <div>
      <h1>{digest.authors_display}: {digest.title}</h1>
      <span className="badge">{digest.category}</span>
      <div style={{ padding: 10 }}>
        <div className="markdown" style={{ paddingTop: 8 }}>
          {html ? <div dangerouslySetInnerHTML={{ __html: String(html) }} /> : <div className="small muted">(no content)</div>}
        </div>
      </div>
    </div>
  );
}
function TopicPage({ slug, datasets }) {
  const go = useGo();
  const topic = datasets.topics.find((t) => t.slug === slug);
  if (!topic) return <div>Topic not found.</div>;

  // --- essay: compute path and load once (same pattern as Work summary) ---
  // category folder: drop leading number from slugified category, e.g. "4-anthropology-..." -> "anthropology-..."
  const catFolder = slugify(topic.category || "other").split("-").slice(1).join("-") || "other";
  // topic folder: drop "1-a-" style ordinal from topic slug
  const topicFolder = String(topic.slug || "").split("-").slice(2).join("-");
  const essayRel = `outlines/${catFolder}/${topicFolder}/${topicFolder}.md`;

  const [essayHTML, setEssayHTML] = React.useState("");
  const [essayOpen, setEssayOpen] = React.useState(true); // default open like "About"

  React.useEffect(() => {
    let gone = false;
    (async () => {
      try {
        const r = await api("/api/outline?path=" + encodeURIComponent(essayRel));
        if (!gone) setEssayHTML(r.html || "");
      } catch {
        if (!gone) setEssayHTML("");
      }
    })();
    return () => { gone = true; };
  }, [essayRel]);

  // --- existing state/logic ---
  const [openWts, setOpenWts] = React.useState(false);
  const [openRecent, setOpenRecent] = React.useState(false);
  const [openEra, setOpenEra] = React.useState({});

  const entry = datasets.byTopic[topic.id] || { theologians: [] };
  const theoTitle = (T) => (T.dates ? `${T.full_name} (${T.dates})` : T.full_name);

  // outlines lookup for this topic
  function outlinesForTheo(theologian_id) {
    const tEntry = datasets.byTheo[theologian_id];
    if (!tEntry) return [];
    const groups = tEntry.outlines_by_topic_category || {};
    return Object.values(groups)
      .flat()
      .filter((o) => o.topic_id === topic.id || o.topic_slug === topic.slug);
  }
  function firstOutlineForTheo(theologian_id) {
    const list = outlinesForTheo(theologian_id);
    return Array.isArray(list) && list.length ? list[0] : null;
  }

  // group theologians by era (for outline list)
  const theosByEra = React.useMemo(() => {
    const map = new Map();
    for (const t of entry.theologians || []) {
      const T = (datasets.theologians || []).find((x) => x.id === t.theologian_id);
      if (!T) continue;
      const era = getEra(T);
      const key = `${era.start ?? 99999}|||${era.label || "Other"}`;
      if (!map.has(key)) map.set(key, { label: era.label || "Other", start: era.start ?? 99999, items: [] });
      map.get(key).items.push(T);
    }
    return [...map.values()].sort((a, b) => a.start - b.start || a.label.localeCompare(b.label));
  }, [entry.theologians, datasets.theologians]);

  const canonCounts = datasets.canonCountsTopic[topic.id] || { WTS: [], Recent: [] };

  return (
    <div>
      <h1>
        {topic.title}{" "}
        {topic.category && (
          <span className="badge">
            <CategoryLink name={topic.category} />
          </span>
        )}
      </h1>

      {/* NEW: Essay panel — collapsible, default open, like "About" */}
      <div className="card" style={{ marginTop: 12, padding: 0 }}>
        <div className={"section " + (essayOpen ? "open" : "")}>
          <div className="section-head sticky-head" onClick={() => setEssayOpen(o => !o)}>
            <div className="caret">▸</div>
            <h3 style={{ margin: 0 }}>Essay</h3>
          </div>
          {essayOpen && (
            <div style={{ padding: 16 }}>
              {essayHTML
                ? <div className="markdown" dangerouslySetInnerHTML={{ __html: essayHTML }} />
                : <div className="small muted">(no content yet)</div>}
            </div>
          )}
        </div>
      </div>

      {/* badges row */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "4px 0 8px" }}>
        <span className="badge">WTS/Princeton: {(canonCounts.WTS || []).length}</span>
        <span className="badge">Recent: {(canonCounts.Recent || []).length}</span>
        <span className="badge">Cited in outlines: {(topic.work_ids || []).length}</span>
      </div>

      {/* Key works — WTS */}
      <div className={"section " + (openWts ? "open" : "")}>
        <div className="section-head" onClick={() => setOpenWts(!openWts)}>
          <div className="caret">▸</div>
          <h3>Key Works — WTS / Old Princeton</h3>
          <span className="count">{(canonCounts.WTS || []).length}</span>
        </div>
        {openWts && (
          <div className="work-list">
            {(canonCounts.WTS || []).map(({ id, count }) => (
              <WorkRowCollapsible
                key={id}
                wid={id}
                datasets={datasets}
                badge="WTS"
                count={count}
                compact
                asCard={false}
              />
            ))}
          </div>
        )}
      </div>

      {/* Key works — Recent */}
      <div className={"section " + (openRecent ? "open" : "")}>
        <div className="section-head" onClick={() => setOpenRecent(!openRecent)}>
          <div className="caret">▸</div>
          <h3>Key Works — Recent Scholarship</h3>
          <span className="count">{(canonCounts.Recent || []).length}</span>
        </div>
        {openRecent && (
          <div className="work-list">
            {(canonCounts.Recent || []).map(({ id, count }) => (
              <WorkRowCollapsible
                key={id}
                wid={id}
                datasets={datasets}
                badge="Recent"
                count={count}
                compact
                asCard={false}
              />
            ))}
          </div>
        )}
      </div>

      {/* Outlines — grouped by era */}
      <div style={{ marginTop: 18 }}>
        <h3>Outlines</h3>
        <div className="grid" style={{ gridTemplateColumns: "1fr", gap: 6 }}>
          {theosByEra.map((era) => {
            const opened = !!openEra[era.label];
            return (
              <div
                key={era.label}
                className={"section " + (opened ? "open" : "")}
                style={{ marginBottom: 6 }}
              >
                <div
                  className="section-head"
                  onClick={() => setOpenEra((s) => ({ ...s, [era.label]: !opened }))}
                >
                  <div className="caret">▸</div>
                  <div className="small"><b>{era.label}</b></div>
                  <span className="count">{era.items.length}</span>
                </div>

                {opened && (
                  <div style={{ marginTop: 6 }}>
                    {era.items
                      .sort(
                        (a, b) =>
                          birthYear(a) - birthYear(b) ||
                          lastNameKey(a.full_name).localeCompare(lastNameKey(b.full_name))
                      )
                      .map((T) => {
                        const first = firstOutlineForTheo(T.id);
                        if (!first) return null;

                        return (
                          <OutlineRow
                            key={T.id}
                            title={theoTitle(T)}
                            titleHref={`/theologian/${T.slug}`}
                            path={first.markdown_path}
                            keyWorkIds={first.key_work_ids || []}
                            datasets={datasets}
                            asCard={false}
                          />
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
function TheologianPage({ slug, datasets }) {
  const theo = datasets.theologians.find((x) => x.slug === slug);
  if (!theo) return <div>Theologian not found.</div>;

  const entry = datasets.byTheo[theo.id] || {};
  const groups = entry.outlines_by_topic_category || {};
  const canonList = datasets.canonCountsTheo[theo.id] || [];

  // NEW: Theologian Essay panel
  const [essayOpen, setEssayOpen] = React.useState(true);      // default open (like Work summary)
  const [essayHTML, setEssayHTML] = React.useState("");

  React.useEffect(() => {
    let gone = false;
    (async () => {
      try {
        const r = await api(`/api/theologian_essay/${encodeURIComponent(theo.id)}`);
        if (!gone) setEssayHTML(r?.html || "");
      } catch {
        if (!gone) setEssayHTML("");
      }
    })();
    return () => { gone = true; };
  }, [theo.id]);

  const [openWorks, setOpenWorks] = React.useState(false);
  const [openCats, setOpenCats] = React.useState({});
  const [aboutOpen, setAboutOpen] = React.useState(false);

  return (
    <div>
      <h1>
        {theo.full_name || theo.name} {theo.dates ? <span className="small">{theo.dates}</span> : null}
      </h1>
      <TheoBadges theo={theo}/>

      {/* NEW: Essay panel, collapsible, default open */}
      <div className="card" style={{ marginTop: 12, padding: 0 }}>
        <div className={"section " + (essayOpen ? "open" : "")}>
          <div className="section-head sticky-head" onClick={() => setEssayOpen(o => !o)}>
            <div className="caret">▸</div>
            <h3 style={{ margin: 0 }}>Essay</h3>
          </div>
          {essayOpen && (
            <div className="markdown" style={{ padding: 16 }}>
              {essayHTML ? (
                <div dangerouslySetInnerHTML={{ __html: essayHTML }} />
              ) : (
                <div className="small muted">(no content yet)</div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* About */}
      <div className="card" style={{marginTop: 12, padding: 0}}>
        <div className={'section ' + (aboutOpen ? 'open' : '')}>
          <div className="section-head" onClick={() => setAboutOpen(!aboutOpen)}>
            <div className="caret">▸</div>
            <h3 style={{margin: 0}}>About</h3>
          </div>
          {aboutOpen && (
            <div style={{padding: 16}}>
              {theo.bio ? <div className="prose" style={{marginBottom: 16}}>{theo.bio}</div> : null}
              {Array.isArray(theo.timeline) && theo.timeline.length ? (
                <div style={{marginTop: 10}}>
                  <h4>Timeline</h4>
                  <ul className="timeline">
                    {[...theo.timeline].sort((a,b)=>(a.year??0)-(b.year??0)).map((evt, i) => (
                      <li key={i}><span className="yr">{evt.year}</span><span className="evt">{evt.event}</span></li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {Array.isArray(theo.themes) && theo.themes.length ? (
                <div style={{marginTop: 10}}>
                  <h4>Themes</h4>
                  <ul className="theme-list">
                    {theo.themes.map((t, i) => (<li key={i}><b>{t.label}.</b> {t.gloss}</li>))}
                  </ul>
                </div>
              ) : null}
            </div>
          )}
        </div>
      </div>

      {/* Canonical Works */}
      <div className={"section " + (openWorks ? "open" : "")} style={{marginTop: 18}}>
        <div className="section-head" onClick={() => setOpenWorks(!openWorks)}>
          <div className="caret">▸</div>
          <h3>Works</h3>
          {canonList.length ? <span className="count">{canonList.length}</span> : null}
        </div>
        {openWorks && (
          <div className="work-list">
            {canonList.length === 0 ? <div className="small">No works found.</div> : (
              canonList.map(({id, count}) => (
                <WorkRowCollapsible key={id} wid={id} datasets={datasets} count={count} compact asCard={false} />
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
function TopicCategoryPage({ slug, datasets }) {
  const go = useGo();
  const { topics } = datasets;

  const { catName, items } = React.useMemo(() => {
    const sample = topics.find((t) => slugify(t.category || "Other") === slug);
    const name = sample ? sample.category : slug;
    const list = topics
      .filter((t) => slugify(t.category || "Other") === slug)
      .sort((a, b) => {
        // numeric/letter ordering like "2.A" vs "10.B"
        const [na, la] = parseTopicKeyFromSlug(a.slug);
        const [nb, lb] = parseTopicKeyFromSlug(b.slug);
        if (na !== nb) return na - nb;
        return String(la).localeCompare(String(lb));
      });
    return { catName: name, items: list };
  }, [slug, topics]);

  return (
    <div>
      <h1>{catName}</h1>
      <div className="grid">
        {items.map((t) => (
          <div
            key={t.id}
            className="card"
            style={{ cursor: "pointer" }}
            onClick={(e) => go(e, `/topic/${t.slug}`)}
            role="link"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") go(e, `/topic/${t.slug}`);
            }}
          >
            <b>{t.title}</b>
          </div>
        ))}
      </div>
    </div>
  );
}
function PodcastPage() {
  const feeds = [
    { file: "podcasts/ap-figures.rss", title: "Apologetics: Figures & Methods" },
    { file: "podcasts/ap-issues.rss", title: "Apologetics: Issues & Applications" },
    { file: "podcasts/ap-vantil.rss", title: "Cornelius Van Til: Method & Debate" },
    { file: "podcasts/ch-ancient.rss", title: "Church History: Ancient" },
    { file: "podcasts/ch-medieval.rss", title: "Church History: Medieval" },
    { file: "podcasts/ch-reformation.rss", title: "Church History: Reformation" },
    { file: "podcasts/ch-modern.rss", title: "Church History: Modern" },
  ];
  const base = "https://klosoter.github.io/theology-audio/";

  function CopyBtn({ url }) {
    const [ok, setOk] = React.useState(false);
    return (
      <button
        className="btn secondary"
        onClick={async () => {
          try { await navigator.clipboard.writeText(url); setOk(true); setTimeout(()=>setOk(false),1200); } catch {}
        }}
      >
        {ok ? "Copied ✓" : "Copy RSS"}
      </button>
    );
  }

  return (
    <div className="container podcasts">
      <h1>Theology Audio — Podcast Feeds</h1>
      <p className="lead">
        Subscribe to narrated <b>AP</b> and <b>CH</b> essays. Add a feed to your podcast app; new audio
        will drop in automatically.
      </p>

      <div className="podcast-grid">
        {feeds.map((f) => {
          const url = base + f.file;
          return (
            <article key={f.file} className="card podcast-card">
              <h3 className="podcast-title">{f.title}</h3>
              <div className="podcast-actions">
                <a className="btn primary" href={url} target="_blank" rel="noopener noreferrer">Open feed</a>
                <CopyBtn url={url} />
              </div>
              <code className="rss-url">{url}</code>
            </article>
          );
        })}
      </div>

      <h3 style={{marginTop:16}}>How to subscribe</h3>
      <ol className="small">
        <li>Click “Open feed” or copy the RSS link.</li>
        <li>In your app, choose “Add by URL” / “Add RSS Feed”.</li>
        <li>Paste, then subscribe.</li>
      </ol>
    </div>
  );
}

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

  const [summaryHTML, setSummaryHTML] = useState("");
  useEffect(() => { (async () => { try { const r = await api(`/api/work_summary/${canonicalId}`); setSummaryHTML(r.html); } catch { setSummaryHTML(""); } })(); }, [canonicalId]);

  const [openCats, setOpenCats] = useState(() => ({ _summary: true }));

  const groups = useMemo(() => {
    const refs = by.referenced_in || [];
    const tmap = new Map((datasets.topics || []).map((t) => [t.id, t]));
    const byCat = {};
    for (const ref of refs) {
      const t = tmap.get(ref.topic_id) || {};
      const cat = t.category || "Other";
      (byCat[cat] ??= []).push({
        topic_id: t.id,
        topic_slug: t.slug,
        topic_title: t.title || ref.topic_id,
        markdown_path: ref.markdown_path,
        key_work_ids: ref.key_work_ids || []
      });
    }
    const sortedEntries = Object.entries(byCat).sort(([a], [b]) => parseCategoryKey(a) - parseCategoryKey(b));
    for (const [, items] of sortedEntries) {
      items.sort((ta, tb) => {
        const [na, la] = parseTopicKeyFromSlug(ta.topic_slug || "");
        const [nb, lb] = parseTopicKeyFromSlug(tb.topic_slug || "");
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

      {summaryHTML && (
        <div className={"section card " + (openCats._summary ? "open" : "")} style={{marginTop: 16}}>
          <div className="section-head sticky-head" onClick={() => setOpenCats(prev => ({ ...prev, _summary: !prev._summary }))}>
            <div className="caret">▸</div>
            <div className="small"><b>Summary</b></div>
          </div>
          {openCats._summary && (
            <div className="markdown" style={{padding: 8}}>
              <div dangerouslySetInnerHTML={{ __html: summaryHTML }} />
            </div>
          )}
        </div>
      )}

      {featured.length ? (
        <div style={{marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap"}}>
          {featured.slice(0, 4).map((t, i) => (
            <a
              key={i}
              className={Array.isArray(t.bucket) ? "chip2" : t.bucket === "WTS" ? "chip" : "chip2"}
              href={`/topic/${t.topic_slug}`}
              onClick={(e) => {
                e.preventDefault();
                window.history.pushState({}, "", `/topic/${t.topic_slug}`);
                window.dispatchEvent(new PopStateEvent("popstate"));
              }}
            >
              {Array.isArray(t.bucket) ? t.bucket.join(' / ') : t.bucket}: {t.title}
            </a>
          ))}
          {featured.length > 4 && <span className="count">+{featured.length - 4} topics</span>}
        </div>
      ) : null}

      <div style={{marginTop: 18}}>
        <h3>Outlines</h3>
        <OutlineGroups groups={groups} datasets={datasets} />
      </div>
    </div>
  );
}
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
/* ---------------- Routes ---------------- */
function Routes({ datasets }) {
  const { path } = useContext(RouterCtx);
  const url = new URL(window.location.origin + path);
  const pathname = url.pathname.replace(/\/+$/, "").toLowerCase();

  if (pathname === "" || pathname === "/")              return <TopicsPage datasets={datasets} />;
  if (pathname === "/theologians")                      return <TheologiansPage datasets={datasets} />;
  if (pathname === "/works")                            return <WorksPage datasets={datasets} />;
  if (pathname.startsWith("/topic/"))                   return <TopicPage slug={decodeURIComponent(url.pathname.split("/").pop())} datasets={datasets} />;
  if (pathname.startsWith("/theologian/"))              return <TheologianPage slug={decodeURIComponent(url.pathname.split("/").pop())} datasets={datasets} />;
  if (pathname.startsWith("/work/"))                    return <WorkPage id={decodeURIComponent(url.pathname.split("/").pop())} datasets={datasets} />;
  if (pathname.startsWith("/outline"))                  return <OutlinePage />;
  if (pathname.startsWith("/church-history"))           return <DomainPage domainId="CH" datasets={datasets} />;
  if (pathname.startsWith("/apologetics"))              return <DomainPage domainId="AP" datasets={datasets} />;
  if (pathname.startsWith("/essay/"))                   return <EssayPage id={decodeURIComponent(url.pathname.split("/").pop())} />;
  if (pathname.startsWith("/category/"))                return <TopicCategoryPage slug={decodeURIComponent(url.pathname.split("/").pop())} datasets={datasets} />;
  if (pathname === "/digests")                          return <DigestsPage />;
  if (pathname.startsWith("/digest/"))                  return <DigestPage slug={decodeURIComponent(url.pathname.split("/").pop())} />;
  if (pathname === "/podcasts")                         return <PodcastPage />;

  return <div>Not found.</div>;
}


/* ---------------- App (DataHub + Router) ---------------- */
function App() {
  const router = useRouter();
  const [datasets, setDatasets] = useState(null);

  useEffect(() => {
    (async () => {
      const [
        topics, theologians, works,
        byTopic, byTheo, byWork,
        canonMap, reverseCanonMap,
        canonCountsTheo, canonCountsTopic,
        chData, apData,
      ] = await Promise.all([
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
        api("/api/essays/ch"),
        api("/api/essays/ap"),
      ]);
      setDatasets({
        topics, theologians, works,
        byTopic, byTheo, byWork,
        canonMap, reverseCanonMap,
        canonCountsTheo, canonCountsTopic,
        chData, apData,
      });
    })().catch(console.error);
  }, []);

  if (!datasets) return <div className="container">Loading…</div>;

  return (
    <RouterCtx.Provider value={router}>
      <Header />
      <div className="container">
        <Routes datasets={datasets} />
      </div>
    </RouterCtx.Provider>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
