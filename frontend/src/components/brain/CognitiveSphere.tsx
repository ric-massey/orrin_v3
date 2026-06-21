import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { Html, Line, OrbitControls } from "@react-three/drei";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
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
import { FnCatalog, FnEvent, TelemetryState } from "@/lib/telemetry";
import { PanelSubtitle } from "./Lex";
import { type Settings, type Layout, SKEY, loadSettings, buildLayout, sizeOf, arcPoints, roadColor } from "./cognitiveSphere/layout";
import { ControlsPanel } from "./cognitiveSphere/ControlsPanel";
import { CognitionExplorer } from "./cognitiveSphere/CognitionExplorer";


// ── camera fly-to (for search focus + reset) ──────────────────────────────────
function CameraRig({ focus, resetTick, controls }: { focus: THREE.Vector3 | null; resetTick: number; controls: React.MutableRefObject<any> }) {
  const { camera } = useThree();
  const target = useRef(new THREE.Vector3());
  const want = useRef(new THREE.Vector3(0, 0, 7.5));
  const until = useRef(0); // animate only briefly, then fully release control to OrbitControls
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false; // don't hijack the camera on initial mount
      return;
    }
    if (focus) {
      target.current.copy(focus);
      want.current.copy(focus).multiplyScalar(1.9);
    } else {
      target.current.set(0, 0, 0);
      want.current.set(0, 0, 7.5);
    }
    until.current = performance.now() + 650;
  }, [focus, resetTick]);
  useFrame(() => {
    if (performance.now() > until.current) return; // idle → you have full control
    camera.position.lerp(want.current, 0.14);
    if (controls.current) controls.current.target.lerp(target.current, 0.14);
  });
  return null;
}

// ── traveling light (follows real chain edges when they exist) ────────────────
function TravelingLight({ layout, edgeSet, activeFn, fnRecent }: { layout: Layout; edgeSet: Set<string>; activeFn: string | null; fnRecent: FnEvent[] }) {
  const head = useRef<THREE.Mesh>(null);
  const halo = useRef<THREE.Mesh>(null);
  const start = useRef(performance.now());
  const path = useMemo<THREE.Vector3[]>(() => {
    if (!activeFn) return [];
    const cur = layout.byName.get(activeFn);
    if (!cur) return [];
    const prevName = [...fnRecent].reverse().find((e) => e.fn !== activeFn)?.fn;
    const prev = prevName ? layout.byName.get(prevName) : undefined;
    if (!prev || !prevName) return [cur.pos];
    // real learned edge → travel it straight; else route via subsystem anchors
    if (edgeSet.has(`${prevName}>${activeFn}`) || edgeSet.has(`${activeFn}>${prevName}`)) {
      return [prev.pos, cur.pos];
    }
    const aPrev = layout.anchors[prev.sub];
    const aCur = layout.anchors[cur.sub];
    return [prev.pos, aPrev, aCur, cur.pos].filter((p, i, arr) => i === 0 || !p.equals(arr[i - 1]));
  }, [activeFn, fnRecent, layout, edgeSet]);
  useEffect(() => void (start.current = performance.now()), [activeFn]);
  useFrame(() => {
    if (!head.current) return;
    const on = path.length > 0;
    head.current.visible = on;
    if (halo.current) halo.current.visible = on;
    if (!on) return;
    const t = Math.min(1, (performance.now() - start.current) / 850);
    let p: THREE.Vector3;
    if (path.length === 1) p = path[0];
    else {
      const segs = path.length - 1;
      const f = t * segs;
      const i = Math.min(segs - 1, Math.floor(f));
      p = path[i].clone().lerp(path[i + 1], f - i);
    }
    head.current.position.copy(p);
    if (halo.current) {
      halo.current.position.copy(p);
      halo.current.scale.setScalar(1 + Math.sin(performance.now() / 180) * 0.25);
    }
  });
  return (
    <group>
      <mesh ref={head}>
        <sphereGeometry args={[0.09, 16, 16]} />
        <meshBasicMaterial color="#ffffff" toneMapped={false} />
      </mesh>
      <mesh ref={halo}>
        <sphereGeometry args={[0.2, 16, 16]} />
        <meshBasicMaterial color="#ffffff" transparent opacity={0.25} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
      </mesh>
    </group>
  );
}

