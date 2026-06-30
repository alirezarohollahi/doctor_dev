export const state = {
  user: null,
  view: "dashboard",
  nodes: [],
  cores: [],
  inboundCatalog: [],
  stats: null,
  summary: null,
  runtimeCache: null,
  integrity: null,
  logSources: [],
  logs: { source: "panel", level: "all", q: "", limit: 300, lines: [], path: "", error: "", auto: false },
  selectedNodeId: "",
  selectedNodeTab: "overview",
  selectedCoreId: "",
  selectedCoreTab: "overview",
  draftNode: null,
  draftCore: null,
  dirtyCore: false,
  loading: new Set(),
  lastRefresh: "never",
};

export function setView(view) {
  state.view = view || "dashboard";
  location.hash = `#/${state.view}`;
}

export function startLoading(key) { state.loading.add(key); }
export function stopLoading(key) { state.loading.delete(key); }
export function isLoading(key) { return state.loading.has(key); }
