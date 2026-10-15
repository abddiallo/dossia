import React, { useState } from "react";
import { api, getToken } from "../api.js";
import { Top, useApp } from "../App.jsx";

/** Paramètres : dépôt par e-mail, préférences par défaut, données personnelles (RGPD). */
export default function SettingsPage() {
  const { user, setUser, notify, logout } = useApp();
  const [senders, setSenders] = useState((user.allowed_senders || []).join(", "));
  const [defaults, setDefaults] = useState({ adapt: true, ...(user.defaults || {}) });
  const [name, setName] = useState(user.full_name || "");

  const save = async () => {
    try {
      setUser(await api.patchMe({ full_name: name, allowed_senders: senders.split(",").map((s) => s.trim()).filter(Boolean), defaults }));
      notify("Paramètres enregistrés");
    } catch (e) { notify(e.message); }
  };
  const exportData = async () => {
    const res = await fetch("/api/v1/me/export", { headers: { Authorization: `Bearer ${getToken()}` } });
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "dossia-export.zip"; a.click();
  };
  const del = async () => {
    if (!confirm("Supprimer définitivement votre compte, votre profil, vos modèles et vos dossiers ?")) return;
    await api.deleteMe(); logout();
  };
  const toggle = (k) => setDefaults({ ...defaults, [k]: !defaults[k] });

  return (
    <>
      <Top title="Paramètres"><button className="btn p" onClick={save}>Enregistrer</button></Top>
      <div className="content grid cols" style={{ gridTemplateColumns: "1fr 1fr", alignItems: "start" }}>
        <div className="card pad">
          <h3>Compte</h3>
          <label className="lbl" style={{ marginTop: 14 }}>Nom</label>
          <input className="in" value={name} onChange={(e) => setName(e.target.value)} />
          <label className="lbl" style={{ marginTop: 12 }}>E-mail</label>
          <div className="in" style={{ background: "#f7f8fa" }}>{user.email}</div>
          <h3 style={{ marginTop: 22 }}>Dépôt par e-mail</h3>
          <p className="sm muted" style={{ margin: "6px 0 10px", lineHeight: 1.5 }}>Transférez les e-mails des ESN à cette adresse : le dossier vous revient en réponse.</p>
          <div className="in" style={{ fontWeight: 600, color: "#3d6dfd" }}>{user.inbound_address}</div>
          <label className="lbl" style={{ marginTop: 12 }}>Autres adresses autorisées à déposer (séparées par des virgules)</label>
          <input className="in" value={senders} onChange={(e) => setSenders(e.target.value)} placeholder="ex. mon.adresse.pro@exemple.fr" />
          <p className="sm muted" style={{ marginTop: 6 }}>Les e-mails venant d'autres adresses sont ignorés, par sécurité.</p>
        </div>
        <div className="grid">
          <div className="card pad">
            <h3>Par défaut</h3>
            {[["adapt", "Adapter le dossier à la fiche de poste"], ["anonymize", "Toujours anonymiser mon nom (initiales)"],
              ["anonymize_clients", "Toujours anonymiser les clients"]].map(([k, l]) => (
              <label key={k} className="row" style={{ padding: "9px 0" }}>
                <input type="checkbox" checked={!!defaults[k]} onChange={() => toggle(k)} /> {l}
              </label>
            ))}
            <p className="sm muted">Sinon, l'anonymisation suit ce que demande le modèle de l'ESN.</p>
          </div>
          <div className="card pad">
            <h3>Mes données</h3>
            <p className="sm muted" style={{ margin: "6px 0 12px", lineHeight: 1.5 }}>
              Hébergement en Europe. Vos CV et dossiers ne servent jamais à entraîner un modèle d'IA.
              Les fichiers sources sont supprimés automatiquement après 6 mois.
            </p>
            <div className="row wrap">
              <button className="btn" onClick={exportData}>Exporter mes données</button>
              <button className="btn" onClick={logout}>Se déconnecter</button>
              <button className="btn danger" onClick={del}>Supprimer mon compte</button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
