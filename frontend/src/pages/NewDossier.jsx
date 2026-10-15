import React, { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { Steps, useApp, useLive } from "../App.jsx";

/** Nouveau dossier, étapes 1 (l'offre) et 2 (le modèle). L'étape 3 est la page du dossier.  [D1] [D3] */
export default function NewDossier() {
  const { notify } = useApp();
  const navigate = useNavigate();
  const init = useLocation().state || {};
  const [step, setStep] = useState(1);
  const [text, setText] = useState(init.text || "");
  const [m, setM] = useState(null);           // résultat de /match
  const [profile, setProfile] = useState(null);
  const [templates, setTemplates] = useState(null);
  const [tpl, setTpl] = useState(init.template_id || null);
  const [busy, setBusy] = useState(false);
  const [skipped, setSkipped] = useState(false);
  const tplInput = useRef(null);

  const analyze = async (body) => {
    setBusy(true);
    try { setM(await api.match(body)); } catch (e) { notify(e.message); }
    setBusy(false);
  };
  useEffect(() => {
    api.profile().then(setProfile).catch(() => {});
    api.templates().then((ts) => { setTemplates(ts); setTpl((c) => c || ts.find((t) => t.status === "ready")?.id || null); }).catch(() => setTemplates([]));
    if (init.job_posting_id) analyze({ job_posting_id: init.job_posting_id });
    else if (init.text) analyze({ text: init.text });
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps
  useLive((type, data) => { if (type === "template") setTemplates((ts) => [data, ...(ts || []).filter((t) => t.id !== data.id)]); });
  useEffect(() => {
    if (!(templates || []).some((t) => t.status === "analyzing")) return undefined;
    const t = setInterval(() => api.templates().then(setTemplates).catch(() => {}), 3000);
    return () => clearInterval(t);
  }, [templates]);

  const refresh = () => m && analyze({ job_posting_id: m.job_posting.id });
  const generate = async () => {
    setBusy(true);
    try {
      const d = await api.createDossier({ template_id: tpl, job_posting_id: !skipped && m ? m.job_posting.id : null });
      navigate(`/dossiers/${d.id}`, { replace: true });
    } catch (e) { notify(e.message); setBusy(false); }
  };
  const addTemplate = async (files) => {
    if (!files.length) return;
    try {
      const r = await api.drop(files, null, { autoDossier: false, expected: "template" });
      (r.notes || []).forEach((n) => notify(n));
      if (r.template_id) setTpl(r.template_id);
      api.templates().then(setTemplates);
    } catch (e) { notify(e.message); }
  };

  const selected = (templates || []).find((t) => t.id === tpl);
  const steps = [
    { label: "L'offre", meta: step === 2 ? (skipped || !m ? "sans offre" : `${m.have}/${m.total} compétences`) : m?.job_posting?.title?.slice(0, 40),
      state: step === 1 ? "on" : "done", onClick: step === 2 ? () => setStep(1) : null },
    { label: "Le modèle", meta: step === 2 ? null : selected?.esn_name, state: step === 2 ? "on" : "todo" },
    { label: "Le dossier", state: "todo" },
  ];

  return (
    <>
      <Steps steps={steps}><button className="btn ghost" onClick={() => navigate("/")}>Annuler</button></Steps>
      {step === 1 && !m && (
        <div className="content" style={{ maxWidth: 900 }}>
          <h1 style={{ fontSize: 26 }}>Collez l'offre</h1>
          <p className="muted" style={{ marginTop: 6 }}>Le dossier mettra en avant les compétences et missions qui correspondent. Rien n'est ajouté à votre profil sans vous.</p>
          <textarea className="in" rows={14} style={{ marginTop: 22, fontSize: 15 }} value={text} onChange={(e) => setText(e.target.value)}
                    placeholder="Texte de l'offre ou de l'appel d'offres…" aria-label="Texte de l'offre" />
          <div className="row" style={{ marginTop: 18 }}>
            <button className="btn big" onClick={() => { setSkipped(true); setStep(2); }}>Passer cette étape</button><span className="sp" />
            <button className="btn p big" disabled={!text.trim() || busy} onClick={() => analyze({ text })}>{busy ? "Analyse…" : "Comparer à mon profil"}</button>
          </div>
        </div>
      )}
      {step === 1 && m && (
        <div className="cols" style={{ display: "grid", gridTemplateColumns: "1fr 520px", gap: 24, padding: "24px 32px" }}>
          <div className="panel" style={{ padding: "30px 36px", minWidth: 0 }}>
            <div className="row"><h2 style={{ flex: 1 }}>{m.job_posting.title}</h2>
              <button className="btn ghost small" onClick={() => { setM(null); setText(m.job_posting.text); }}>Modifier le texte</button></div>
            <div className="row sm" style={{ margin: "10px 0 20px", gap: 18, color: "var(--ink2)" }}>
              <span><span style={{ display: "inline-block", width: 22, height: 11, background: "var(--hl)", verticalAlign: "middle", marginRight: 6, borderRadius: 2 }} />dans votre profil</span>
              <span><span style={{ display: "inline-block", width: 22, borderBottom: "2px dotted #98A1AF", marginRight: 6, verticalAlign: "middle" }} />absent de votre profil</span>
            </div>
            <OfferText text={m.job_posting.text} spans={m.spans} />
          </div>
          <div className="col" style={{ gap: 16 }}>
            <div className="panel pad">
              <div className="row" style={{ alignItems: "flex-end" }}>
                <div style={{ flex: 1 }}><h3>{verdict(m)}</h3>
                  <p className="sm muted" style={{ marginTop: 4 }}>{m.total ? `${m.have} compétence(s) demandée(s) sur ${m.total} sont dans votre profil.` : "Aucune compétence technique reconnue dans ce texte."}</p></div>
                {m.total > 0 && <div style={{ fontFamily: "'Inter Display'", fontSize: 34, fontWeight: 650, lineHeight: 1 }}>{m.have}<span style={{ fontSize: 18, color: "var(--ink3)" }}>/{m.total}</span></div>}
              </div>
              {m.total > 0 && <div className="meter" style={{ marginTop: 14 }}>
                <span style={{ flex: m.have, background: "var(--hl)" }} /><span style={{ flex: m.total - m.have, background: "var(--desk)" }} /></div>}
            </div>
            {m.skills.some((s) => !s.have) && (
              <div className="panel pad">
                <h3>Absentes de votre profil</h3>
                <p className="sm muted" style={{ marginTop: 4 }}>On ne les ajoute jamais sans vous. Si vous les avez, ajoutez-les en un clic.</p>
                <div className="col" style={{ gap: 10, marginTop: 14 }}>
                  {m.skills.filter((s) => !s.have).map((s) => (
                    <MissingSkill key={s.label} s={s} missions={profile?.data.missions || []} notify={notify} onAdded={refresh} />
                  ))}
                </div>
              </div>
            )}
            <div className="panel pad">
              <h3>Ce qui sera mis en avant</h3>
              <div className="col" style={{ gap: 9, marginTop: 12 }}>
                {m.first_mission && <div className="row sm"><span className="check">✓</span><span style={{ flex: 1 }}><b>Mission {m.first_mission.client} en premier</b>{m.first_mission.skills.length ? ` · ${m.first_mission.skills.join(", ")}` : ""}</span></div>}
                {m.top_skills.length > 0 && <div className="row sm"><span className="check">✓</span><span style={{ flex: 1 }}><b>Compétences triées</b> · {m.top_skills.join(", ")} en tête</span></div>}
                {m.sectors.length > 0 && <div className="row sm"><span className="check">✓</span><span style={{ flex: 1 }}><b>Secteur {m.sectors[0].toLowerCase()}</b> mis en avant quand votre parcours le permet</span></div>}
                <div className="row sm"><span className="check off" /><span style={{ flex: 1, color: "var(--ink2)" }}>Si le modèle impose un nombre de pages, les missions les moins utiles à cette offre sont retirées en premier</span></div>
              </div>
            </div>
            <div className="row" style={{ marginTop: "auto", paddingTop: 8 }}>
              <button className="btn big" onClick={() => { setSkipped(true); setStep(2); }}>Passer cette étape</button><span className="sp" />
              <button className="btn p big" onClick={() => { setSkipped(false); setStep(2); }}>Continuer : choisir le modèle</button>
            </div>
          </div>
        </div>
      )}
      {step === 2 && (
        <div className="content">
          <h1 style={{ fontSize: 26 }}>Quel modèle l'ESN vous a-t-elle envoyé ?</h1>
          <p className="muted" style={{ marginTop: 6 }}>Le dossier reprend exactement sa mise en page : logo, couleurs, tableaux, police.</p>
          {!templates ? <span className="spin" style={{ marginTop: 24 }} /> : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 24, marginTop: 28 }}>
              {templates.map((t) => <TemplateCard key={t.id} t={t} on={t.id === tpl} onPick={() => (t.status === "ready" ? setTpl(t.id) : navigate(`/modeles/${t.id}`))} />)}
              <div className="col" style={{ gap: 14 }}>
                <div className="drop" style={{ height: 362 }} role="button" tabIndex={0} onClick={() => tplInput.current.click()}
                     onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); addTemplate([...e.dataTransfer.files]); }}>
                  <div className="icon" style={{ background: "#fff", border: "1px solid var(--line)", color: "var(--ink2)" }}>+</div>
                  <b style={{ marginTop: 16, fontSize: 15 }}>Nouveau modèle</b>
                  <span className="sm muted" style={{ marginTop: 6, maxWidth: 220 }}>Déposez le .docx reçu de l'ESN, vide ou rempli par un autre consultant</span>
                  <span className="sm" style={{ marginTop: 18, color: "var(--pine)", fontWeight: 560 }}>Reconnu en 10 secondes environ</span>
                </div>
                <input ref={tplInput} type="file" hidden accept=".docx" onChange={(e) => { addTemplate([...e.target.files]); e.target.value = ""; }} />
              </div>
            </div>
          )}
          <div className="row" style={{ marginTop: 34 }}>
            <button className="btn big" onClick={() => setStep(1)}>Retour</button><span className="sp" />
            <span className="sm muted" style={{ marginRight: 10 }}>Environ 30 secondes</span>
            <button className="btn p big" disabled={!selected || selected.status !== "ready" || busy} onClick={generate}>
              {busy ? "Lancement…" : `Générer le dossier${selected?.esn_name ? ` ${selected.esn_name}` : ""}`}
            </button>
          </div>
        </div>
      )}
    </>
  );
}

