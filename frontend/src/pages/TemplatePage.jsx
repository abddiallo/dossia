import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import { useApp, useLive } from "../App.jsx";

const POLICIES = [["keep_recent", "Garder les missions les plus récentes"], ["shorten", "Raccourcir les descriptions"],
  ["allow_extra_page", "Autoriser une page de plus"]];

/** Un modèle d'ESN : aperçu, au plus une ou deux questions, ce qui a été reconnu, réglages.  [D2] [D4] */
export default function TemplatePage() {
  const { id } = useParams();
  const { notify } = useApp();
  const navigate = useNavigate();
  const [t, setT] = useState(null);
  const [answers, setAnswers] = useState({});
  const [view, setView] = useState("source");
  const [name, setName] = useState("");
  const [showSettings, setShowSettings] = useState(false);

  const load = useCallback(() => api.template(id).then((x) => { setT(x); setName(x.esn_name || ""); }).catch((e) => notify(e.message)), [id, notify]);
  useEffect(() => { load(); }, [load]);
  useLive((type, data) => { if (type === "template" && data.id === id) load(); });
  useEffect(() => {
    if (t?.status !== "analyzing") return undefined;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [t?.status, load]);

  if (!t) return <div className="content"><span className="spin" /></div>;
  const pending = t.zones.filter((z) => z.status === "pending");
  const recognized = [...new Set(t.zones.filter((z) => z.status !== "pending" && z.kind !== "remove").map((z) => z.label).filter(Boolean))];
  const report = t.fidelity_report;
  const pages = view === "test" && t.test_previews?.length ? t.test_previews : (t.source_previews?.length ? t.source_previews : t.test_previews || []);
  const title = t.esn_name || t.filename;

  const sendAnswers = async () => {
    const full = {};
    for (const z of pending) full[z.key] = answers[z.key] || z.suggested || z.choices?.[0]?.value;
    try { setT(await api.answerTemplate(id, full)); setAnswers({}); notify("C'est noté, le modèle est relu…"); }
    catch (e) { notify(e.message); }
  };
  const patch = async (b) => { try { setT(await api.patchTemplate(id, b)); } catch (e) { notify(e.message); } };
  const validate = async () => {
    try { await api.validateTemplate(id); notify("Modèle validé"); navigate("/", { replace: true }); } catch (e) { notify(e.message); }
  };
  const generate = async () => {
    try { if (!t.from_library) await api.validateTemplate(id); const d = await api.createDossier({ template_id: id }); navigate(`/dossiers/${d.id}`); }
    catch (e) { notify(e.message); }
  };

  return (
    <div className="cols" style={{ display: "grid", gridTemplateColumns: "1fr 470px", minHeight: "calc(100vh - 64px)" }}>
      <div style={{ background: "var(--desk2)", padding: "24px 0 34px", display: "flex", flexDirection: "column", alignItems: "center", minWidth: 0 }}>
        {t.test_previews?.length > 0 && t.source_previews?.length > 0 && (
          <div className="row" style={{ marginBottom: 18, background: "var(--paper)", borderRadius: 9, padding: 3, gap: 2, border: "1px solid var(--line)" }}>
            {[["source", "Modèle d'origine"], ["test", "Essai avec mon profil"]].map(([k, l]) => (
              <button key={k} className="btn small" style={{ border: "none", background: view === k ? "var(--ink)" : "transparent", color: view === k ? "#fff" : "var(--ink2)" }} onClick={() => setView(k)}>{l}</button>
            ))}
          </div>
        )}
        <div className="col" style={{ gap: 22, width: "min(560px, 90%)" }}>
          {t.status === "analyzing" && !pages.length && <div className="sheet blank-sheet col" style={{ aspectRatio: "210 / 297", alignItems: "center", justifyContent: "center" }}><span className="spin" /></div>}
          {pages.map((u, i) => <div key={u} className="sheet"><img src={u} alt={`Page ${i + 1} du modèle`} /></div>)}
        </div>
      </div>

      <aside style={{ background: "var(--paper)", borderLeft: "1px solid var(--line)", padding: "34px 32px", display: "flex", flexDirection: "column" }}>
        {t.status === "analyzing" ? <span className="pill info" style={{ alignSelf: "flex-start" }}>Lecture du modèle…</span>
          : t.status === "failed" ? <span className="pill err" style={{ alignSelf: "flex-start" }}>Illisible</span>
            : t.from_library ? <span className="pill ok" style={{ alignSelf: "flex-start" }}>Déjà connu : reconnu sans question</span>
              : <span className="pill ok" style={{ alignSelf: "flex-start" }}>Modèle lu · {t.zones_total - t.zones_pending} zones sur {t.zones_total}</span>}
        <h1 style={{ fontSize: 26, marginTop: 14 }}>
          {t.status === "analyzing" ? `${title} : lecture en cours` : t.status === "failed" ? `${title} n'a pas pu être lu`
            : pending.length === 1 ? `${title} : une seule question` : pending.length ? `${title} : ${pending.length} questions` : `${title} est prêt`}
        </h1>
        <p className="muted" style={{ marginTop: 8 }}>
          {t.status === "failed" ? (t.error || "Demandez à l'ESN la version Word (.docx) du modèle.")
            : pending.length ? "Tout le reste a été reconnu. Nous gardons la mise en page telle quelle." : t.status === "analyzing" ? "Environ 10 secondes." : "Chaque dossier reprendra exactement cette mise en page."}
        </p>

        {pending.map((z) => {
          const val = answers[z.key] || z.suggested || z.choices?.[0]?.value;
          return (
            <div key={z.key} className="panel warn" style={{ marginTop: 24, padding: 20 }}>
              <b>{z.question || `Que faut-il mettre dans « ${z.label} » ?`}</b>
              {z.sample && <p className="sm muted" style={{ marginTop: 4 }}>« {z.sample.slice(0, 90)} »</p>}
              <div className="col" style={{ gap: 8, marginTop: 14 }} role="radiogroup">
                {(z.choices || []).map((c) => (
                  <button key={c.value} role="radio" aria-checked={val === c.value} className="choice" style={val === c.value ? { border: "1.5px solid var(--pine)" } : undefined}
                          onClick={() => setAnswers({ ...answers, [z.key]: c.value })}>
                    <span style={{ width: 16, height: 16, borderRadius: "50%", border: val === c.value ? "5px solid var(--pine)" : "1.5px solid #B8C0CC", flex: "none" }} />
                    <span style={{ flex: 1 }}>{c.label}</span>{z.suggested === c.value && <span className="sm faint">suggéré</span>}
                  </button>
                ))}
              </div>
            </div>
          );
        })}

        {recognized.length > 0 && (
          <>
            <h3 style={{ marginTop: 26 }}>Reconnu dans le modèle</h3>
            <div className="col" style={{ gap: 9, marginTop: 12 }}>
              {recognized.slice(0, 9).map((l) => <div key={l} className="row sm"><span className="check">✓</span><span style={{ flex: 1 }}>{l}</span></div>)}
              <div className="row sm"><span className="check">✓</span><span style={{ flex: 1 }}>
                {((x) => x.charAt(0).toUpperCase() + x.slice(1))([t.max_pages ? `limite : ${t.max_pages} page(s)` : null, t.constraints?.anonymize ? "nom en initiales" : null, "logo et pied de page conservés"].filter(Boolean).join(", "))}</span></div>
            </div>
          </>
        )}
        {report && report.level !== "ok" && (
          <div className="banner warn sm" style={{ marginTop: 18, marginBottom: 0 }}>
            <span>Essai : {report.checks.filter((c) => !c.ok).map((c) => c.label).join(" · ")}</span>
          </div>
        )}

        <button className="bare sm" style={{ marginTop: 22, textAlign: "left", color: "var(--ink2)" }} onClick={() => setShowSettings(!showSettings)}>
          {showSettings ? "▾" : "▸"} Réglages du modèle
        </button>
        {showSettings && (
          <div className="col" style={{ gap: 14, marginTop: 10 }}>
            <div className="field"><label>Nom de l'ESN</label>
              <div className="row"><input className="in" value={name} onChange={(e) => setName(e.target.value)} />
                <button className="btn" disabled={name === (t.esn_name || "")} onClick={() => patch({ esn_name: name })}>OK</button></div></div>
            <div className="field"><label>Nombre de pages maximum {t.original_pages ? `(modèle : ${t.original_pages})` : ""}</label>
              <input className="in" type="number" min={1} max={10} value={t.max_pages || ""} placeholder="Pas de limite"
                     onChange={(e) => e.target.value && patch({ max_pages: +e.target.value })} /></div>
            <div className="field"><label>Si le profil est trop long</label>
              {POLICIES.map(([v, l]) => (
                <label key={v} className="row sm" style={{ padding: "4px 0" }}>
                  <input type="radio" checked={(t.overflow_policy || "keep_recent") === v} onChange={() => patch({ overflow_policy: v })} /> {l}
                </label>
              ))}</div>
            <div className="row">
              <a className="btn small" href={t.source_url}>Fichier d'origine</a>
              {t.status === "complex" && <button className="btn small" onClick={() => api.cleanupTemplate(id).then(() => notify("Demande envoyée")).catch((e) => notify(e.message))}>Faire remettre au propre</button>}
              <span className="sp" />
              <button className="btn small danger" onClick={() => window.confirm("Supprimer ce modèle ?") && api.deleteTemplate(id).then(() => navigate("/modeles"))}>Supprimer</button>
            </div>
          </div>
        )}

        <div className="row" style={{ marginTop: "auto", paddingTop: 26 }}>
          {pending.length ? (
            <><span className="sp" /><button className="btn p big" onClick={sendAnswers}>Valider ma réponse</button></>
          ) : t.status === "ready" ? (
            <>
              {t.test_previews?.length > 0 && view !== "test" ? <button className="btn big" onClick={() => setView("test")}>Voir un essai</button> : <button className="btn big" onClick={validate}>Valider le modèle</button>}
              <span className="sp" />
              <button className="btn p big" onClick={generate}>Générer un dossier</button>
            </>
          ) : t.status === "failed" ? <button className="btn big" onClick={() => navigate("/modeles")}>Retour aux modèles</button> : null}
        </div>
      </aside>
    </div>
  );
}