// ── executive lane's second light (Fix 1) ─────────────────────────────────────
// The procedural daemon advances ONE goal step per ~7s tick, then idles — so
// this light PULSES and FADES after each step instead of glowing continuously,
// and renders nothing when the tick mapped to no function (active_fn = null).
// Fixed amber tint so the two lanes are visually distinct from the white
// deliberate comet.
const EXEC_COLOR = "#f59e0b";
function ExecutiveLight({ layout, execFn }: { layout: Layout; execFn: string | null }) {
  const core = useRef<THREE.Mesh>(null);
  const ring = useRef<THREE.Mesh>(null);
  const seen = useRef(performance.now());
  useEffect(() => {
    seen.current = performance.now();
  }, [execFn]);
  const pos = execFn ? layout.byName.get(execFn)?.pos ?? null : null;
  useFrame(() => {
    const on = !!pos;
    if (core.current) core.current.visible = on;
    if (ring.current) ring.current.visible = on;
    if (!on || !pos) return;
    // Fade over ~6s after the step landed (the daemon ticks every ~7s).
    const fade = Math.max(0, 1 - (performance.now() - seen.current) / 6000);
    const pulse = 1 + Math.sin(performance.now() / 260) * 0.3;
    if (core.current) {
      core.current.position.copy(pos);
      (core.current.material as THREE.MeshBasicMaterial).opacity = 0.7 * fade;
      core.current.scale.setScalar(pulse);
    }
    if (ring.current) {
      ring.current.position.copy(pos);
      (ring.current.material as THREE.MeshBasicMaterial).opacity = 0.25 * fade;
      ring.current.scale.setScalar(pulse * 1.7);
    }
  });
  return (
    <group>
      <mesh ref={core}>
        <sphereGeometry args={[0.08, 16, 16]} />
        <meshBasicMaterial color={EXEC_COLOR} transparent opacity={0.7} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
      </mesh>
      <mesh ref={ring}>
        <sphereGeometry args={[0.08, 12, 12]} />
        <meshBasicMaterial color={EXEC_COLOR} wireframe transparent opacity={0.25} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
      </mesh>
    </group>
  );
}

function Pulse({ pos, color, r = 0.16 }: { pos: THREE.Vector3; color: string; r?: number }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(() => ref.current && ref.current.scale.setScalar(1 + Math.sin(performance.now() / 220) * 0.35));
  return (
    <mesh ref={ref} position={pos}>
      <sphereGeometry args={[r, 16, 16]} />
      <meshBasicMaterial color={color} transparent opacity={0.35} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
    </mesh>
  );
}