function verdict(m) {
  if (!m.total) return "Offre enregistrée";
  const r = m.have / m.total;
  return r >= 0.7 ? "Votre profil correspond bien" : r >= 0.4 ? "Votre profil correspond en partie" : "Peu de compétences en commun";
}

/** Texte de l'offre : surligné si la compétence est dans le profil, pointillés sinon. */
export function OfferText({ text, spans }) {
  const parts = [];
  let last = 0;
  spans.forEach((s, i) => {
    if (s.start < last) return;
    if (s.start > last) parts.push(text.slice(last, s.start));
    parts.push(s.have ? <mark key={i}>{text.slice(s.start, s.end)}</mark> : <span key={i} className="miss-u">{text.slice(s.start, s.end)}</span>);
    last = s.end;
  });
  parts.push(text.slice(last));
  return <div className="offer">{parts}</div>;
}

function MissingSkill({ s, missions, notify, onAdded }) {
  const [state, setState] = useState("idle"); // idle | pick | added | ignored
  const [mission, setMission] = useState("");
  if (state === "ignored") return null;
  const add = async () => {
    try {
      await api.addSkill(s.label, mission || null);
      setState("added");
      onAdded();
    } catch (e) { notify(e.message); }
  };
  return (
    <div>
      <div className="row">
        <span className="chip miss" style={{ margin: 0 }}>{s.label}</span><span className="sp" />
        {state === "idle" && <><button className="btn small" onClick={() => setState("pick")}>Je l'ai</button><button className="btn ghost small" onClick={() => setState("ignored")}>Ignorer</button></>}
        {state === "added" && <span className="pill ok">Ajouté à votre profil</span>}
      </div>
      {state === "pick" && (
        <div className="row" style={{ marginTop: 8, gap: 8 }}>
          <select className="in" style={{ flex: 1 }} value={mission} onChange={(e) => setMission(e.target.value)} aria-label="Mission concernée">
            <option value="">Dans mes compétences, sans mission précise</option>
            {missions.map((mi) => <option key={mi.id} value={mi.id}>Utilisé chez {mi.client || "?"}{mi.debut ? ` (${mi.debut.slice(0, 4)})` : ""}</option>)}
          </select>
          <button className="btn p small" onClick={add}>Ajouter</button>
        </div>
      )}
    </div>
  );
}

export function TemplateCard({ t, on, onPick }) {
  return (
    <div className="col" style={{ gap: 14 }}>
      <button onClick={onPick} style={{ padding: 16, borderRadius: 12, background: "var(--paper)", border: on ? "none" : "1px solid var(--line)",
        outline: on ? "2.5px solid var(--pine)" : "none", position: "relative", textAlign: "left" }} aria-pressed={on}>
        {on && <span className="check" style={{ position: "absolute", right: 12, top: 12, width: 24, height: 24, fontSize: 13, zIndex: 3 }}>✓</span>}
        <div className="stack"><div className="sheet" style={{ height: 330 }}>
          {t.thumb_url ? <img src={t.thumb_url} alt={`Aperçu du modèle ${t.esn_name || ""}`} /> : <div className="blank-sheet" style={{ height: "100%" }} />}
          {t.status === "analyzing" && <div className="col" style={{ position: "absolute", inset: 0, background: "rgba(255,255,255,.8)", alignItems: "center", justifyContent: "center", gap: 10 }}><span className="spin" /><span className="sm muted">Lecture du modèle…</span></div>}
        </div></div>
      </button>
      <div>
        <div className="row"><b style={{ flex: 1, fontSize: 15 }}>{t.esn_name || t.filename}</b>
          {t.status === "ready" ? <span className="pill ok">Reconnu</span> : t.status === "analyzing" ? <span className="pill info">Lecture…</span>
            : t.status === "failed" ? <span className="pill err">Illisible</span> : <span className="pill warn">Une question</span>}</div>
        <div className="sm muted" style={{ marginTop: 3 }}>
          {[t.max_pages ? `${t.max_pages} page(s) max` : null, t.anonymize ? "anonymisé (trigramme)" : null, t.usage_count ? `utilisé ${t.usage_count} fois` : null].filter(Boolean).join(" · ") || (t.error || "")}
        </div>
      </div>
    </div>
  );
}
