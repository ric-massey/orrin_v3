import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import * as THREE from "three";
import { Cpu, Maximize2, Minus, PanelLeft, Plus, Search, Spline } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import FnDetailDrawer from "./FnDetailDrawer";
import PanelInfo from "./PanelInfo";
import StaleBadge from "./StaleBadge";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { API, colorFor } from "@/lib/cognitive";
import { fetchJSON } from "@/lib/fetchJSON";
import { useLexicon } from "@/lib/lexicon";
import { useNavTarget } from "@/lib/navigate";
import { FnCatalog, TelemetryState } from "@/lib/telemetry";
import { PanelSubtitle } from "./Lex";
import { CAM_Z, type Settings, SKEY, loadSettings, buildLayout } from "./cognitiveSphere/layout";
import { ControlsPanel } from "./cognitiveSphere/ControlsPanel";
import { CognitionExplorer } from "./cognitiveSphere/CognitionExplorer";
import { Scene } from "./cognitiveSphere/Scene";


// ── camera fly-to (for search focus + reset) ──────────────────────────────────
export default function CognitiveSphere({ telemetry }: { telemetry: TelemetryState }) {
  const [catalog, setCatalog] = useState<FnCatalog | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [settings, setSettings] = useState<Settings>(loadSettings);
  const [query, setQuery] = useState("");
  const [focusNode, setFocusNode] = useState<string | null>(null);
  // Cluster fly-to (click a subsystem name on the globe) — node focus wins.
  const [focusSub, setFocusSub] = useState<string | null>(null);
  const [resetTick, setResetTick] = useState(0);
  const tries = useRef(0);
  const controlsRef = useRef<any>(null);

  // Easy maneuvering: step zoom by moving the camera along its view ray.
  const zoom = (factor: number) => {
    const c = controlsRef.current;
    if (!c) return;
    const cam = c.object as THREE.Camera;
    const dir = (cam.position as THREE.Vector3).clone().sub(c.target);
    const dist = Math.min(c.maxDistance, Math.max(c.minDistance, dir.length() * factor));
    (cam.position as THREE.Vector3).copy(c.target).add(dir.setLength(dist));
    c.update();
  };

  useEffect(() => localStorage.setItem(SKEY, JSON.stringify(settings)), [settings]);

  useEffect(() => {
    if (catalog) return;
    let stop = false;
    const load = () =>
      fetchJSON<FnCatalog>(`${API}/catalog`)
        .then((d: FnCatalog) => {
          if (stop) return;
          if (d && d.functions && Object.keys(d.functions).length) setCatalog(d);
          else if (tries.current++ < 30) setTimeout(load, 2000);
        })
        .catch(() => !stop && tries.current++ < 30 && setTimeout(load, 2000));
    load();
    return () => {
      stop = true;
    };
  }, [catalog]);

  // Gap 1: node usage sizes froze at boot — the /catalog endpoint is live
  // (decision_stats merged per request) but was fetched once. Re-poll on a slow
  // timer and merge counts/avg_reward in; node positions stay stable because
  // the layout derives deterministically from the subsystem map.
  const haveCatalog = !!catalog;
  useEffect(() => {
    if (!haveCatalog) return;
    const id = setInterval(() => {
      fetchJSON<FnCatalog>(`${API}/catalog`)
        .then((d) => {
          if (d && d.functions && Object.keys(d.functions).length) {
            setCatalog((prev) => (prev ? { ...prev, functions: d.functions, edges: d.edges } : d));
          }
        })
        .catch(() => {});
    }, 30_000);
    return () => clearInterval(id);
  }, [haveCatalog]);

  const layout = useMemo(() => (catalog ? buildLayout(catalog) : null), [catalog]);
  const activeFn = telemetry.activeFn;
  // Fix 1 + multi-goal pursuit: the executive lane's function(s) this tick.
  // With multi-goal Option A the Executive advances EVERY queued goal per tick,
  // so the summary's `advanced` list can light several nodes ("1 conscious +
  // K executive lights"); falls back to the single active_fn for older frames.
  const execFns = useMemo(() => {
    const ex = telemetry.executive;
    const adv = (ex?.advanced ?? [])
      .map((a) => a?.fn)
      .filter((f): f is string => typeof f === "string" && !!f);
    const single = (ex?.active_fn as string | null | undefined) ?? null;
    return [...new Set(adv.length ? adv : single ? [single] : [])].slice(0, 3);
  }, [telemetry.executive]);
  const activeSub = activeFn && catalog ? catalog.functions[activeFn]?.subsystem ?? null : null;

  const subList = useMemo(
    () => (catalog ? Object.keys(catalog.subsystems).sort((a, b) => catalog.subsystems[b].length - catalog.subsystems[a].length).map((name) => ({ name, count: catalog.subsystems[name].length })) : []),
    [catalog],
  );
  const matches = useMemo(() => {
    if (!query.trim() || !catalog) return [];
    const q = query.toLowerCase();
    return Object.keys(catalog.functions).filter((n) => n.toLowerCase().includes(q)).slice(0, 8);
  }, [query, catalog]);

  // clicking a function (in the list or search) focuses it on the ball AND opens
  // its detail — the "show me exactly what this is doing" gesture for a dev.
  const pick = (name: string) => {
    setFocusSub(null);
    setFocusNode(name);
    setSelected(name);
  };
  const pickSub = (sub: string) => {
    setFocusNode(null);
    setFocusSub(sub);
  };
  // Cross-box provenance links (Fix 4 step 4): other panels (e.g. the
  // Consciousness panel's executive fn) navigate here with a function name.
  useNavTarget("sphere", (fn) => {
    if (catalog?.functions[fn]) pick(fn);
  });
  const { t, tip } = useLexicon();
  const toggleSub = (name: string) =>
    setSettings({ ...settings, hiddenSubs: { ...settings.hiddenSubs, [name]: !settings.hiddenSubs[name] } });

  return (
    <Card id="box-sphere" className="relative flex h-full flex-col overflow-hidden">
      <CardHeader className="flex-row items-center justify-between gap-2 space-y-0 pb-2">
        <CardTitle className="flex min-w-0 items-center gap-2 text-sm font-medium text-muted-foreground">
          <Cpu className="h-4 w-4" /> <span title={tip("sphere_title")}>{t("sphere_title")}</span>
          <PanelInfo
            title="Function-call graph"
            perspective="dev-only"
            what="Every cognitive function it can run, as a 3D map grouped by subsystem. The white comet is the deliberate (attention-winning) pick this cycle; the amber pulse is the executive lane quietly advancing a goal step in the background. Node size grows with real usage; the silver roads are learned transitions — thicker and brighter where cognition actually travels, with pulses flowing in the transition's direction. Click any node to read its code and stats."
            source="GET /api/catalog (function registry + live decision_stats) · active lights from the telemetry socket"
            good="Two lanes visibly alive: the comet moving every ~20s cycle, and node sizes growing where it actually spends its cognition."
            src={{ file: "brain/registry/function_catalog.py", start: 1, end: 60, label: "build_catalog" }}
          />
          <PanelSubtitle id="sphere_sub" />
          <StaleBadge url={`${API}/catalog`} pollMs={30_000} />
        </CardTitle>
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          {activeFn && (
            <span className="hidden items-center gap-1.5 sm:flex" title="Deliberate lane (attention-winner slot)">
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: colorFor(activeSub || "Other") }} />
              <span className="font-mono">{activeFn}</span>
            </span>
          )}
          {execFns.length > 0 && (
            <span className="hidden items-center gap-1.5 sm:flex" title="Executive lane (autopilot) — the amber lights; multi-goal pursuit can run several per tick">
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: "#f59e0b" }} />
              <span className="font-mono text-[10px]">
                {execFns[0]}
                {execFns.length > 1 && <span className="text-muted-foreground"> +{execFns.length - 1}</span>}
              </span>
            </span>
          )}
          <button
            onClick={() => setSettings({ ...settings, showList: !settings.showList })}
            className={`rounded p-1 hover:bg-muted hover:text-foreground ${settings.showList ? "text-foreground" : ""}`}
            title="Toggle function list"
            aria-label="Toggle function list"
          >
            <PanelLeft className="h-3.5 w-3.5" />
          </button>
          {catalog && <ControlsPanel settings={settings} setSettings={setSettings} subs={subList} />}
        </div>
      </CardHeader>

      <CardContent className="flex min-h-[340px] flex-1 p-0">
        {catalog && settings.showList && (
          <CognitionExplorer
            catalog={catalog}
            settings={settings}
            setSettings={setSettings}
            activeFn={activeFn}
            fnRecent={telemetry.fnRecent}
            query={query}
            setQuery={setQuery}
            onPick={pick}
            focusNode={focusNode}
          />
        )}

        <div className="relative min-h-0 min-w-0 flex-1">
          {/* compact search only when the list is hidden */}
          {catalog && !settings.showList && (
            <div className="absolute left-2 top-2 z-30 w-52">
              <div className="flex items-center gap-1.5 rounded-md border border-border bg-card/90 px-2 py-1 shadow-sm backdrop-blur">
                <Search className="h-3.5 w-3.5 text-muted-foreground" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && matches[0] && pick(matches[0])}
                  placeholder="Find a function…"
                  className="w-full bg-transparent text-[11px] outline-none placeholder:text-muted-foreground"
                />
              </div>
              {matches.length > 0 && (
                <div className="mt-1 overflow-hidden rounded-md border border-border bg-popover shadow-lg">
                  {matches.map((m) => (
                    <button key={m} onClick={() => pick(m)} className="flex w-full items-center gap-1.5 px-2 py-1 text-left text-[11px] hover:bg-muted">
                      <span className="h-1.5 w-1.5 flex-none rounded-full" style={{ background: colorFor(catalog.functions[m].subsystem) }} />
                      <span className="truncate font-mono">{m}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {(focusNode || focusSub) && (
            <button
              onClick={() => {
                setFocusNode(null);
                setFocusSub(null);
              }}
              className="absolute left-1/2 top-2 z-30 -translate-x-1/2 rounded bg-card/90 px-2 py-0.5 font-mono text-[10px] text-muted-foreground shadow backdrop-blur hover:text-foreground"
            >
              ✕ {focusNode || focusSub}
            </button>
          )}

          {!layout || !catalog ? (
            <div className="flex h-full items-center justify-center text-[12px] text-muted-foreground">{t("sphere_empty")} (waiting for the catalog)</div>
          ) : (
            <ErrorBoundary
              fallback={
                <div role="alert" className="flex h-full flex-col items-center justify-center gap-1 p-4 text-center text-[12px] text-muted-foreground">
                  <span className="font-medium text-foreground/80">3D view unavailable</span>
                  <span>WebGL may be disabled or unsupported on this device.</span>
                </div>
              }
            >
              <Canvas camera={{ position: [0, 0, CAM_Z], fov: 50 }} dpr={[1, 2]}>
                <color attach="background" args={["#0a0d14"]} />
                <Scene
                  layout={layout}
                  catalog={catalog}
                  settings={settings}
                  activeFn={activeFn}
                  execFns={execFns}
                  fnRecent={telemetry.fnRecent}
                  hovered={hovered}
                  setHovered={setHovered}
                  onSelect={setSelected}
                  focusNode={focusNode}
                  focusSub={focusSub}
                  onPickSub={pickSub}
                  resetTick={resetTick}
                  controls={controlsRef}
                />
              </Canvas>
            </ErrorBoundary>
          )}

          {/* maneuver controls — clean zoom / reset, like a map */}
          {catalog && (
            <div className="absolute right-2 top-2 z-30 flex flex-col overflow-hidden rounded-md border border-border bg-card/90 shadow-sm backdrop-blur">
              <button onClick={() => zoom(0.8)} className="p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground" title="Zoom in" aria-label="Zoom in">
                <Plus className="h-3.5 w-3.5" />
              </button>
              <button onClick={() => zoom(1.25)} className="border-t border-border p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground" title="Zoom out" aria-label="Zoom out">
                <Minus className="h-3.5 w-3.5" />
              </button>
              <button onClick={() => { setFocusNode(null); setFocusSub(null); setResetTick((k) => k + 1); }} className="border-t border-border p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground" title="Reset view" aria-label="Reset view">
                <Maximize2 className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setSettings({ ...settings, lines: !settings.lines })}
                className={`border-t border-border p-1.5 hover:bg-muted hover:text-foreground ${settings.lines ? "text-foreground" : "text-muted-foreground/50"}`}
                title={settings.lines ? "Hide roads (connections)" : "Show roads (connections)"}
                aria-label="Toggle connection lines"
              >
                <Spline className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          {/* legend — clickable to show/hide a subsystem */}
          {catalog && (
            <div className="scrollbar-thin absolute bottom-0 left-0 right-0 flex gap-x-3 overflow-x-auto border-t border-border/40 bg-background/70 px-2 py-1.5 backdrop-blur">
              {subList.map((s) => (
                <button
                  key={s.name}
                  onClick={() => toggleSub(s.name)}
                  className={`flex shrink-0 items-center gap-1 whitespace-nowrap text-[10px] transition-opacity hover:text-foreground ${settings.hiddenSubs[s.name] ? "opacity-30" : "text-muted-foreground"}`}
                  title={settings.hiddenSubs[s.name] ? `Show ${s.name}` : `Hide ${s.name}`}
                >
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: colorFor(s.name) }} />
                  {s.name}
                </button>
              ))}
            </div>
          )}

          {selected && catalog && (
            <FnDetailDrawer fn={selected} info={catalog.functions[selected]} recent={telemetry.fnRecent} onClose={() => setSelected(null)} />
          )}
        </div>
      </CardContent>
    </Card>
  );
}
