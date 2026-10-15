import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { Top, useApp, useLive } from "../App.jsx";

const CATS = { langages: "Langages", frameworks: "Frameworks", outils: "Outils", systemes: "Systèmes", cloud: "Cloud",
  bases: "Bases de données", normes: "Normes", methodes: "Méthodes", autres: "Autres" };
const SECTIONS = [
  ["identite", "Identité"], ["resume", "Synthèse"], ["competences", "Compétences"], ["missions", "Missions"],
  ["formations", "Formations"], ["langues", "Langues"], ["disponibilite", "Disponibilité"],
];

/** « AAAA-MM » ↔ « MM/AAAA » */
const fmtDate = (v) => (!v ? "" : /^\d{4}-\d{2}/.test(v) ? `${v.slice(5, 7)}/${v.slice(0, 4)}` : v);
const parseDate = (s) => {
  const t = (s || "").trim();
  let m = t.match(/^(\d{1,2})\s*[/.-]\s*(\d{4})$/);
  if (m) return `${m[2]}-${m[1].padStart(2, "0")}`;
  m = t.match(/^(\d{4})(?:-(\d{2}))?$/);
  if (m) return m[2] ? `${m[1]}-${m[2]}` : m[1];
  return null;
};

/** Mon profil : création (CV, LinkedIn, à la main) puis édition directe avec enregistrement automatique. */
export default function ProfilePage() {
  const { notify } = useApp();
  const navigate = useNavigate();
  const [p, setP] = useState(null);
  const [data, setData] = useState(null);
  const [updates, setUpdates] = useState([]);
  const [section, setSection] = useState("identite");
  const [manual, setManual] = useState(false);
  const [save, setSave] = useState("saved"); // saved | pending | saving | error
  const [verified, setVerified] = useState([]);
  const [reading, setReading] = useState(null); // nom du CV en cours de lecture (création)
  const [found, setFound] = useState(false);
  const timer = useRef(null);
  const latest = useRef(null);

  const load = useCallback(async () => {
    const [x, ups] = await Promise.all([api.profile(), api.updates().catch(() => [])]);
    setP(x); setData(structuredClone(x.data)); setUpdates(ups); setVerified([]);
    return x;
  }, []);
  useEffect(() => { load(); }, [load]);

  const flush = useCallback(async () => {
    clearTimeout(timer.current);
    if (!latest.current) return;
    const { d, v } = latest.current;
    latest.current = null;
    setSave("saving");
    try {
      const x = await api.saveProfile(d, v);
      setP(x); setSave("saved");
      if (!latest.current) { setData(structuredClone(x.data)); setVerified([]); }  // identifiants attribués par le serveur
    }
    catch (e) { setSave("error"); notify(e.message); }
  }, [notify]);
  useEffect(() => () => { flush(); }, [flush]);

  useLive((type, u) => {
    if (type !== "profile_update") return;
    if (u.status === "extracting") return;
    api.updates().then(setUpdates).catch(() => {});
    if (!latest.current) load().then((x) => {
      if (reading && (x.data.missions.length || x.data.competences.length)) { setReading(null); setFound(true); }
      if (reading && u.status === "failed") { setReading(null); notify(u.error || "Ce CV n'a pas pu être lu. Essayez la version PDF ou Word."); }
    });
  });
  // secours si le temps réel est coupé
  useEffect(() => {
    if (!reading) return undefined;
    const t = setInterval(async () => {
      const x = await api.profile().catch(() => null);
      const ups = await api.updates().catch(() => []);
      if (x && (x.data.missions.length || x.data.competences.length)) { setP(x); setData(structuredClone(x.data)); setReading(null); setFound(true); }
      else if (ups.some((u) => u.status === "failed")) { setReading(null); notify("Ce CV n'a pas pu être lu. Essayez la version PDF ou Word."); }
    }, 2500);
    return () => clearInterval(t);
  }, [reading, notify]);

  if (!data) return <><Top title="Mon profil" /><div className="content"><span className="spin" /></div></>;

  const change = (fn, alsoVerify = []) => {
    const d = structuredClone(data); fn(d); setData(d);
    const v = [...new Set([...verified, ...alsoVerify])]; setVerified(v);
    latest.current = { d, v }; setSave("pending");
    clearTimeout(timer.current); timer.current = setTimeout(flush, 900);
  };
  const empty = !data.missions.length && !data.competences.length && !data.identite.nom && !data.resume.text;
  const extracting = updates.find((u) => u.status === "extracting");
  const sendCv = async (files) => {
    if (!files.length) return;
    try {
      const r = await api.drop(files, null, { autoDossier: false, expected: "cv" });
      if (!r.profile_update_id) { notify((r.notes || [])[0] || "Ce fichier n'a pas été reconnu comme un CV."); return; }
      setReading(files[0].name);
    } catch (e) { notify(e.message); }
  };

  if ((empty && !manual) || reading || found) {
    return <CreateProfile reading={reading || (extracting && extracting.filename)} found={found} data={data}
                          unverified={p.unverified_paths || []} onCv={sendCv}
                          onManual={() => { setManual(true); setSection("identite"); }}
                          onDone={() => { setFound(false); setManual(true); setSection(p.unverified_paths?.length ? "missions" : "identite"); }} />;
  }

  // points à vérifier : chemins d'origine (missions[2].debut) → identifiant de mission, pour survivre au réordonnancement
  const unv = (p.unverified_paths || []).filter((x) => !verified.includes(x));
  const missionIdx = (path) => { const m = path.match(/^missions\[(\d+)\]\.(\w+)/); return m ? [p.data.missions[+m[1]]?.id, m[2]] : null; };
  const unvMission = (id, field) => unv.find((x) => { const r = missionIdx(x); return r && r[0] === id && r[1] === field; });
  const unvField = (path) => unv.includes(path) ? path : null;
  const sectionOf = (path) => (path.startsWith("missions") ? "missions" : path.startsWith("identite.disponibilite") || path.startsWith("identite.mobilite") ? "disponibilite"
    : path.startsWith("identite") ? "identite" : path.startsWith("langues") ? "langues" : path.split(/[.[]/)[0]);

  const id = data.identite;
  const checks = [
    { ok: !!(id.prenom && id.nom && id.titre), label: "Nom, prénom et titre", s: "identite" },
    { ok: !!data.resume.text, label: "Une synthèse de quelques lignes", s: "resume" },
    { ok: data.competences.length >= 5, label: "Au moins 5 compétences", s: "competences" },
    { ok: data.missions.length > 0 && data.missions.every((m) => m.debut), label: "Missions datées", s: "missions" },
    { ok: data.formations.length + data.certifications.length > 0, label: "Une formation ou certification", s: "formations" },
    { ok: data.langues.length > 0, label: "Vos langues et leur niveau", s: "langues" },
    { ok: !!id.disponibilite, label: "Disponibilité, souvent demandée par les ESN", s: "disponibilite" },
  ];
  const pct = Math.round(((checks.filter((c) => c.ok).length) / checks.length) * 100 * (unv.length ? 0.95 : 1));
  const countFor = (s) => ({ competences: data.competences.length, missions: data.missions.length,
    formations: data.formations.length + data.certifications.length, langues: data.langues.length })[s];
  const pendingUpdate = updates.find((u) => u.status === "ready");

  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "240px 1fr 330px", minHeight: "calc(100vh - 64px)" }} className="cols">
        <aside style={{ padding: "30px 18px 30px 32px", borderRight: "1px solid var(--line)" }}>
          <div className="navlist">
            {SECTIONS.map(([k, label]) => {
              const nUnv = unv.filter((x) => sectionOf(x) === k).length;
              const ok = checks.find((c) => c.s === k)?.ok;
              return (
                <button key={k} className={section === k ? "on" : ""} onClick={() => setSection(k)}>
                  <span style={{ flex: 1 }}>{label}</span>
                  {nUnv ? <span className="pill warn" style={{ height: 20, fontSize: 11 }}>{nUnv}</span>
                    : countFor(k) !== undefined ? <span className="sm faint">{countFor(k)}</span>
                      : ok ? <span className="check" style={{ width: 16, height: 16, fontSize: 10 }}>✓</span> : <span className="sm faint">—</span>}
                </button>
              );
            })}
          </div>
          <div className="sm faint" style={{ marginTop: 24, padding: "0 12px" }}>
            {save === "saved" ? "Enregistré automatiquement" : save === "error" ? "Non enregistré : vérifiez la connexion" : "Enregistrement…"}
          </div>
        </aside>

        <section style={{ padding: "30px 36px", minWidth: 0 }}>
          {extracting && <div className="banner info"><span className="spin" />Lecture de {extracting.filename}…</div>}
          {pendingUpdate && <UpdateBanner u={pendingUpdate} onDone={load} notify={notify} />}
          {section === "identite" && (
            <>
              <h1>Identité</h1>
              <p className="muted" style={{ marginTop: 6 }}>Sur les modèles anonymisés, seules vos initiales apparaissent.</p>
              <div className="panel pad" style={{ marginTop: 22, display: "grid", gridTemplateColumns: "1fr 1fr 180px", gap: 16 }}>
                {[["prenom", "Prénom"], ["nom", "Nom"], ["annees_experience", "Années d'expérience"], ["titre", "Titre affiché sur les dossiers", 2], ["ville", "Ville"]].map(([k, l, span]) => (
                  <div className="field" key={k} style={{ gridColumn: span ? `span ${span}` : undefined }}>
                    <label>{l}</label>
                    <input className={"in" + (unvField(`identite.${k}`) ? " warn" : "")} value={id[k] ?? ""} type={k === "annees_experience" ? "number" : "text"}
                           placeholder={k === "titre" ? "Ex. Développeur C++ / Qt" : ""}
                           onChange={(e) => change((d) => { d.identite[k] = k === "annees_experience" ? (e.target.value ? +e.target.value : null) : e.target.value; },
                             unvField(`identite.${k}`) ? [`identite.${k}`] : [])} />
                  </div>
                ))}
              </div>
            </>
          )}
          {section === "resume" && (
            <>
              <h1>Synthèse</h1>
              <p className="muted" style={{ marginTop: 6 }}>Quelques lignes sur votre profil. Pour une offre, elle peut être reformulée, jamais enrichie.</p>
              <div className="panel pad" style={{ marginTop: 22 }}>
                <textarea className="in" rows={7} value={data.resume.text} placeholder="Ex. Développeur C++/Qt spécialisé dans les IHM de systèmes critiques…"
                          onChange={(e) => change((d) => { d.resume.text = e.target.value; })} />
                <div className="sm faint" style={{ marginTop: 8 }}>{data.resume.text.length} caractères · idéalement 300 à 600</div>
              </div>
            </>
          )}
          {section === "competences" && <Skills data={data} change={change} />}
          {section === "missions" && <Missions data={data} change={change} unvMission={unvMission} />}
          {section === "formations" && (
            <>
              <h1>Formations et certifications</h1>
              <ListEditor title="Formations" items={data.formations} fields={[["annee", "Année", "100px"], ["intitule", "Diplôme"], ["etablissement", "Établissement"]]}
                          onChange={(items) => change((d) => { d.formations = items; })} />
              <ListEditor title="Certifications" items={data.certifications} fields={[["annee", "Année", "100px"], ["intitule", "Certification"]]}
                          onChange={(items) => change((d) => { d.certifications = items; })} />
            </>
          )}
          {section === "langues" && (
            <>
              <h1>Langues</h1>
              <ListEditor items={data.langues} fields={[["langue", "Langue"], ["niveau", "Niveau (B2, C1, courant…)"]]}
                          onChange={(items) => change((d) => { d.langues = items; })} warn={unv.some((x) => x.startsWith("langues"))} />
            </>
          )}
          {section === "disponibilite" && (
            <>
              <h1>Disponibilité et mobilité</h1>
              <div className="panel pad" style={{ marginTop: 22, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                {[["disponibilite", "Disponibilité", "Ex. Immédiate, ou À partir du 1er décembre"], ["mobilite", "Mobilité", "Ex. Toulouse et Occitanie"]].map(([k, l, ph]) => (
                  <div className="field" key={k}><label>{l}</label>
                    <input className="in" value={id[k] || ""} placeholder={ph} onChange={(e) => change((d) => { d.identite[k] = e.target.value; })} /></div>
                ))}
              </div>
            </>
          )}
        </section>

        <aside style={{ padding: "30px 32px 30px 0" }}>
          <div className="panel pad">
            <h3>Votre profil est complet à {pct} %</h3>
            <div className="meter" style={{ margin: "14px 0 18px" }}><span style={{ width: `${pct}%`, background: "var(--pine)" }} /></div>
            <div className="col" style={{ gap: 12 }}>
              {unv.map((x) => (
                <button key={x} className="row sm" style={{ border: "none", background: "none", textAlign: "left", padding: 0 }} onClick={() => setSection(sectionOf(x))}>
                  <span className="check off" style={{ borderColor: "var(--amberline)" }} /><span style={{ flex: 1 }}>{unvLabel(x, p.data)}</span>
                </button>
              ))}
              {checks.filter((c) => !c.ok).map((c) => (
                <button key={c.label} className="row sm" style={{ border: "none", background: "none", textAlign: "left", padding: 0, color: "var(--ink2)" }} onClick={() => setSection(c.s)}>
                  <span className="check off" /><span style={{ flex: 1 }}>{c.label}</span>
                </button>
              ))}
              {!unv.length && checks.every((c) => c.ok) && <div className="sm muted">Tout est prêt pour vos dossiers.</div>}
            </div>
          </div>
          <SayIt onSaid={async (x) => { await flush(); setP(x); setData(structuredClone(x.data)); }} notify={notify} />
          <div className="panel pad" style={{ marginTop: 16 }}>
            <h3>Un nouveau CV ?</h3>
            <p className="sm muted" style={{ marginTop: 6 }}>Seules les nouveautés vous seront proposées, rien n'est écrasé.</p>
            <FileDrop onFiles={sendCv} label="Glissez votre CV ici · PDF ou Word" height={80} />
          </div>
          <button className="btn ghost sm" style={{ marginTop: 10 }} onClick={() => navigate("/")}>Préparer un dossier avec ce profil</button>
        </aside>
      </div>
    </>
  );
}

