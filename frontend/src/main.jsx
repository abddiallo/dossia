import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import "./styles.css";

/** Jamais d'écran blanc : en cas d'erreur d'affichage, on montre l'erreur et un bouton pour recharger. */
class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch(error, info) { console.error("[Dossia]", error, info); }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div style={{ padding: 40, fontFamily: "system-ui", maxWidth: 640 }}>
        <h2>Un problème d'affichage est survenu</h2>
        <p style={{ color: "#5b6577" }}>Vos fichiers et dossiers sont enregistrés. Rechargez la page ; si l'erreur revient, envoyez-nous ce message :</p>
        <pre style={{ background: "#f4f6fa", padding: 12, borderRadius: 8, whiteSpace: "pre-wrap" }}>{String(this.state.error?.message || this.state.error)}</pre>
        <button onClick={() => { this.setState({ error: null }); window.location.reload(); }}>Recharger</button>
      </div>
    );
  }
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ErrorBoundary>
  </React.StrictMode>
);
