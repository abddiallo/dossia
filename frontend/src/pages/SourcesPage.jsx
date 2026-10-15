import React, { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api.js";
import { Top, useApp, useLive } from "../App.jsx";

const FIELD_LABELS = {
  titre: "Titre", resume: "Synthèse", competences: "Compétences", "mission.client": "Client",
  "mission.poste": "Poste", "mission.contexte": "Contexte", "mission.realisation": "Réalisation",
  "mission.env": "Environnement", formations: "Formation", certifications: "Certification", langues: "Langue",
  disponibilite: "Disponibilité", mobilite: "Mobilité",
};
const HIDEABLE = new Set(["resume", "mission.client", "mission.contexte", "mission.realisation", "formations",
  "certifications", "langues", "disponibilite", "mobilite"]);
const OP = { copy: ["Repris tel quel", "ok"], rephrase: ["Reformulé", "info"], reorder: ["Réordonné", "info"], user_edit: ["Retouché", "warn"] };

/** Sources des reformulations + retouches avant envoi.  [D3] */
export default function SourcesPage() {
  const { id } = useParams();
  const { notify } = useApp();
  const [d, setD] = useState(null);
  const [filter, setFilter] = useState("changed");
  const [editing, setEditing] = useState(null);

  const load = useCallback(() => api.dossier(id).then(setD), [id]);
  useEffect(() => { load(); }, [load]);
  useLive((type, data) => { if (type === "dossier" && data.id === id) load(); });

  const patch = async (body) => {
    try { setD(await api.patchSegment(id, body)); notify("Modification enregistrée, mise à jour du dossier…"); }
    catch (e) { notify(e.message); }
    setEditing(null);
  };

  if (!d) return <><Top title="Sources" /><div className="content"><span className="spin" /></div></>;
  const segs = (d.segments || []).filter((s) => s.final_text || s.hidden);
  const shown = filter === "changed" ? segs.filter((s) => s.op !== "copy" || s.hidden || s.risk !== "none") : segs;
  const s = d.origin_stats || {};
  const pct = (x) => `${Math.round((x || 0) * 100)} %`;

  return (
    <>
      <Top title="Sources et retouches" crumb={`Dossiers / ${d.esn_name || ""} /`}>
        <Link className="btn p" to={`/dossiers/${id}`}>Retour à l'aperçu</Link>
      </Top>
      <div className="content">
        <div className="banner ok">
          <b style={{ color: "#0e7f53" }}>Garantie</b>
          <span style={{ flex: 1 }}>Chaque phrase du dossier provient de votre profil. L'adaptation reformule et réordonne : elle n'ajoute ni compétence, ni mission, ni date.</span>
        </div>
        <div className="grid cols" style={{ gridTemplateColumns: "1fr 300px", alignItems: "start" }}>
          <div>
            <div className="tabs">
              <button className={filter === "changed" ? "on" : ""} onClick={() => setFilter("changed")}>Modifiés ({segs.filter((x) => x.op !== "copy" || x.hidden).length})</button>
              <button className={filter === "all" ? "on" : ""} onClick={() => setFilter("all")}>Tout le dossier ({segs.length})</button>
            </div>
            {shown.length === 0 && <div className="card pad muted">Rien n'a été modifié : tout le dossier reprend votre profil tel quel.</div>}
            {shown.map((seg) => (
              <div key={seg.key} className="card" style={{ padding: 16, marginBottom: 12, borderColor: seg.risk === "review" ? "#f3dcae" : undefined, opacity: seg.hidden ? 0.6 : 1 }}>
                <div className="row wrap" style={{ marginBottom: 10 }}>
                  <b>{FIELD_LABELS[seg.field] || seg.field}</b>
                  <span className={`pill ${OP[seg.op]?.[1]}`}>{OP[seg.op]?.[0]}</span>
                  {seg.risk === "review" && <span className="pill warn">À vérifier</span>}
                  {seg.hidden && <span className="pill err">Masqué pour cet envoi</span>}
                  <span style={{ flex: 1 }} />
                  {(seg.op === "rephrase" || seg.op === "user_edit") && (
                    <button className="btn" onClick={() => patch({ key: seg.key, decision: "reverted" })}>Revenir à l'original</button>
                  )}
                  {seg.risk === "review" && <button className="btn p" onClick={() => patch({ key: seg.key, decision: "accepted" })}>Accepter</button>}
                  {!["competences", "mission.client", "mission.env"].includes(seg.field) && (
                    <button className="btn" onClick={() => setEditing({ key: seg.key, text: seg.final_text, profile: false })}>Retoucher</button>
                  )}
                  {HIDEABLE.has(seg.field) && (
                    <button className="btn" onClick={() => patch({ key: seg.key, hidden: !seg.hidden })}>
                      {seg.hidden ? "Réafficher" : seg.field === "mission.client" ? "Masquer la mission" : "Masquer"}</button>
                  )}
                </div>
                {seg.risk_reason && <div className="banner warn sm" style={{ marginBottom: 10 }}>{seg.risk_reason}</div>}
                {editing?.key === seg.key ? (
                  <div>
                    <textarea className="in" rows={3} value={editing.text} onChange={(e) => setEditing({ ...editing, text: e.target.value })} />
                    <div className="row" style={{ marginTop: 8 }}>
                      <label className="row sm"><input type="checkbox" checked={editing.profile}
                                                       onChange={(e) => setEditing({ ...editing, profile: e.target.checked })} />
                        Reporter aussi dans mon profil</label>
                      <span style={{ flex: 1 }} />
                      <button className="btn" onClick={() => setEditing(null)}>Annuler</button>
                      <button className="btn p" onClick={() => patch({ key: seg.key, final_text: editing.text, apply_to_profile: editing.profile })}>Enregistrer</button>
                    </div>
                  </div>
                ) : (
                  <div className="grid cols" style={{ gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                    <div><label className="lbl">Dans votre profil</label><div style={{ fontSize: 13, lineHeight: 1.6, background: "#f7f8fa", borderRadius: 8, padding: 10 }}>{seg.original_text || "—"}</div></div>
                    <div><label className="lbl">Dans ce dossier</label>
                      <div style={{ fontSize: 13, lineHeight: 1.6, background: "#f7f8fa", borderRadius: 8, padding: 10 }}>
                        {seg.op === "copy" ? seg.final_text : <span className="diff-add">{seg.final_text}</span>}
                      </div></div>
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="card pad" style={{ position: "sticky", top: 84 }}>
            <h3>Origine des éléments</h3>
            <div className="sm muted" style={{ margin: "4px 0 14px" }}>Ce dossier, par rapport à votre profil</div>
            {[["Repris tel quel", s.copy], ["Reformulé", s.rephrase], ["Réordonné", s.reorder], ["Retouché par vous", s.user_edit], ["Ajouté par l'IA", s.added]].map(([l, v]) => (
              <div key={l} className="row" style={{ justifyContent: "space-between", padding: "9px 0", borderBottom: "1px solid #eef0f4" }}><span>{l}</span><b>{pct(v)}</b></div>
            ))}
            <p className="sm muted" style={{ marginTop: 14, lineHeight: 1.5 }}>Les retouches et masquages ne concernent que ce dossier, sauf si vous cochez « Reporter aussi dans mon profil ».</p>
          </div>
        </div>
      </div>
    </>
  );
}