function unvLabel(path, data) {
  const m = path.match(/^missions\[(\d+)\]\.(\w+)/);
  if (m) {
    const mis = data.missions[+m[1]];
    const what = { debut: "Dates", fin: "Date de fin", secteur: "Secteur" }[m[2]] || "Détail";
    return `${what} de la mission ${mis?.client || ""}`.trim();
  }
  return { "identite.annees_experience": "Années d'expérience", "identite.titre": "Titre", "identite.ville": "Ville" }[path] || "Une information déduite à vérifier";
}

/** Écran de création : déposer son CV, ou passer par LinkedIn, ou remplir à la main. */
function CreateProfile({ reading, found, data, unverified, onCv, onManual, onDone }) {
  const [linkedin, setLinkedin] = useState(false);
  const nUnvMissions = unverified.filter((x) => x.startsWith("missions")).length;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(380px, 560px) 1fr", minHeight: "calc(100vh - 64px)" }} className="cols">
      <div style={{ padding: "64px 56px" }}>
        <h1 style={{ fontSize: 34 }}>Créons votre profil<br />une bonne fois pour toutes</h1>
        <p className="muted" style={{ fontSize: 15.5, marginTop: 14, maxWidth: 420 }}>Il sert à remplir tous vos dossiers de compétences, quel que soit le modèle de l'ESN.</p>
        <FileDrop onFiles={onCv} height={190} big accept=".pdf,.docx,.txt" />
        <div className="row" style={{ margin: "22px 0", color: "var(--ink3)" }}><div style={{ flex: 1, height: 1, background: "var(--line)" }} /><span className="sm">ou</span><div style={{ flex: 1, height: 1, background: "var(--line)" }} /></div>
        <div className="col" style={{ gap: 10 }}>
          <button className="panel row" style={{ padding: "14px 16px", textAlign: "left" }} onClick={() => setLinkedin(!linkedin)}>
            <div style={{ flex: 1 }}><b>Importer depuis LinkedIn</b><div className="sm muted">Exportez votre profil en PDF depuis LinkedIn, puis déposez-le</div></div><span className="faint">{linkedin ? "⌄" : "›"}</span>
          </button>
          {linkedin && (
            <div className="sm muted" style={{ padding: "4px 16px 8px", lineHeight: 1.6 }}>
              Sur LinkedIn, ouvrez votre profil, cliquez sur <b>Plus</b> puis <b>Enregistrer au format PDF</b>. Déposez ensuite ce PDF ci-dessus.
            </div>
          )}
          <button className="panel row" style={{ padding: "14px 16px", textAlign: "left" }} onClick={onManual}>
            <div style={{ flex: 1 }}><b>Remplir à la main</b><div className="sm muted">7 courtes rubriques, environ 10 minutes</div></div><span className="faint">›</span>
          </button>
        </div>
      </div>
      <div style={{ background: "var(--desk2)", padding: "56px 64px" }}>
        {reading && (
          <>
            <div className="sm muted" style={{ marginBottom: 18 }}><b style={{ color: "var(--ink)" }}>{reading}</b> · lecture en cours</div>
            <h2 style={{ marginBottom: 14 }}>Lecture de votre CV…</h2>
            {["Identité", "Synthèse", "Compétences", "Missions", "Formations et langues"].map((s) => (
              <div key={s} className="row" style={{ padding: "11px 0", borderBottom: "1px solid #D2D8E0", color: "var(--ink3)" }}><span className="spin" /><span>{s}</span></div>
            ))}
            <p className="sm muted" style={{ marginTop: 18 }}>Quelques secondes. Rien n'est inventé : chaque information vient de votre CV.</p>
          </>
        )}
        {found && (
          <>
            <h2 style={{ marginBottom: 14 }}>Ce que nous avons trouvé</h2>
            {[
              [!!data.identite.nom, "Identité", [data.identite.prenom, data.identite.nom].filter(Boolean).join(" ") + (data.identite.ville ? `, ${data.identite.ville}` : "")],
              [!!data.resume.text, "Synthèse", data.identite.annees_experience ? `${data.identite.annees_experience} ans d'expérience` : "à compléter"],
              [data.competences.length > 0, `${data.competences.length} compétences`, `regroupées en ${new Set(data.competences.map((c) => c.categorie)).size} familles`],
              [data.missions.length > 0 && !nUnvMissions, `${data.missions.length} missions`, nUnvMissions ? `${nUnvMissions} point(s) à confirmer` : "datées"],
              [data.formations.length + data.langues.length > 0, "Formations et langues", `${data.formations.length} formation(s), ${data.langues.length} langue(s)`],
            ].map(([ok, a, b]) => (
              <div key={a} className="row" style={{ padding: "11px 0", borderBottom: "1px solid #D2D8E0" }}>
                <span className={"check" + (ok ? "" : " amber")}>{ok ? "✓" : "!"}</span><span style={{ flex: 1 }}><b>{a}</b>{b ? ` · ${b}` : ""}</span>
              </div>
            ))}
            <p className="sm muted" style={{ marginTop: 18, maxWidth: 420 }}>Rien n'est inventé : chaque information vient de votre CV. Vérifiez maintenant les points en orange.</p>
            <button className="btn p big" style={{ marginTop: 22 }} onClick={onDone}>Vérifier mon profil</button>
          </>
        )}
        {!reading && !found && (
          <div className="col" style={{ height: "100%", justifyContent: "center", maxWidth: 440 }}>
            <h2>Ce que vous obtenez</h2>
            <p className="muted" style={{ marginTop: 10, lineHeight: 1.6 }}>Vos missions, compétences, formations et langues, rangées une fois pour toutes.
              Ensuite, chaque dossier se remplit dans le modèle de l'ESN en 30 secondes, adapté à l'offre si vous la collez.</p>
          </div>
        )}
      </div>
    </div>
  );
}

