import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, setToken } from "../api.js";
import { useApp } from "../App.jsx";

export default function Login() {
  const { setUser } = useApp();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const token = params.get("token");
    if (!token) return;
    setBusy(true);
    api.verify(token)
      .then((r) => { setToken(r.session_token); setUser(r.user); navigate("/", { replace: true }); })
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false));
  }, [params, navigate, setUser]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try { setSent(await api.requestLink(email)); } catch (err) { setError(err.message); }
    setBusy(false);
  };

  return (
    <div className="center" style={{ background: "var(--desk)" }}>
      <div className="card" style={{ width: 420, padding: 32 }}>
        <div className="brand" style={{ marginBottom: 22 }}><i /><span>Dossia</span></div>
        <h2 style={{ fontSize: 22, marginBottom: 6 }}>Vos dossiers de compétences, sans effort</h2>
        <p className="muted" style={{ marginBottom: 22, lineHeight: 1.5 }}>
          Déposez le modèle de l'ESN : le dossier est rempli à partir de votre profil, au format exact demandé.
        </p>
        {params.get("token") && busy ? (
          <div className="row"><span className="spin" /> Connexion…</div>
        ) : sent ? (
          <div className="banner ok" style={{ flexDirection: "column", alignItems: "flex-start" }}>
            <b>Vérifiez votre boîte mail</b>
            <span className="sm">Un lien de connexion a été envoyé à {email}.</span>
            {sent.dev_link && <a className="sm" href={sent.dev_link}>Mode développement : se connecter directement</a>}
          </div>
        ) : (
          <form onSubmit={submit}>
            <label className="lbl">Adresse e-mail</label>
            <input className="in" type="email" required value={email} autoFocus
                   onChange={(e) => setEmail(e.target.value)} placeholder="vous@exemple.fr" />
            <button className="btn p big" style={{ width: "100%", justifyContent: "center", marginTop: 14 }} disabled={busy}>
              {busy ? "Envoi…" : "Recevoir mon lien de connexion"}
            </button>
            <p className="sm muted" style={{ marginTop: 12 }}>Pas de mot de passe. Le compte est créé automatiquement.</p>
          </form>
        )}
        {error && <div className="banner err" style={{ marginTop: 14 }}>{error}</div>}
      </div>
    </div>
  );
}