// ── scene ─────────────────────────────────────────────────────────────────────
function Scene({
  layout,
  catalog,
  settings,
  activeFn,
  execFns,
  fnRecent,
  hovered,
  setHovered,
  onSelect,
  focusNode,
  resetTick,
  controls,
}: {
  layout: Layout;
  catalog: FnCatalog;
  settings: Settings;
  activeFn: string | null;
  execFns: string[];
  fnRecent: FnEvent[];
  hovered: string | null;
  setHovered: (n: string | null) => void;
  onSelect: (n: string) => void;
  focusNode: string | null;
  resetTick: number;
  controls: React.MutableRefObject<any>;
}) {
  const nodeGeo = useMemo(() => new THREE.SphereGeometry(0.05, 18, 18), []);

  // visibility filter
  const visible = useMemo(() => {
    const set = new Set<string>();
    for (const n of layout.nodes) {
      if (settings.hiddenSubs[n.sub]) continue;
      if (settings.onlyUsed && n.count <= 0) continue;
      set.add(n.name);
    }
    return set;
  }, [layout, settings.hiddenSubs, settings.onlyUsed]);

  const edgeSet = useMemo(() => {
    const s = new Set<string>();
    for (const e of catalog.edges || []) s.add(`${e.from}>${e.to}`);
    return s;
  }, [catalog.edges]);

  // Glowing roads on the outer shell. Width scales with the learned transition
  // strength, so heavily-travelled paths (his loops) swell into thick bright roads
  // you can read at a glance; faint one-offs stay thin.
  const roads = useMemo(() => {
    if (!settings.lines) return [];
    const out: { key: string; points: THREE.Vector3[]; color: string; width: number; opacity: number }[] = [];
    for (const e of catalog.edges || []) {
      if (!visible.has(e.from) || !visible.has(e.to)) continue;
      const a = layout.byName.get(e.from);
      const b = layout.byName.get(e.to);
      if (!a || !b) continue;
      const w = e.weight || 0;
      out.push({
        key: `${e.from}>${e.to}`,
        points: arcPoints(a.pos, b.pos),
        color: roadColor(w),
        width: 0.8 + Math.min(3.6, w * 10),
        opacity: 0.12 + Math.min(0.2, w * 0.8),
      });
    }
    return out;
  }, [catalog.edges, visible, layout, settings.lines]);

  const focusPos = focusNode ? layout.byName.get(focusNode)?.pos ?? null : null;
  const activePos = activeFn ? layout.byName.get(activeFn)?.pos : undefined;
  const activeColor = activeFn ? colorFor(layout.byName.get(activeFn)?.sub || "Other") : "#fff";

  const showLabel = (name: string, isActive: boolean) => {
    if (settings.labels === "none") return false;
    // "active": a clean view that labels ONLY the live running node — no hover noise.
    if (settings.labels === "active") return isActive;
    // "used": every node that has fired at least once, plus whatever you hover.
    if (settings.labels === "used") return (layout.byName.get(name)?.count ?? 0) > 0 || name === hovered;
    // "hover" (default): interaction-driven labels, plus the running node for context.
    return isActive || name === hovered || name === focusNode;
  };

  return (
    <>
      <fog attach="fog" args={["#0a0d14", 7.5, 17]} />
      <ambientLight intensity={0.45} />
      <pointLight position={[6, 6, 8]} intensity={0.7} />
      <pointLight position={[-7, -4, -6]} intensity={0.4} color="#5b8cff" />
      <pointLight position={[0, 8, -4]} intensity={0.3} color="#ff7ad9" />
      <OrbitControls
        ref={controls}
        makeDefault
        enablePan={false}
        enableDamping
        dampingFactor={0.1}
        autoRotate={settings.autoRotate && !hovered && !focusNode}
        autoRotateSpeed={0.45}
        minDistance={1.6}
        maxDistance={13}
        zoomSpeed={0.3}
        zoomToCursor
      />
      <CameraRig focus={focusPos} resetTick={resetTick} controls={controls} />

      {roads.map((r) => (
        <Line key={r.key} points={r.points} color={r.color} lineWidth={r.width} transparent opacity={r.opacity} />
      ))}

      {layout.nodes.map((n) => {
        if (!visible.has(n.name)) return null;
        const isActive = n.name === activeFn;
        const isHover = n.name === hovered;
        const isFocus = n.name === focusNode;
        const s = sizeOf(n, settings.sizeBy) * (isActive ? 1.7 : isHover || isFocus ? 1.4 : 1);
        const dim = n.count <= 0 && !isActive && !isHover && !isFocus;
        return (
          <mesh
            key={n.name}
            geometry={nodeGeo}
            position={n.pos}
            scale={s}
            onPointerOver={(e: ThreeEvent<PointerEvent>) => {
              e.stopPropagation();
              setHovered(n.name);
              document.body.style.cursor = "pointer";
            }}
            onPointerOut={() => {
              setHovered(null);
              document.body.style.cursor = "auto";
            }}
            onClick={(e: ThreeEvent<MouseEvent>) => {
              e.stopPropagation();
              onSelect(n.name);
            }}
          >
            <meshStandardMaterial
              color={n.color}
              emissive={n.color}
              emissiveIntensity={(isActive ? 1.5 : isHover || isFocus ? 0.95 : dim ? 0.12 : 0.45) * (settings.effects ? 1 : 0.45)}
              metalness={0.3}
              roughness={0.35}
              transparent
              opacity={dim ? 0.5 : 1}
            />
          </mesh>
        );
      })}

      {activePos && <Pulse pos={activePos} color={activeColor} />}
      {focusPos && focusNode !== activeFn && <Pulse pos={focusPos} color="#ffffff" r={0.18} />}
      <TravelingLight layout={layout} edgeSet={edgeSet} activeFn={activeFn} fnRecent={fnRecent} />
      {/* executive (procedural) lane lights — Fix 1 / Gap 2; with multi-goal
          pursuit there can be up to K of them per tick (one per advanced goal) */}
      {execFns.map((fn) => (
        <ExecutiveLight key={fn} layout={layout} execFn={fn} />
      ))}

      {layout.nodes.map((n) => {
        if (!visible.has(n.name)) return null;
        const isActive = n.name === activeFn;
        if (!showLabel(n.name, isActive)) return null;
        return (
          <Html key={`l-${n.name}`} position={n.pos} center distanceFactor={9} zIndexRange={[20, 0]}>
            <div
              className="pointer-events-none -translate-y-5 whitespace-nowrap rounded px-1.5 py-0.5 font-mono text-[10px] shadow"
              style={isActive ? { background: activeColor, color: "#0b0f17", fontWeight: 700 } : { background: "hsl(var(--popover) / 0.9)", color: "hsl(var(--foreground))" }}
            >
              {n.name}
            </div>
          </Html>
        );
      })}

      {/* subtle bloom — only the active node / comet should softly glow */}
      {settings.effects && (
        <EffectComposer>
          <Bloom luminanceThreshold={0.55} luminanceSmoothing={0.9} intensity={0.35} mipmapBlur radius={0.5} />
        </EffectComposer>
      )}
    </>
  );
}

