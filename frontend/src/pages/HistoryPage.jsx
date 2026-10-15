import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { FileIcon, StatusPill, Top, useApp, useLive } from "../App.jsx";

/** Historique : quel dossier, pour quelle ESN, quelle mission, quand. */
export default function HistoryPage() {
  const { notify } = useApp();
  const [items, setItems] = useState(null);
  const [q, setQ] = useState("");
  useEffect(() => { api.dossiers().then(setItems); }, []);
  useLive((type, data) => { if (type === "dossier") setItems((xs) => [data, ...(xs || []).filter((x) => x.id !== data.id)]); });

  const shown = (items || []).filter((d) => !q || `${d.esn_name} ${d.job_posting?.title || ""}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <Top title="Mes dossiers"><Link className="btn p" to="/">Nouveau dossier</Link></Top>
      <div className="content">
        <input className="in" style={{ maxWidth: 360, marginBottom: 16 }} placeholder="Rechercher (ESN, mission…)" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="card" style={{ padding: "4px 20px" }}>
          {!items && <div style={{ padding: 20 }}><span className="spin" /></div>}
          {items && shown.length === 0 && <p className="muted" style={{ padding: 20 }}>Aucun dossier.</p>}
          {shown.map((d) => (
            <div key={d.id} className="list-row">
              <FileIcon />
              <div style={{ flex: 1, minWidth: 0 }}>
                <Link to={`/dossiers/${d.id}`}><b style={{ color: "#1c2330" }}>{d.esn_name || "Dossier"}</b></Link>
                <div className="sm muted">{d.job_posting?.title || "Sans fiche de poste"} · {new Date(d.created_at).toLocaleDateString("fr-FR")}
                  {d.channel === "email" ? " · reçu par e-mail" : ""}</div>
              </div>
              <StatusPill status={d.status} />
              {d.docx_url && <a className="btn" href={d.docx_url}>.docx</a>}
              {d.pdf_url && <a className="btn" href={d.pdf_url}>PDF</a>}
              <button className="btn" title="Supprimer" onClick={() => confirm("Supprimer ce dossier ?") &&
                api.deleteDossier(d.id).then(() => setItems(items.filter((x) => x.id !== d.id))).catch((e) => notify(e.message))}>✕</button>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