export function FileDrop({ onFiles, label, height = 120, big = false, accept = ".pdf,.docx,.txt" }) {
  const [hover, setHover] = useState(false);
  const input = useRef(null);
  return (
    <div className={"drop" + (hover ? " hover" : "")} style={{ height, marginTop: big ? 34 : 14, background: big ? "#fff" : undefined, borderColor: big ? "var(--pine)" : undefined }}
         role="button" tabIndex={0} onClick={() => input.current.click()} onKeyDown={(e) => e.key === "Enter" && input.current.click()}
         onDragOver={(e) => { e.preventDefault(); setHover(true); }} onDragLeave={() => setHover(false)}
         onDrop={(e) => { e.preventDefault(); setHover(false); onFiles([...e.dataTransfer.files]); }}>
      {big ? (
        <>
          <div className="icon">↓</div>
          <b style={{ fontSize: 16.5, marginTop: 14 }}>Déposez votre CV</b>
          <span className="sm muted" style={{ marginTop: 4 }}>PDF ou Word · ou un ancien dossier de compétences</span>
        </>
      ) : <span className="sm muted">{label}</span>}
      <input ref={input} type="file" hidden accept={accept} onChange={(e) => { onFiles([...e.target.files]); e.target.value = ""; }} />
    </div>
  );
}

