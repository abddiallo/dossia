import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import { Steps, useApp, useLive } from "../App.jsx";

/** Étape 3 « Le dossier » : aperçu (avec ou sans les adaptations surlignées), réglages, missions incluses, demandes.  [D1] [D3] */
export default function DossierPage() {
  const { id } = useParams();
  const { notify } = useApp();
  const navigate = useNavigate();
  const [d, setD] = useState(null);
  const [msg, setMsg] = useState("");
  const [sending, setSending] = useState(false);
  const [showHl, setShowHl] = useState(true);
  const [page, setPage] = useState(0);
  const [reply, setReply] = useState(null);
  const cvInput = useRef(null);
  const pageRefs = useRef([]);

  const load = useCallback(() => api.dossier(id).then(setD).catch((e) => notify(e.message)), [id, notify]);
  useEffect(() => { load(); }, [load]);
  useLive((type, data) => { if (type === "dossier" && data.id === id) load(); });
  useEffect(() => {  // secours si le temps réel est coupé
    if (!d || !["queued", "generating", "waiting_template", "needs_profile"].includes(d.status)) return undefined;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [d?.status, load]);

  const run = async (fn) => {
    setSending(true);
    try { const r = await fn(); if (r?.dossier) { setD(r.dossier); setReply(r.reply); } else if (r) setD(r); }
    catch (e) { notify(e.message); }
    setSending(false);
  };
  const sendCv = async (files) => {
    if (!files.length) return;
    try { await api.drop(files, null, { autoDossier: false, expected: "cv" }); notify("CV reçu : lecture du profil, puis génération du dossier…"); load(); }
    catch (e) { notify(e.message); }
  };

  if (!d) return <div className="content"><span className="spin" /></div>;
  const busy = ["queued", "generating", "waiting_template"].includes(d.status);
  const noProfile = d.status === "needs_profile";
  const templateQuestion = d.status === "waiting_template" && d.template_status && !["analyzing", "ready"].includes(d.template_status);
  const settings = d.settings || {};
  const pages = showHl && d.highlight_preview_urls?.length ? d.highlight_preview_urls : d.preview_urls;
  const fid = d.fidelity_report;
  const fidOk = fid && fid.level === "ok";
  const missions = d.missions || [];
  const setOpt = (b) => run(() => api.dossierOptions(id, b));
  const toggleMission = (mid) => {
    const hidden = missions.filter((m) => m.state === "hidden").map((m) => m.id);
    setOpt({ hidden_missions: hidden.includes(mid) ? hidden.filter((x) => x !== mid) : [...hidden, mid] });
  };

  const steps = [
    { label: "L'offre", meta: d.job_posting ? d.job_posting.title.slice(0, 30) : "sans offre", state: "done" },
    { label: "Le modèle", meta: d.esn_name, state: "done", onClick: () => navigate(`/modeles/${d.template_id}`) },
    { label: "Le dossier", meta: busy ? "génération…" : d.pages ? `prêt · ${d.pages} page(s)` : null, state: "on" },
  ];

  return (
    <>
      <Steps steps={steps}>
        {d.pdf_url && <a className="btn" href={d.pdf_url}>Télécharger le PDF</a>}
        {d.docx_url && <a className="btn p" style={{ marginLeft: 10 }} href={d.docx_url}>Télécharger le Word</a>}
      </Steps>
      <div className="cols" style={{ display: "grid", gridTemplateColumns: "1fr 400px", minHeight: "calc(100vh - 122px)" }}>
        <div style={{ padding: "26px 40px", background: "var(--desk2)", minWidth: 0 }}>
          {noProfile ? (
            <div className="banner warn">
              <span style={{ flex: 1 }}><b>Il manque votre CV.</b> Le modèle {d.esn_name || ""} est prêt : déposez votre CV (PDF ou Word) et le dossier se génère automatiquement.</span>
              <button className="btn p" onClick={() => cvInput.current.click()}>Déposer mon CV</button>
              <input ref={cvInput} type="file" hidden accept=".pdf,.docx,.txt" onChange={(e) => { sendCv([...e.target.files]); e.target.value = ""; }} />
            </div>
          ) : templateQuestion ? (
            <div className="banner warn"><span style={{ flex: 1 }}><b>Le modèle a une question.</b> Répondez-y, puis le dossier se génère.</span>
              <Link className="btn p" to={`/modeles/${d.template_id}`}>Répondre</Link></div>
          ) : d.status === "failed" ? (
            <div className="banner err"><span style={{ flex: 1 }}><b>Le dossier n'a pas pu être généré.</b> {d.error}</span>
              <button className="btn" onClick={() => run(() => api.regenerate(id))}>Réessayer</button></div>
          ) : busy ? (
            <div className="banner info"><span className="spin" /><span>Le dossier se prépare : adaptation, remplissage du modèle, mise en page. Environ 30 secondes.</span></div>
          ) : d.highlight_preview_urls?.length > 0 ? (
            <div className="row" style={{ marginBottom: 16 }}>
              <button className={"toggle" + (showHl ? "" : " off")} aria-pressed={showHl} aria-label="Montrer les adaptations" onClick={() => setShowHl(!showHl)} />
              <span className="sm"><b>Montrer les adaptations à l'offre</b> <span className="muted">· surlignées en jaune sur l'aperçu seulement, le fichier téléchargé n'est pas surligné</span></span>
            </div>
          ) : null}

          <div style={{ display: "flex", gap: 28, alignItems: "flex-start", opacity: busy ? 0.45 : 1 }}>
            <div className="col" style={{ gap: 22, flex: 1, maxWidth: 720, minWidth: 0 }}>
              {pages.length ? pages.map((u, i) => (
                <div key={u} className="sheet" ref={(el) => { pageRefs.current[i] = el; }}><img src={u} alt={`Page ${i + 1} du dossier`} /></div>
              )) : <div className="sheet blank-sheet" style={{ aspectRatio: "210 / 297" }} />}
            </div>
            {pages.length > 1 && (
              <div className="col" style={{ gap: 10, position: "sticky", top: 140 }}>
                {pages.map((u, i) => (
                  <button key={u} className="col" style={{ gap: 6, border: "none", background: "none", alignItems: "center" }}
                          onClick={() => { setPage(i); pageRefs.current[i]?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>
                    <div className="sheet" style={{ width: 96, outline: page === i ? "2px solid var(--pine)" : "none", outlineOffset: 3 }}><img src={u} alt="" /></div>
                    <span className="sm muted">Page {i + 1}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <aside style={{ background: "var(--paper)", borderLeft: "1px solid var(--line)", padding: "26px 28px", display: "flex", flexDirection: "column",
          position: "sticky", top: 122, height: "calc(100vh - 122px)", overflowY: "auto" }}>
          {fid && (
            <div className="row" style={{ padding: "12px 14px", background: fidOk ? "var(--pinebg)" : "var(--amberbg)", borderRadius: 10 }}>
              <span className={"check" + (fidOk ? "" : " amber")}>{fidOk ? "✓" : "!"}</span>
              <span className="sm" style={{ flex: 1 }}>
                <b>{fidOk ? `Mise en page ${d.esn_name || "du modèle"} respectée` : "À vérifier avant l'envoi"}</b><br />
                <span className="muted">{fidOk ? `police, couleurs, logo${d.pages ? `, ${d.pages} page(s)${d.max_pages ? ` sur ${d.max_pages}` : ""}` : ""}`
                  : fid.checks.filter((c) => !c.ok).map((c) => c.label).join(" · ")}</span>
              </span>
            </div>
          )}

          {d.question && !busy && (
            <div className="panel warn" style={{ padding: 16, marginTop: 18 }}>
              <b>Une question avant l'envoi</b>
              <p className="sm" style={{ marginTop: 6, lineHeight: 1.5 }}>{d.question.text}</p>
              <div className="row wrap" style={{ marginTop: 10, gap: 8 }}>
                {d.question.choices.map((c, i) => <button key={c} className={"btn small" + (i === 0 ? " p" : "")} disabled={sending} onClick={() => run(() => api.assistant(id, { choice: c }))}>{c}</button>)}
              </div>
            </div>
          )}

          <h3 style={{ marginTop: 24 }}>Réglages</h3>
          <div className="col" style={{ gap: 14, marginTop: 14 }}>
            <div className="row"><span style={{ flex: 1 }}>Nombre de pages maximum</span>
              <div className="row" style={{ gap: 0, border: "1px solid var(--line)", borderRadius: 8 }}>
                <button className="btn ghost small" aria-label="Une page de moins" disabled={busy || sending || (settings.max_pages || 2) <= 1} onClick={() => setOpt({ max_pages: (settings.max_pages || d.pages || 2) - 1 })}>−</button>
                <b style={{ width: 28, textAlign: "center" }}>{settings.max_pages || "—"}</b>
                <button className="btn ghost small" aria-label="Une page de plus" disabled={busy || sending} onClick={() => setOpt({ max_pages: (settings.max_pages || d.pages || 1) + 1 })}>+</button>
              </div></div>
            <div className="row"><span style={{ flex: 1 }}>Anonymiser {settings.anonymize ? "(initiales)" : ""}</span>
              <button className={"toggle" + (settings.anonymize ? "" : " off")} aria-pressed={!!settings.anonymize} aria-label="Anonymiser" disabled={busy || sending} onClick={() => setOpt({ anonymize: !settings.anonymize })} /></div>
            {d.job_posting && (
              <div className="row"><span style={{ flex: 1 }}>Adapter à l'offre</span>
                <button className={"toggle" + (settings.adapt ? "" : " off")} aria-pressed={!!settings.adapt} aria-label="Adapter à l'offre" disabled={busy || sending} onClick={() => setOpt({ adapt: !settings.adapt })} /></div>
            )}
          </div>

          {missions.length > 0 && (
            <>
              <h3 style={{ marginTop: 24 }}>Missions incluses</h3>
              <div className="col" style={{ gap: 10, marginTop: 12 }}>
                {missions.map((m) => (
                  <label key={m.id} className="row sm" style={{ cursor: busy ? "default" : "pointer" }}>
                    <button className={"check" + (m.state === "included" ? "" : " off")} aria-pressed={m.state === "included"} disabled={busy || sending} onClick={() => toggleMission(m.id)}>{m.state === "included" ? "✓" : ""}</button>
                    <span style={{ flex: 1, color: m.state === "included" ? "var(--ink)" : "var(--ink2)" }}>{m.client}{m.period ? ` · ${m.period}` : ""}
                      {m.state === "dropped" && <span className="faint"> (retirée pour tenir en {settings.max_pages || d.max_pages} pages)</span>}</span>
                  </label>
                ))}
              </div>
            </>
          )}

          <div style={{ marginTop: "auto", paddingTop: 26 }}>
            <h3>Demander une modification</h3>
            {reply && <div className="sm" style={{ marginTop: 8, padding: "10px 12px", background: "var(--desk)", borderRadius: 8, lineHeight: 1.5 }}>{reply}</div>}
            <div className="row wrap" style={{ marginTop: 10, gap: 0 }}>
              {(d.suggestions || []).map((s) => <button key={s} className="chip" disabled={sending || busy} onClick={() => run(() => api.assistant(id, { message: s }))}>{s}</button>)}
            </div>
            <form className="row" style={{ marginTop: 6, border: "1px solid var(--line)", borderRadius: 10, padding: "6px 6px 6px 14px", gap: 8 }}
                  onSubmit={(e) => { e.preventDefault(); if (msg.trim()) run(() => api.assistant(id, { message: msg.trim() })).then(() => setMsg("")); }}>
              <input className="bare" value={msg} onChange={(e) => setMsg(e.target.value)} disabled={busy} placeholder="Ex. : enlève Java des compétences" aria-label="Votre demande" />
              <button className="btn p" style={{ height: 34 }} disabled={sending || busy || !msg.trim()}>Envoyer</button>
            </form>
            <div className="col sm" style={{ marginTop: 14, gap: 8, alignItems: "flex-start" }}>
              {d.can_undo && !busy && <button className="bare" style={{ width: "auto", color: "var(--ink2)" }} onClick={() => run(() => api.undo(id))}>↶ Annuler la dernière modification</button>}
              <Link to={`/dossiers/${id}/sources`} style={{ color: "var(--ink2)" }}>D'où vient chaque texte</Link>
              {["ready", "needs_answer"].includes(d.status) && <button className="bare" style={{ width: "auto", color: "var(--ink2)" }} onClick={() => api.emailMe(id).then(() => notify("Envoyé sur votre adresse e-mail")).catch((e) => notify(e.message))}>Me l'envoyer par e-mail</button>}
            </div>
          </div>
        </aside>
      </div>
    </>
  );
}
