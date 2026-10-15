import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { Top, useApp, useLive } from "../App.jsx";
import { TemplateCard } from "./NewDossier.jsx";

/** Mes modèles d'ESN : galerie avec aperçu, dépôt d'un nouveau modèle. */
export default function TemplatesPage() {
  const { notify } = useApp();
  const navigate = useNavigate();
  const [items, setItems] = useState(null);
  const [q, setQ] = useState("");
  const input = useRef(null);

  const load = () => api.templates().then(setItems).catch((e) => notify(e.message));
  useEffect(() => { load(); }, []);  // eslint-disable-line react-hooks/exhaustive-deps
  useLive((type, data) => { if (type === "template") setItems((xs) => [data, ...(xs || []).filter((x) => x.id !== data.id)]); });
  useEffect(() => {  // secours si le temps réel est coupé
    if (!(items || []).some((t) => t.status === "analyzing")) return undefined;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [items]);  // eslint-disable-line react-hooks/exhaustive-deps

  const upload = async (files) => {
    if (!files.length) return;
    try {
      const r = await api.drop(files, null, { autoDossier: false, expected: "template" });
      (r.notes || []).forEach((x) => notify(x));
      const n = r.detected.filter((d) => d.detected_as === "template").length;
      if (n) notify(n > 1 ? `${n} modèles reçus : lecture en cours…` : "Modèle reçu : lecture en cours, environ 10 secondes.");
      else if (!r.notes?.length) notify("Ce fichier n'a pas été reconnu comme un modèle Word (.docx).");
      load();
    } catch (e) { notify(e.message); }
  };
  const shown = (items || []).filter((t) => !q || (t.esn_name || t.filename || "").toLowerCase().includes(q.toLowerCase()));

  return (
    <>
      <Top title="Mes modèles d'ESN">
        <input className="in" style={{ maxWidth: 280 }} placeholder="Rechercher un modèle…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Rechercher un modèle" />
        <button className="btn p" onClick={() => input.current.click()}>Déposer un modèle .docx</button>
        <input ref={input} type="file" accept=".docx" multiple hidden onChange={(e) => { upload([...e.target.files]); e.target.value = ""; }} />
      </Top>
      <div className="content">
        <p className="muted" style={{ marginBottom: 24 }}>Un modèle reconnu une fois sert pour tous vos dossiers chez cette ESN.</p>
        {!items ? <span className="spin" /> : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 24 }}>
            {shown.map((t) => <TemplateCard key={t.id} t={t} on={false} onPick={() => navigate(`/modeles/${t.id}`)} />)}
            <div className="drop" style={{ height: 362 }} role="button" tabIndex={0} onClick={() => input.current.click()}
                 onKeyDown={(e) => e.key === "Enter" && input.current.click()}
                 onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); upload([...e.dataTransfer.files]); }}>
              <div className="icon" style={{ background: "#fff", border: "1px solid var(--line)", color: "var(--ink2)" }}>+</div>
              <b style={{ marginTop: 16, fontSize: 15 }}>Déposez le modèle d'une ESN</b>
              <span className="sm muted" style={{ marginTop: 6, maxWidth: 220 }}>Vide ou rempli par un autre consultant : les zones sont reconnues automatiquement</span>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