function SayIt({ onSaid, notify }) {
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [reply, setReply] = useState(null);
  const send = async () => {
    if (!msg.trim()) return;
    setBusy(true);
    try { const r = await api.sayProfile(msg.trim()); setReply(r.reply); if (r.changes.length) { setMsg(""); onSaid(r.profile); } }
    catch (e) { notify(e.message); }
    setBusy(false);
  };
  return (
    <div className="panel pad" style={{ marginTop: 16 }}>
      <h3>Dites-le simplement</h3>
      <p className="sm muted" style={{ marginTop: 6 }}>Décrivez la modification, elle s'applique à votre profil.</p>
      <textarea className="in" rows={2} style={{ marginTop: 12, minHeight: 64 }} value={msg} placeholder="Ex. disponible à partir du 1er décembre"
                onChange={(e) => setMsg(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
      {reply && <div className="sm" style={{ marginTop: 8, color: "var(--ink2)" }}>{reply}</div>}
      <div className="row" style={{ justifyContent: "flex-end", marginTop: 10 }}><button className="btn p" disabled={busy || !msg.trim()} onClick={send}>Appliquer</button></div>
    </div>
  );
}

function Skills({ data, change }) {
  const [label, setLabel] = useState("");
  const cats = Object.entries(CATS).map(([k, l]) => [k, l, data.competences.filter((c) => (c.categorie || "autres") === k)]).filter((x) => x[2].length);
  const remove = (c) => change((d) => { d.competences = d.competences.filter((x) => (x.id ? x.id !== c.id : x.label !== c.label)); });
  return (
    <>
      <div className="row"><h1 style={{ flex: 1 }}>Compétences</h1></div>
      <p className="muted" style={{ marginTop: 6 }}>Les variantes sont regroupées (Qt5 → Qt 5, QtQuick → QML). Le niveau n'est affiché que si le modèle le demande.</p>
      <form className="row" style={{ marginTop: 20 }} onSubmit={(e) => {
        e.preventDefault();
        const items = label.split(",").map((s) => s.trim()).filter(Boolean);
        if (items.length) change((d) => { items.forEach((it) => { if (!d.competences.some((c) => c.label.toLowerCase() === it.toLowerCase())) d.competences.push({ label: it, categorie: "", niveau: null }); }); });
        setLabel("");
      }}>
        <input className="in" style={{ maxWidth: 420 }} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Ajouter (ex. Qt 6, Docker, DO-178C)" />
        <button className="btn">Ajouter</button>
      </form>
      <div className="panel pad" style={{ marginTop: 16 }}>
        {cats.length === 0 && <p className="muted">Aucune compétence pour l'instant.</p>}
        {cats.map(([k, l, list]) => (
          <div key={k} style={{ marginBottom: 14 }}>
            <div className="sm muted" style={{ marginBottom: 8, fontWeight: 520 }}>{l}</div>
            {list.map((c) => (
              <span key={c.id || c.label} className="chip">{c.label}
                <select aria-label={`Niveau ${c.label}`} value={c.niveau || ""} style={{ border: "none", background: "transparent", fontSize: 11.5, color: "var(--ink2)" }}
                        onChange={(e) => change((d) => { const x = d.competences.find((y) => (y.id ? y.id === c.id : y.label === c.label)); x.niveau = e.target.value ? +e.target.value : null; })}>
                  <option value="">niveau</option>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{"●".repeat(n)}</option>)}
                </select>
                <button aria-label={`Retirer ${c.label}`} onClick={() => remove(c)}>✕</button>
              </span>
            ))}
          </div>
        ))}
      </div>
    </>
  );
}

function DateInput({ value, onCommit, placeholder, warn }) {
  const [text, setText] = useState(fmtDate(value));
  useEffect(() => { setText(fmtDate(value)); }, [value]);
  return (
    <input className={"in" + (warn ? " warn" : "")} value={text} placeholder={placeholder} onChange={(e) => setText(e.target.value)}
           onBlur={() => { const v = text.trim() ? parseDate(text) : null; if (v !== null || !text.trim()) onCommit(v); else setText(fmtDate(value)); }} />
  );
}

function Missions({ data, change, unvMission }) {
  const [open, setOpen] = useState(data.missions[0]?.id || null);
  const [drag, setDrag] = useState(null);
  const move = (from, to) => change((d) => { const [m] = d.missions.splice(from, 1); d.missions.splice(to, 0, m); });
  const add = () => {
    const nid = "new" + Date.now();
    change((d) => { d.missions.unshift({ id: undefined, _tmp: nid, client: "", poste: "", debut: "", fin: null, secteur: "", contexte: { text: "" }, realisations: [], environnement: [] }); });
    setOpen(nid);
  };
  return (
    <>
      <div className="row"><h1 style={{ flex: 1 }}>Missions</h1><button className="btn" onClick={add}>+ Ajouter une mission</button></div>
      <p className="muted" style={{ marginTop: 6 }}>Glissez pour réordonner. L'ordre sert par défaut ; une offre peut mettre d'autres missions en avant.</p>
      <div className="col" style={{ gap: 12, marginTop: 22 }}>
        {data.missions.map((m, i) => {
          const key = m._tmp || m.id;
          const warnDebut = unvMission(m.id, "debut");
          const isOpen = open === key;
          const set = (fn, verify = []) => change((d) => fn(d.missions[i]), verify);
          return (
            <div key={key} draggable={!isOpen} onDragStart={() => setDrag(i)} onDragOver={(e) => e.preventDefault()}
                 onDrop={() => { if (drag !== null && drag !== i) move(drag, i); setDrag(null); }}
                 className={"panel" + (isOpen ? " focus" : warnDebut ? " warn" : "")}>
              {!isOpen ? (
                <div className="row" style={{ padding: "16px 22px", cursor: "pointer" }} onClick={() => setOpen(key)}>
                  <span className="faint" style={{ cursor: "grab" }} title="Glisser pour réordonner">⋮⋮</span>
                  <div style={{ flex: 1, minWidth: 0 }}><b>{m.client || "Nouvelle mission"}</b>{m.poste ? ` · ${m.poste}` : ""}
                    <span className="faint sm"> · {fmtDate(m.debut) || "?"} – {m.fin ? fmtDate(m.fin) : "aujourd'hui"}</span>
                    {warnDebut && <span className="sm" style={{ color: "var(--amber)" }}> · dates à confirmer</span>}</div>
                  <span className="sm muted">{m.realisations.filter((r) => r.text).length} réalisation(s)</span>
                  <button className="btn ghost small" aria-label="Monter" disabled={i === 0} onClick={(e) => { e.stopPropagation(); move(i, i - 1); }}>↑</button>
                </div>
              ) : (
                <div className="pad">
                  <div className="row"><h3 style={{ flex: 1 }}>{m.client || "Nouvelle mission"}{m.poste ? ` · ${m.poste}` : ""}</h3>
                    <button className="btn ghost small" onClick={() => setOpen(null)}>Replier</button></div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1.5fr 130px 130px", gap: 14, marginTop: 18 }}>
                    <div className="field"><label>Client</label><input className="in" value={m.client || ""} onChange={(e) => set((x) => { x.client = e.target.value; })} /></div>
                    <div className="field"><label>Poste</label><input className="in" value={m.poste || ""} onChange={(e) => set((x) => { x.poste = e.target.value; })} /></div>
                    <div className="field"><label>Début</label><DateInput value={m.debut} placeholder="MM/AAAA" warn={warnDebut}
                      onCommit={(v) => set((x) => { x.debut = v || ""; }, warnDebut ? [warnDebut] : [])} /></div>
                    <div className="field"><label>Fin</label><DateInput value={m.fin} placeholder="En cours" onCommit={(v) => set((x) => { x.fin = v; })} /></div>
                  </div>
                  <div className="field" style={{ marginTop: 16 }}><label>Contexte (facultatif)</label>
                    <input className="in" value={m.contexte?.text || ""} placeholder="Ex. Programme A350, équipe de 12 personnes"
                           onChange={(e) => set((x) => { x.contexte = { ...(x.contexte || {}), text: e.target.value }; })} /></div>
                  <div className="field" style={{ marginTop: 16 }}><label>Ce que vous avez fait</label>
                    <div style={{ border: "1px solid var(--line)", borderRadius: 8, padding: "4px 0" }}>
                      {m.realisations.map((r, j) => (
                        <div key={r.id || j} className="row" style={{ padding: "0 8px 0 14px", gap: 8 }}>
                          <span className="faint">•</span>
                          <input className="bare" value={r.text} onChange={(e) => set((x) => { x.realisations[j] = { ...x.realisations[j], text: e.target.value }; })}
                                 onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); set((x) => { x.realisations.splice(j + 1, 0, { text: "" }); }); } }} />
                          <button className="btn ghost small" aria-label="Retirer la ligne" onClick={() => set((x) => { x.realisations.splice(j, 1); })}>✕</button>
                        </div>
                      ))}
                      <button className="row bare" style={{ padding: "7px 14px", color: "var(--ink3)", textAlign: "left" }} onClick={() => set((x) => { x.realisations.push({ text: "" }); })}>
                        <span>+</span><span>Ajouter une ligne</span></button>
                    </div>
                  </div>
                  <div className="field" style={{ marginTop: 16 }}><label>Environnement technique</label>
                    <EnvChips items={m.environnement} onChange={(items) => set((x) => { x.environnement = items; })} />
                  </div>
                  <div className="row" style={{ marginTop: 14 }}>
                    <div className="field" style={{ width: 240 }}><label>Secteur</label>
                      <input className={"in" + (unvMission(m.id, "secteur") ? " warn" : "")} value={m.secteur || ""} placeholder="Ex. Aéronautique"
                             onChange={(e) => set((x) => { x.secteur = e.target.value; }, unvMission(m.id, "secteur") ? [unvMission(m.id, "secteur")] : [])} /></div>
                    <span className="sp" />
                    <button className="btn danger" onClick={() => { if (window.confirm("Supprimer cette mission de votre profil ?")) change((d) => { d.missions.splice(i, 1); }); }}>Supprimer la mission</button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
        {data.missions.length === 0 && <div className="panel pad muted">Aucune mission. Ajoutez la plus récente d'abord.</div>}
      </div>
    </>
  );
}

function EnvChips({ items, onChange }) {
  const [v, setV] = useState("");
  return (
    <div>
      {items.map((e, k) => <span key={e + k} className="chip">{e}<button aria-label={`Retirer ${e}`} onClick={() => onChange(items.filter((_, j) => j !== k))}>✕</button></span>)}
      <input className="chip" style={{ width: 150, background: "transparent", border: "1px dashed var(--line)" }} value={v} placeholder="+ ajouter"
             onChange={(e) => setV(e.target.value)}
             onKeyDown={(e) => { if ((e.key === "Enter" || e.key === ",") && v.trim()) { e.preventDefault(); onChange([...items, v.trim()]); setV(""); } }}
             onBlur={() => { if (v.trim()) { onChange([...items, v.trim()]); setV(""); } }} />
    </div>
  );
}

function ListEditor({ title, items, fields, onChange, warn }) {
  return (
    <div className={"panel pad" + (warn ? " warn" : "")} style={{ marginTop: 22 }}>
      {title && <h3 style={{ marginBottom: 12 }}>{title}</h3>}
      {items.map((it, i) => (
        <div key={it.id || i} className="row" style={{ marginBottom: 8 }}>
          {fields.map(([k, l, w]) => (
            <input key={k} className="in" style={w ? { width: w, flex: "none" } : undefined} placeholder={l} value={it[k] || ""}
                   onChange={(e) => onChange(items.map((x, j) => (j === i ? { ...x, [k]: e.target.value } : x)))} />
          ))}
          <button className="btn ghost small" aria-label="Retirer" onClick={() => onChange(items.filter((_, j) => j !== i))}>✕</button>
        </div>
      ))}
      <button className="btn small" onClick={() => onChange([...items, {}])}>+ Ajouter</button>
    </div>
  );
}

function UpdateBanner({ u, onDone, notify }) {
  const [open, setOpen] = useState(false);
  const d = u.diff || {};
  const parts = [];
  if (d.missions?.length) parts.push(`${d.missions.length} mission(s)`);
  if (d.competences?.length) parts.push(`${d.competences.length} compétence(s)`);
  if (d.formations?.length) parts.push(`${d.formations.length} formation(s)`);
  if (Object.keys(d.identite || {}).length) parts.push("des informations d'identité");
  if (d.resume) parts.push("une nouvelle synthèse");
  return (
    <div className="banner info" style={{ flexWrap: "wrap" }}>
      <b>Nouveautés dans {u.filename}</b>
      <span style={{ flex: 1 }}>{parts.join(", ") || "Quelques changements"}</span>
      <button className="btn small ghost" onClick={() => setOpen(!open)}>{open ? "Masquer" : "Voir"}</button>
      <button className="btn small" onClick={() => api.dismissUpdate(u.id).then(onDone)}>Ignorer</button>
      <button className="btn small p" onClick={() => api.applyUpdate(u.id).then(() => { notify("Nouveautés ajoutées à votre profil"); onDone(); })}>Tout ajouter</button>
      {open && (
        <div className="sm" style={{ width: "100%", lineHeight: 1.7 }}>
          {d.missions?.map((m, i) => <div key={"m" + i}>Mission : <b>{m.client}</b> {m.poste ? `· ${m.poste}` : ""} {m.debut ? `· ${fmtDate(m.debut)}` : ""}</div>)}
          {d.competences?.length > 0 && <div>Compétences : {d.competences.map((c) => c.label).join(", ")}</div>}
          {d.formations?.map((f, i) => <div key={"f" + i}>Formation : {f.intitule}</div>)}
          {Object.entries(d.identite || {}).map(([k, v]) => <div key={k}>{k} : {String(v)}</div>)}
          {d.resume && <div>Nouvelle synthèse : « {d.resume.slice(0, 140)}… »</div>}
        </div>
      )}
    </div>
  );
}