// ── customization panel ───────────────────────────────────────────────────────

// Compact relative time for History rows ("what was he doing ten minutes ago" —
// Fix 10.1). ISO string or epoch in; "now" / "42s" / "7m" / "3h" / "2d" out.

// ── top-level ─────────────────────────────────────────────────────────────────
export default function CognitiveSphere({ telemetry }: { telemetry: TelemetryState }) {
  const [catalog, setCatalog] = useState<FnCatalog | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [settings, setSettings] = useState<Settings>(loadSettings);
  const [query, setQuery] = useState("");
  const [focusNode, setFocusNode] = useState<string | null>(null);
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
    setFocusNode(name);
    setSelected(name);
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
            title="Cognitive Sphere"
            perspective="dev-only"
            what="Every cognitive function he can run, as a 3D map grouped by subsystem. The white comet is the deliberate (conscious) pick this cycle; the amber pulse is the executive lane quietly advancing a goal step in the background. Node size grows with real usage; the gray 'roads' are learned transitions between functions. Click any node to read its code and stats."
            source="GET /api/catalog (function registry + live decision_stats) · active lights from the telemetry socket"
            good="Two lanes visibly alive: the comet moving every ~20s cycle, and node sizes growing where he actually spends his cognition."
            src={{ file: "brain/registry/function_catalog.py", start: 1, end: 60, label: "build_catalog" }}
          />
          <PanelSubtitle id="sphere_sub" />
          <StaleBadge url={`${API}/catalog`} pollMs={30_000} />
        </CardTitle>
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          {activeFn && (
            <span className="hidden items-center gap-1.5 sm:flex" title="Deliberate lane (conscious slot)">
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

          {focusNode && (
            <button onClick={() => setFocusNode(null)} className="absolute left-1/2 top-2 z-30 -translate-x-1/2 rounded bg-card/90 px-2 py-0.5 font-mono text-[10px] text-muted-foreground shadow backdrop-blur hover:text-foreground">
              ✕ {focusNode}
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
              <Canvas camera={{ position: [0, 0, 7.5], fov: 50 }} dpr={[1, 2]}>
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
              <button onClick={() => { setFocusNode(null); setResetTick((k) => k + 1); }} className="border-t border-border p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground" title="Reset view" aria-label="Reset view">
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
            <div className="absolute bottom-2 left-2 right-2 flex flex-wrap gap-x-2 gap-y-1">
              {subList.map((s) => (
                <button
                  key={s.name}
                  onClick={() => toggleSub(s.name)}
                  className={`flex items-center gap-1 text-[10px] transition-opacity hover:text-foreground ${settings.hiddenSubs[s.name] ? "opacity-30" : "text-muted-foreground"}`}
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
