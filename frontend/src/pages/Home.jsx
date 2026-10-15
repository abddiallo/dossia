import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { StatusPill, useApp, useLive } from "../App.jsx";
import { FileDrop } from "./ProfilePage.jsx";

/** Accueil : l'offre (facultative) + le modèle de l'ESN → « Préparer le dossier ».  [D1] */
export default function Home() {
  const { notify } = useApp();
  const navigate = useNavigate();
  const [profile, setProfile] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [dossiers, setDossiers] = useState([]);
  const [updates, setUpdates] = useState([]);
  const [offer, setOffer] = useState("");
  const [posting, setPosting] = useState(null); // offre déposée en PDF
  const [tpl, setTpl] = useState(null);
  const [busy, setBusy] = useState(false);
  const tplInput = useRef(null);
  const offerInput = useRef(null);

  const load = useCallback(() => {
    api.profile().then(setProfile).catch(() => {});
    api.templates().then((ts) => {
      setTemplates(ts);
      setTpl((cur) => cur || ts.find((t) => t.status === "ready")?.id || null);
    }).catch(() => {});
    api.dossiers().then(setDossiers).catch(() => {});
    api.updates().then(setUpdates).catch(() => {});
  }, []);
  useEffect(load, [load]);
  useLive((type, data) => {
    if (type === "template") {
      setTemplates((ts) => [data, ...ts.filter((t) => t.id !== data.id)]);
      if (data.status === "ready") setTpl((cur) => cur || data.id);
    }
    if (type === "dossier") setDossiers((ds) => [data, ...ds.filter((d) => d.id !== data.id)]);
    if (type === "profile_update") load();
  });
  // secours si le temps réel est coupé
  const analyzing = templates.some((t) => t.status === "analyzing") || updates.some((u) => u.status === "extracting");
  useEffect(() => {
    if (!analyzing) return undefined;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [analyzing, load]);

  const addTemplate = async (files) => {
    if (!files.length) return;
    try {
      const r = await api.drop(files, null, { autoDossier: false, expected: "template" });
      (r.notes || []).forEach((n) => notify(n));
      if (r.template_id) { setTpl(r.template_id); notify("Modèle reçu : lecture en cours, environ 10 secondes."); }
      load();
    } catch (e) { notify(e.message); }
  };
  const addOfferFile = async (files) => {
    if (!files.length) return;
    try {
      const r = await api.drop(files, null, { autoDossier: false });
      if (r.job_posting_id) { setPosting({ id: r.job_posting_id, name: files[0].name }); setOffer(""); }
      else notify("Ce fichier ne ressemble pas à une offre. Collez plutôt son texte.");
    } catch (e) { notify(e.message); }
  };
  const addCv = async (files) => {
    if (!files.length) return;
    try { await api.drop(files, null, { autoDossier: false, expected: "cv" }); notify("CV reçu : seules les nouveautés vous seront proposées."); load(); }
    catch (e) { notify(e.message); }
  };

  const prepare = async () => {
    if (!tpl) return;
    if (offer.trim() || posting) {
      navigate("/nouveau", { state: { text: offer.trim() || null, job_posting_id: posting?.id || null, template_id: tpl } });
      return;
    }
    setBusy(true);
    try { const d = await api.createDossier({ template_id: tpl }); navigate(`/dossiers/${d.id}`); }
    catch (e) { notify(e.message); }
    setBusy(false);
  };

  const data = profile?.data;
  const emptyProfile = data && !data.missions.length && !data.competences.length;
  const ident = data?.identite || {};
  const shownTemplates = templates.slice(0, 4);
  const selected = templates.find((t) => t.id === tpl);
  const pendingUpdate = updates.find((u) => u.status === "ready");
  const extracting = updates.find((u) => u.status === "extracting");
  const recent = dossiers.filter((d) => d.preview_urls?.length || ["ready", "needs_answer"].includes(d.status)).slice(0, 5);

  return (
    <div className="content cols" style={{ display: "grid", gridTemplateColumns: "1fr 380px", gap: 24, paddingTop: 36 }}>
      <div style={{ minWidth: 0 }}>
        <h1>Bonjour{ident.prenom ? ` ${ident.prenom}` : ""}, quel dossier préparez-vous ?</h1>
        <p className="muted" style={{ fontSize: 15.5, marginTop: 8 }}>Ajoutez l'offre et le modèle de l'ESN. Votre profil fait le reste.</p>

        {emptyProfile && (
          <div className="banner warn" style={{ marginTop: 22, marginBottom: 0 }}>
            <span style={{ flex: 1 }}><b>Commencez par votre profil.</b> Déposez votre CV une fois : il remplira tous vos dossiers.</span>
            <Link className="btn p" to="/profil">Créer mon profil</Link>
          </div>
        )}

        <div className="panel cols" style={{ marginTop: 26, padding: 26, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
          <div className="panel" style={{ padding: 24, display: "flex", flexDirection: "column", minHeight: 250 }}>
            <div className="row"><h3>L'offre</h3><span className="sp" /><span className="faint sm">facultatif</span></div>
            {posting ? (
              <div className="row" style={{ marginTop: 14, padding: "12px 14px", background: "var(--desk)", borderRadius: 8 }}>
                <span style={{ flex: 1 }}><b>{posting.name}</b><div className="sm muted">offre enregistrée</div></span>
                <button className="btn ghost small" onClick={() => setPosting(null)}>Retirer</button>
              </div>
            ) : (
              <textarea className="in" value={offer} onChange={(e) => setOffer(e.target.value)} aria-label="Texte de l'offre"
                        style={{ marginTop: 14, flex: 1, background: "var(--desk)", border: "none", minHeight: 140 }}
                        placeholder={"Collez le texte de l'offre ou de l'appel d'offres…\n\nLe dossier mettra en avant les compétences et missions qui correspondent."} />
            )}
            <div className="row sm" style={{ marginTop: 12, color: "var(--ink2)" }}>ou <button className="bare" style={{ width: "auto", textDecoration: "underline", padding: 0 }} onClick={() => offerInput.current.click()}>déposer un PDF</button></div>
            <input ref={offerInput} type="file" hidden accept=".pdf,.docx,.txt" onChange={(e) => { addOfferFile([...e.target.files]); e.target.value = ""; }} />
          </div>

          <div className="panel" style={{ padding: 24, minHeight: 250 }}>
            <h3>Le modèle de l'ESN</h3>
            <div className="col" style={{ gap: 8, marginTop: 14 }}>
              {shownTemplates.map((t) => (
                <TemplateChoice key={t.id} t={t} on={t.id === tpl} onPick={() => (t.status === "ready" ? setTpl(t.id) : navigate(`/modeles/${t.id}`))} />
              ))}
              {templates.length === 0 && <p className="sm muted">Déposez le modèle Word (.docx) que l'ESN vous a envoyé, vide ou rempli par un autre consultant.</p>}
              <button className="bare sm row" style={{ color: "var(--ink2)", textAlign: "left", padding: "6px 2px", gap: 6 }} onClick={() => tplInput.current.click()}>+ Déposer un nouveau modèle .docx</button>
              <input ref={tplInput} type="file" hidden accept=".docx" multiple onChange={(e) => { addTemplate([...e.target.files]); e.target.value = ""; }} />
              {templates.length > 4 && <Link className="sm" to="/modeles">Voir les {templates.length} modèles</Link>}
            </div>
          </div>

          <div className="row" style={{ gridColumn: "1 / -1", flexWrap: "wrap" }}>
            <span className="sm muted">
              {data && !emptyProfile ? <>Profil utilisé : <b style={{ color: "var(--ink)" }}>{[ident.prenom, ident.nom].filter(Boolean).join(" ")}{ident.titre ? ` · ${ident.titre}` : ""}</b>
                {profile.updated_at ? `, mis à jour le ${new Date(profile.updated_at).toLocaleDateString("fr-FR", { day: "numeric", month: "long" })}` : ""}</> : "Votre profil n'est pas encore créé."}
            </span>
            <span className="sp" />
            <button className="btn p big" disabled={!selected || selected.status !== "ready" || busy} onClick={prepare}>
              {busy ? "Préparation…" : "Préparer le dossier"}
            </button>
          </div>
        </div>

        {recent.length > 0 && (
          <>
            <div className="row" style={{ margin: "30px 0 14px" }}><h3 style={{ flex: 1 }}>Vos derniers dossiers</h3><Link className="sm" to="/historique">Tout voir</Link></div>
            <div className="row" style={{ gap: 22, alignItems: "flex-start", flexWrap: "wrap" }}>
              {recent.map((d) => (
                <Link key={d.id} to={`/dossiers/${d.id}`} className="col" style={{ gap: 10, width: 150, color: "var(--ink)" }}>
                  <div className="stack"><div className="sheet" style={{ height: 200 }}>
                    {d.preview_urls?.[0] ? <img src={d.preview_urls[0]} alt="" /> : <div className="blank-sheet" style={{ height: "100%" }} />}
                  </div></div>
                  <div><b className="sm">{d.esn_name || "Dossier"}{d.job_posting ? ` · ${d.job_posting.title.slice(0, 22)}` : ""}</b>
                    <div className="sm faint">{new Date(d.created_at).toLocaleDateString("fr-FR", { day: "numeric", month: "long" })}</div></div>
                </Link>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="col" style={{ gap: 18 }}>
        <div className="panel pad">
          <div className="row"><h3>Mon profil</h3><span className="sp" />{data && (emptyProfile ? <span className="pill warn">À créer</span> : <span className="pill ok">Prêt</span>)}</div>
          {data && !emptyProfile ? (
            <>
              <div className="row" style={{ marginTop: 16, gap: 14 }}>
                <div className="av" style={{ width: 48, height: 48, fontSize: 15 }}>{(ident.prenom?.[0] || "") + (ident.nom?.[0] || "")}</div>
                <div><b style={{ fontSize: 15 }}>{ident.titre || "Titre à compléter"}</b>
                  <div className="sm muted">{[ident.annees_experience ? `${ident.annees_experience} ans d'expérience` : "", ident.ville].filter(Boolean).join(" · ")}</div></div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, marginTop: 18 }}>
                <div className="stat"><b>{data.missions.length}</b><span className="sm muted">missions</span></div>
                <div className="stat"><b>{data.competences.length}</b><span className="sm muted">compétences</span></div>
                <div className="stat"><b>{data.formations.length + data.certifications.length}</b><span className="sm muted">formations</span></div>
              </div>
              {profile.unverified_paths?.length > 0 && (
                <Link to="/profil" className="row" style={{ marginTop: 16, padding: "11px 13px", background: "var(--amberbg)", borderRadius: 8, color: "#6B4510" }}>
                  <span className="sm" style={{ flex: 1 }}><b>{profile.unverified_paths.length} information(s) à vérifier</b></span><span className="sm" style={{ fontWeight: 600 }}>Vérifier</span>
                </Link>
              )}
              {pendingUpdate && (
                <Link to="/profil" className="row" style={{ marginTop: 10, padding: "11px 13px", background: "var(--pinebg)", borderRadius: 8, color: "var(--ink)" }}>
                  <span className="sm" style={{ flex: 1 }}><b>Nouveautés de votre dernier CV</b> à confirmer</span><span className="sm" style={{ fontWeight: 600, color: "var(--pine)" }}>Voir</span>
                </Link>
              )}
              <Link className="btn" style={{ width: "100%", marginTop: 12 }} to="/profil">Modifier mon profil</Link>
            </>
          ) : (
            <>
              <p className="sm muted" style={{ marginTop: 10, lineHeight: 1.5 }}>Déposez votre CV (PDF ou Word) : votre profil est créé automatiquement.</p>
              <Link className="btn p" style={{ width: "100%", marginTop: 14 }} to="/profil">Créer mon profil</Link>
            </>
          )}
        </div>
        {data && !emptyProfile && (
          <div className="panel pad">
            <h3>Un nouveau CV ?</h3>
            <p className="sm muted" style={{ marginTop: 6 }}>Déposez-le : seules les nouveautés vous seront proposées, rien n'est écrasé.</p>
            {extracting ? <div className="row sm muted" style={{ marginTop: 14 }}><span className="spin" />Lecture de {extracting.filename}…</div>
              : <FileDrop onFiles={addCv} label="Glissez votre CV ici · PDF ou Word" height={86} />}
          </div>
        )}
      </div>
    </div>
  );
}

export function TemplateChoice({ t, on, onPick }) {
  const status = t.status;
  return (
    <button className={"choice" + (on ? " on" : "")} onClick={onPick}>
      <div className="mini-doc">{t.thumb_url && <img src={t.thumb_url} alt="" />}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <b>{t.esn_name || t.filename}</b>
        <div className="sm muted">
          {status === "ready" ? (t.usage_count ? `utilisé ${t.usage_count} fois` : "prêt") : status === "analyzing" ? "lecture du modèle…"
            : status === "failed" ? (t.error || "illisible") : "une question à régler"}
        </div>
      </div>
      {status === "analyzing" ? <span className="spin" /> : status === "ready" ? (on && <span className="check">✓</span>) : <StatusPill status={status === "complex" ? "needs_answer" : status} />}
    </button>
  );
}
