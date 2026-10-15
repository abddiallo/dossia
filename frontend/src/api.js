// Accès à l'API : jeton de session, appels authentifiés, envoi de fichiers, flux d'événements.
const BASE = "/api/v1";
const KEY = "dossia_session";

export function getToken() {
  try { return localStorage.getItem(KEY); } catch { return null; }
}
export function setToken(t) {
  try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY); } catch { /* navigation privée */ }
}

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

export async function authFetch(path, { method = "GET", body, form } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await fetch(BASE + path, { method, headers, body: payload });
  if (res.status === 401) {
    setToken(null);
    if (!location.pathname.startsWith("/connexion")) location.href = "/connexion";
    throw new ApiError(401, "Session expirée");
  }
  if (res.status === 204) return null;
  const isJson = (res.headers.get("content-type") || "").includes("json");
  const data = isJson ? await res.json() : await res.text();
  if (!res.ok) throw new ApiError(res.status, (data && data.detail) || "Une erreur est survenue");
  return data;
}

export const api = {
  requestLink: (email) => authFetch("/auth/request-link", { method: "POST", body: { email } }),
  verify: (token) => authFetch("/auth/verify", { method: "POST", body: { token } }),
  me: () => authFetch("/me"),
  patchMe: (b) => authFetch("/me", { method: "PATCH", body: b }),
  deleteMe: () => authFetch("/me", { method: "DELETE" }),
  drop: (files, pastedText, { autoDossier = true, expected = null } = {}) => {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    if (pastedText) form.append("pasted_text", pastedText);
    form.append("auto_dossier", autoDossier ? "true" : "false");
    if (expected) form.append("expected", expected);
    return authFetch("/drops", { method: "POST", form });
  },
  profile: () => authFetch("/profile"),
  saveProfile: (data, verified_paths = []) => authFetch("/profile", { method: "PUT", body: { data, verified_paths } }),
  updates: () => authFetch("/profile/updates"),
  addSkill: (label, mission_id = null) => authFetch("/profile/skills", { method: "POST", body: { label, mission_id } }),
  sayProfile: (message) => authFetch("/profile/assistant", { method: "POST", body: { message } }),
  match: (b) => authFetch("/match", { method: "POST", body: b }),
  dossierOptions: (id, b) => authFetch(`/dossiers/${id}/options`, { method: "POST", body: b }),
  applyUpdate: (id, accepted = null) => authFetch(`/profile/updates/${id}/apply`, { method: "POST", body: { accepted } }),
  dismissUpdate: (id) => authFetch(`/profile/updates/${id}/dismiss`, { method: "POST" }),
  templates: () => authFetch("/templates"),
  template: (id) => authFetch(`/templates/${id}`),
  patchTemplate: (id, b) => authFetch(`/templates/${id}`, { method: "PATCH", body: b }),
  answerTemplate: (id, answers) => authFetch(`/templates/${id}/answers`, { method: "POST", body: { answers } }),
  validateTemplate: (id) => authFetch(`/templates/${id}/validate`, { method: "POST" }),
  cleanupTemplate: (id) => authFetch(`/templates/${id}/cleanup-request`, { method: "POST" }),
  deleteTemplate: (id) => authFetch(`/templates/${id}`, { method: "DELETE" }),
  dossiers: () => authFetch("/dossiers"),
  dossier: (id) => authFetch(`/dossiers/${id}`),
  createDossier: (b) => authFetch("/dossiers", { method: "POST", body: b }),
  assistant: (id, b) => authFetch(`/dossiers/${id}/assistant`, { method: "POST", body: b }),
  patchSegment: (id, b) => authFetch(`/dossiers/${id}/segments`, { method: "PATCH", body: b }),
  undo: (id) => authFetch(`/dossiers/${id}/undo`, { method: "POST" }),
  regenerate: (id) => authFetch(`/dossiers/${id}/regenerate`, { method: "POST" }),
  emailMe: (id) => authFetch(`/dossiers/${id}/email`, { method: "POST" }),
  deleteDossier: (id) => authFetch(`/dossiers/${id}`, { method: "DELETE" }),
};

// Flux temps réel (SSE) : appelle onEvent(type, data) pour chaque changement côté serveur.
export function subscribe(onEvent) {
  const token = getToken();
  if (!token || typeof EventSource === "undefined") return () => {};
  const es = new EventSource(`${BASE}/events?token=${encodeURIComponent(token)}`);
  for (const type of ["template", "dossier", "profile_update"]) {
    es.addEventListener(type, (e) => {
      try { onEvent(type, JSON.parse(e.data)); } catch { /* ignore */ }
    });
  }
  return () => es.close();
}
