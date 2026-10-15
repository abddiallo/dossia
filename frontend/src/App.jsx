import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { api, getToken, setToken, subscribe } from "./api.js";
import Login from "./pages/Login.jsx";
import Home from "./pages/Home.jsx";
import DossierPage from "./pages/DossierPage.jsx";
import SourcesPage from "./pages/SourcesPage.jsx";
import ProfilePage from "./pages/ProfilePage.jsx";
import TemplatesPage from "./pages/TemplatesPage.jsx";
import TemplatePage from "./pages/TemplatePage.jsx";
import HistoryPage from "./pages/HistoryPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import NewDossier from "./pages/NewDossier.jsx";

const Ctx = createContext(null);
export const useApp = () => useContext(Ctx);

/** S'abonne aux événements temps réel (template | dossier | profile_update). */
export function useLive(handler) {
  const { addListener } = useApp();
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => addListener((type, data) => ref.current(type, data)), [addListener]);
}

export default function App() {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [toast, setToast] = useState(null);
  const listeners = useRef(new Set());
  const location = useLocation();

  const notify = useCallback((msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  }, []);
  const addListener = useCallback((fn) => {
    listeners.current.add(fn);
    return () => listeners.current.delete(fn);
  }, []);

  useEffect(() => {
    if (!getToken()) { setReady(true); return; }
    api.me().then(setUser).catch(() => setToken(null)).finally(() => setReady(true));
  }, []);

  useEffect(() => {
    if (!user) return undefined;
    return subscribe((type, data) => listeners.current.forEach((fn) => fn(type, data)));
  }, [user]);

  const logout = () => { setToken(null); setUser(null); };
  const value = { user, setUser, notify, addListener, logout };

  if (!ready) return <div className="center"><span className="spin" /></div>;
  if (!user && !location.pathname.startsWith("/connexion")) return <Navigate to="/connexion" replace />;

  return (
    <Ctx.Provider value={value}>
      {location.pathname.startsWith("/connexion") ? (
        <Login />
      ) : (
        <div className="app">
          <TopNav />
          <main>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/nouveau" element={<NewDossier />} />
              <Route path="/dossiers/:id" element={<DossierPage />} />
              <Route path="/dossiers/:id/sources" element={<SourcesPage />} />
              <Route path="/profil" element={<ProfilePage />} />
              <Route path="/modeles" element={<TemplatesPage />} />
              <Route path="/modeles/:id" element={<TemplatePage />} />
              <Route path="/historique" element={<HistoryPage />} />
              <Route path="/parametres" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      )}
      {toast && <div className="toast">{toast}</div>}
    </Ctx.Provider>
  );
}

function TopNav() {
  const { user, logout } = useApp();
  const location = useLocation();
  const [counts, setCounts] = useState({});
  const [open, setOpen] = useState(false);
  useEffect(() => {
    setOpen(false);
    Promise.all([api.dossiers().catch(() => null), api.templates().catch(() => null)])
      .then(([d, t]) => setCounts({ d: d?.length, t: t?.length }));
  }, [location.pathname]);
  const planLabel = { free: "Offre gratuite · 3 dossiers par mois", freelance: "Offre Freelance", team: "Offre Équipe" }[user?.plan] || "";
  const tabs = [["/", "Accueil"], ["/profil", "Mon profil"], ["/historique", "Dossiers", counts.d], ["/modeles", "Modèles", counts.t]];
  const isActive = (to) => (to === "/" ? location.pathname === "/" :
    to === "/historique" ? location.pathname.startsWith("/historique") || location.pathname.startsWith("/dossiers") || location.pathname.startsWith("/nouveau")
      : location.pathname.startsWith(to));
  return (
    <header className="topnav">
      <NavLink to="/" className="brand"><i /><span>Dossia</span></NavLink>
      <nav className="navtabs">
        {tabs.map(([to, label, n]) => (
          <NavLink key={to} to={to} className={() => (isActive(to) ? "active" : "")}>
            {label}{n ? <span className="n">{n}</span> : null}
          </NavLink>
        ))}
      </nav>
      <span className="sp" />
      <button className="av" aria-label="Mon compte" onClick={() => setOpen(!open)}>{initials(user)}</button>
      {open && (
        <div className="menu">
          <div className="who"><b>{user?.full_name || user?.email}</b><div className="sm muted">{planLabel}</div></div>
          <NavLink to="/parametres">Paramètres et adresse de dépôt</NavLink>
          <button onClick={logout}>Se déconnecter</button>
          <div className="sm faint" style={{ padding: "6px 12px 4px" }}>version 2.0.0</div>
        </div>
      )}
    </header>
  );
}

export function initials(user) {
  return (user?.full_name || user?.email || "?").split(/[\s@.]+/).filter(Boolean).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

/** En-tête de page : titre et actions. */
export function Top({ title, crumb, children }) {
  return (
    <div className="pagehead">
      <h1>{crumb && <span className="crumb">{crumb}</span>}{title}</h1>
      {children}
    </div>
  );
}

/** Les 3 étapes du parcours « Nouveau dossier ». steps = [{label, meta, state: done|on|todo, onClick}] */
export function Steps({ steps, children }) {
  return (
    <div className="steps">
      {steps.map((s, i) => (
        <React.Fragment key={s.label}>
          {i > 0 && <div className={"stbar" + (s.state !== "todo" ? " done" : "")} />}
          <button className={"st " + s.state} onClick={s.onClick} disabled={!s.onClick} style={{ cursor: s.onClick ? "pointer" : "default" }}>
            <span className="c">{s.state === "done" ? "✓" : i + 1}</span>{s.label}{s.meta && <span className="meta">{s.meta}</span>}
          </button>
        </React.Fragment>
      ))}
      <span className="sp" />
      {children}
    </div>
  );
}

export function FileIcon({ ext = "DOCX" }) {
  const colors = { DOCX: "#2B5FD9", PDF: "#B42318", TXT: "#4A5568" };
  return <div className="ficon" style={{ background: colors[ext] || "#555" }}>{ext}</div>;
}

export const STATUS = {
  waiting_template: ["En attente", "info"], queued: ["En file", "info"], generating: ["Génération…", "info"],
  needs_answer: ["1 question", "warn"], needs_profile: ["CV manquant", "warn"], ready: ["Prêt", "ok"], failed: ["Échec", "err"],
  analyzing: ["Analyse…", "info"], complex: ["À vérifier", "warn"], extracting: ["Lecture…", "info"],
  waiting_template_ready: ["En attente", "info"],
};

export function StatusPill({ status }) {
  const [label, cls] = STATUS[status] || [status, "info"];
  return <span className={`pill ${cls}`}>{label}</span>;
}
