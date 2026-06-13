import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { Html, Line, OrbitControls } from "@react-three/drei";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import * as THREE from "three";
import { Check, ChevronDown, Cpu, Maximize2, Minus, PanelLeft, Plus, Search, SlidersHorizontal, Spline } from "lucide-react";
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

const ANCHOR_R = 2.0;
const NODE_R = 2.75;
const ROAD_R = NODE_R - 0.34; // roads ride a shell just UNDER the nodes

// Great-circle arc on the inner road shell — clean gray/white "roads" the nodes
// sit on top of, hugging the surface (no flashy arch).
function arcPoints(a: THREE.Vector3, b: THREE.Vector3, n = 16): THREE.Vector3[] {
  const da = a.clone().normalize();
  const db = b.clone().normalize();
  const dot = THREE.MathUtils.clamp(da.dot(db), -1, 1);
  const omega = Math.acos(dot);
  if (omega < 1e-3) return [da.multiplyScalar(ROAD_R), db.multiplyScalar(ROAD_R)];
  const so = Math.sin(omega);
  const pts: THREE.Vector3[] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const s1 = Math.sin((1 - t) * omega) / so;
    const s2 = Math.sin(t * omega) / so;
    const p = da.clone().multiplyScalar(s1).add(db.clone().multiplyScalar(s2));
    pts.push(p.multiplyScalar(ROAD_R));
  }
  return pts;
}

// Gray→white by transition strength: faint paths are a dim gray, his strong loops
// lighten toward soft white. Kept muted so the roads sit quietly under the nodes.
function roadColor(w: number): string {
  const g = Math.round(90 + Math.min(120, w * 280)); // 90 (dim gray) → ~210 (soft white)
  return `rgb(${g},${g + 4},${g + 9})`;
}

// ── settings (fully customizable, persisted) ──────────────────────────────────
type Settings = {
  onlyUsed: boolean;
  lines: boolean;
  labels: "none" | "active" | "hover" | "used";
  sizeBy: "usage" | "reward" | "uniform";
  autoRotate: boolean;
  hiddenSubs: Record<string, boolean>;
  showList: boolean;
  sort: "usage" | "name" | "subsystem";
  effects: boolean;
};
const DEFAULTS: Settings = {
  onlyUsed: false,
  lines: true,
  labels: "hover",
  sizeBy: "usage",
  autoRotate: true,
  hiddenSubs: {},
  showList: true,
  sort: "usage",
  effects: true,
};
const SKEY = "orrin.sphere.v2";
function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(SKEY);
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch {
    /* ignore */
  }
  return DEFAULTS;
}

type LNode = { name: string; sub: string; color: string; pos: THREE.Vector3; count: number; reward: number };
type Layout = {
  nodes: LNode[];
  byName: Map<string, LNode>;
  anchors: Record<string, THREE.Vector3>;
};

function rng(i: number) {
  const x = Math.sin(i * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
}

function buildLayout(cat: FnCatalog): Layout {
  const subs = Object.keys(cat.subsystems).sort((a, b) => cat.subsystems[b].length - cat.subsystems[a].length);
  const anchors: Record<string, THREE.Vector3> = {};
  const N = subs.length;
  subs.forEach((s, i) => {
    const y = 1 - (i / Math.max(1, N - 1)) * 2;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const phi = i * Math.PI * (3 - Math.sqrt(5));
    anchors[s] = new THREE.Vector3(Math.cos(phi) * r, y, Math.sin(phi) * r).multiplyScalar(ANCHOR_R);
  });
  const nodes: LNode[] = [];
  const byName = new Map<string, LNode>();
  let gi = 0;
  for (const s of subs) {
    const aDir = anchors[s].clone().normalize();
    const t1 = new THREE.Vector3().crossVectors(aDir, new THREE.Vector3(0, 1, 0));
    if (t1.lengthSq() < 1e-4) t1.set(1, 0, 0);
    t1.normalize();
    const t2 = new THREE.Vector3().crossVectors(aDir, t1).normalize();
    for (const name of cat.subsystems[s]) {
      gi++;
      const ang = rng(gi) * Math.PI * 2;
      const rad = 0.12 + rng(gi + 7) * 0.55;
      const dir = aDir
        .clone()
        .add(t1.clone().multiplyScalar(Math.cos(ang) * rad))
        .add(t2.clone().multiplyScalar(Math.sin(ang) * rad))
        .normalize();
      const pos = dir.multiplyScalar(NODE_R + (rng(gi + 13) - 0.5) * 0.25);
      const info = cat.functions[name];
      const node: LNode = { name, sub: s, color: colorFor(s), pos, count: info?.count ?? 0, reward: info?.avg_reward ?? 0 };
      nodes.push(node);
      byName.set(name, node);
    }
  }
  return { nodes, byName, anchors };
}

function sizeOf(n: LNode, by: Settings["sizeBy"]) {
  if (by === "uniform") return 1;
  if (by === "reward") return 0.7 + Math.max(0, Math.min(1, n.reward)) * 1.8;
  return 0.7 + Math.min(2.2, Math.log2(1 + n.count) * 0.42); // usage
}

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
function ControlsPanel({ settings, setSettings, subs }: { settings: Settings; setSettings: (s: Settings) => void; subs: { name: string; count: number }[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);
  const set = (p: Partial<Settings>) => setSettings({ ...settings, ...p });
  const toggleSub = (name: string) => set({ hiddenSubs: { ...settings.hiddenSubs, [name]: !settings.hiddenSubs[name] } });

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 rounded-md border border-border bg-card/90 px-2 py-1 text-[11px] font-medium text-muted-foreground shadow-sm backdrop-blur hover:text-foreground"
      >
        <SlidersHorizontal className="h-3.5 w-3.5" /> Customize <ChevronDown className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-1.5 w-60 rounded-lg border border-border bg-popover p-2.5 shadow-xl">
          <Group label="Display">
            <Toggle on={settings.showList} set={(v) => set({ showList: v })} label="Function list (left)" />
            <Toggle on={settings.lines} set={(v) => set({ lines: v })} label="Roads (connections)" />
            <Toggle on={settings.onlyUsed} set={(v) => set({ onlyUsed: v })} label="Only functions he's used" />
            <Toggle on={settings.effects} set={(v) => set({ effects: v })} label="Glow effects" title="Soft bloom around the active node — costs a little GPU. The view is always 3D." />
            <Toggle on={settings.autoRotate} set={(v) => set({ autoRotate: v })} label="Auto-rotate" />
          </Group>
          <Group label="Size nodes by">
            <Seg value={settings.sizeBy} opts={[["usage", "Usage"], ["reward", "Reward"], ["uniform", "Uniform"]]} set={(v) => set({ sizeBy: v as Settings["sizeBy"] })} />
          </Group>
          <Group label="Labels">
            <Seg value={settings.labels} opts={[["none", "None"], ["hover", "Hover"], ["used", "Used"], ["active", "Active"]]} set={(v) => set({ labels: v as Settings["labels"] })} />
          </Group>
          <Group label="Subsystems">
            <div className="max-h-40 overflow-y-auto pr-1">
              {subs.map((s) => {
                const on = !settings.hiddenSubs[s.name];
                return (
                  <button key={s.name} onClick={() => toggleSub(s.name)} className="flex w-full items-center gap-2 rounded px-1 py-1 text-left hover:bg-muted">
                    <span className={`flex h-3.5 w-3.5 flex-none items-center justify-center rounded border ${on ? "border-transparent" : "border-border"}`} style={on ? { background: colorFor(s.name) } : undefined}>
                      {on && <Check className="h-2.5 w-2.5 text-white" />}
                    </span>
                    <span className="flex-1 text-[11px] text-foreground">{s.name}</span>
                    <span className="text-[10px] text-muted-foreground">{s.count}</span>
                  </button>
                );
              })}
            </div>
          </Group>
        </div>
      )}
    </div>
  );
}
const Group = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="mb-2 last:mb-0">
    <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</div>
    {children}
  </div>
);
const Toggle = ({ on, set, label, title }: { on: boolean; set: (v: boolean) => void; label: string; title?: string }) => (
  <button onClick={() => set(!on)} title={title} className="flex w-full items-center justify-between rounded px-1 py-1 text-left text-[11px] hover:bg-muted">
    <span className="text-foreground">{label}</span>
    <span className={`relative h-4 w-7 flex-none rounded-full transition-colors ${on ? "bg-signal-ok" : "bg-muted-foreground/30"}`}>
      <span className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${on ? "left-3.5" : "left-0.5"}`} />
    </span>
  </button>
);
const Seg = ({ value, opts, set }: { value: string; opts: [string, string][]; set: (v: string) => void }) => (
  <div className="flex overflow-hidden rounded-md border border-border">
    {opts.map(([v, l]) => (
      <button key={v} onClick={() => set(v)} className={`flex-1 px-1.5 py-1 text-[10px] transition-colors ${value === v ? "bg-foreground/10 font-medium text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
        {l}
      </button>
    ))}
  </div>
);

// Compact relative time for History rows ("what was he doing ten minutes ago" —
// Fix 10.1). ISO string or epoch in; "now" / "42s" / "7m" / "3h" / "2d" out.
function relTime(ts?: string | number): string {
  if (ts == null) return "";
  const d = typeof ts === "number" ? new Date(ts < 1e12 ? ts * 1000 : ts) : new Date(ts);
  const ms = Date.now() - d.getTime();
  if (isNaN(ms)) return "";
  if (ms < 15_000) return "now";
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m`;
  if (ms < 86_400_000) return `${Math.round(ms / 3_600_000)}h`;
  return `${Math.round(ms / 86_400_000)}d`;
}

// ── left-side function explorer (for someone who reads code) ──────────────────
function CognitionExplorer({
  catalog,
  settings,
  setSettings,
  activeFn,
  fnRecent,
  query,
  setQuery,
  onPick,
  focusNode,
}: {
  catalog: FnCatalog;
  settings: Settings;
  setSettings: (s: Settings) => void;
  activeFn: string | null;
  fnRecent: FnEvent[];
  query: string;
  setQuery: (q: string) => void;
  onPick: (n: string) => void;
  focusNode: string | null;
}) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [view, setView] = useState<"functions" | "history">("functions");
  type HistoryEvent = { fn: string; reward: number | null; agentic: boolean | null; ts?: string; lane?: string | null };
  const [history, setHistory] = useState<HistoryEvent[]>([]);
  const activeSub = activeFn ? catalog.functions[activeFn]?.subsystem ?? null : null;

  // Poll the activation history while the History tab is open.
  useEffect(() => {
    if (view !== "history") return;
    let stop = false;
    const load = () =>
      fetchJSON<{ events?: HistoryEvent[] }>(`${API}/history?n=120`)
        .then((d) => { if (!stop && Array.isArray(d.events)) setHistory(d.events); })
        .catch(() => {});
    load();
    const id = setInterval(load, 3000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [view, activeFn]);

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const subs = Object.keys(catalog.subsystems).sort((a, b) => catalog.subsystems[b].length - catalog.subsystems[a].length);
    return subs
      .filter((s) => !settings.hiddenSubs[s])
      .map((sub) => {
        let fns = catalog.subsystems[sub].map((n) => catalog.functions[n]).filter(Boolean);
        if (settings.onlyUsed) fns = fns.filter((f) => (f.count || 0) > 0);
        if (q) fns = fns.filter((f) => f.name.toLowerCase().includes(q));
        if (settings.sort === "usage") fns.sort((a, b) => (b.count || 0) - (a.count || 0));
        else if (settings.sort === "name") fns.sort((a, b) => a.name.localeCompare(b.name));
        return { sub, fns };
      })
      .filter((g) => g.fns.length);
  }, [catalog, settings.onlyUsed, settings.sort, settings.hiddenSubs, query]);

  const total = groups.reduce((n, g) => n + g.fns.length, 0);

  return (
    <div className="flex w-64 flex-none flex-col border-r border-border bg-card/40">
      {/* tabs: live function map vs. activation history */}
      <div className="flex border-b border-border">
        {(["functions", "history"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setView(t)}
            className={`flex-1 px-2 py-1.5 text-[11px] font-medium capitalize transition-colors ${
              view === t ? "border-b-2 border-foreground text-foreground" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {view === "functions" && (
        <>
      {/* search + sort */}
      <div className="space-y-1.5 border-b border-border p-2">
        <div className="flex items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1">
          <Search className="h-3.5 w-3.5 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter functions…"
            className="w-full bg-transparent text-[11px] outline-none placeholder:text-muted-foreground"
          />
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-muted-foreground">{total} shown</span>
          <Seg
            value={settings.sort}
            opts={[["usage", "Usage"], ["name", "Name"], ["subsystem", "Group"]]}
            set={(v) => setSettings({ ...settings, sort: v as Settings["sort"] })}
          />
        </div>
      </div>

      {/* now running */}
      {activeFn && (
        <div className="border-b border-border px-2 py-1.5">
          <div className="text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Now running</div>
          <button onClick={() => onPick(activeFn)} className="mt-0.5 flex w-full items-center gap-1.5 text-left">
            <span className="h-2 w-2 flex-none animate-pulse rounded-full" style={{ background: colorFor(activeSub || "Other") }} />
            <span className="truncate font-mono text-[11px] font-semibold text-foreground">{activeFn}</span>
          </button>
          {fnRecent.length > 1 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {[...fnRecent].slice(-5, -1).reverse().map((e, i) => (
                <button
                  key={i}
                  onClick={() => onPick(e.fn)}
                  className="truncate rounded bg-muted px-1 py-0.5 font-mono text-[9px] text-muted-foreground hover:text-foreground"
                  style={{ maxWidth: 110 }}
                  title={e.fn}
                >
                  {e.fn}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* grouped function list */}
      <div className="min-h-0 flex-1 overflow-y-auto py-1">
        {groups.map((g) => {
          const color = colorFor(g.sub);
          const isCollapsed = collapsed[g.sub];
          const hasActive = g.sub === activeSub;
          return (
            <div key={g.sub}>
              <button
                onClick={() => setCollapsed((c) => ({ ...c, [g.sub]: !c[g.sub] }))}
                className="flex w-full items-center gap-1.5 px-2 py-1 text-left hover:bg-muted/50"
              >
                <ChevronDown className={`h-3 w-3 flex-none text-muted-foreground transition-transform ${isCollapsed ? "-rotate-90" : ""}`} />
                <span className="h-2 w-2 flex-none rounded-full" style={{ background: color }} />
                <span className="flex-1 truncate text-[11px] font-semibold text-foreground">{g.sub}</span>
                {hasActive && <span className="h-1.5 w-1.5 flex-none animate-pulse rounded-full" style={{ background: color }} />}
                <span className="text-[9px] text-muted-foreground">{g.fns.length}</span>
              </button>
              {!isCollapsed &&
                g.fns.map((f) => {
                  const isActive = f.name === activeFn;
                  const isFocus = f.name === focusNode;
                  return (
                    <button
                      key={f.name}
                      onClick={() => onPick(f.name)}
                      className={`flex w-full items-center gap-1.5 py-0.5 pl-6 pr-2 text-left transition-colors ${
                        isActive ? "bg-foreground/10" : isFocus ? "bg-muted" : "hover:bg-muted/60"
                      }`}
                      title={f.summary || f.name}
                    >
                      <span
                        className={`h-1.5 w-1.5 flex-none rounded-full ${isActive ? "animate-pulse" : ""}`}
                        style={{ background: color, opacity: (f.count || 0) > 0 || isActive ? 1 : 0.35 }}
                      />
                      <span className={`flex-1 truncate font-mono text-[10px] ${isActive ? "font-semibold text-foreground" : (f.count || 0) > 0 ? "text-foreground/85" : "text-muted-foreground"}`}>
                        {f.name}
                      </span>
                      {(f.count || 0) > 0 && <span className="font-mono text-[9px] text-muted-foreground tabular-nums">{f.count}</span>}
                    </button>
                  );
                })}
            </div>
          );
        })}
        {total === 0 && <div className="px-3 py-4 text-center text-[11px] text-muted-foreground">No functions match.</div>}
      </div>
        </>
      )}

      {view === "history" && (
        <div className="min-h-0 flex-1 overflow-y-auto p-1">
          <div className="px-2 py-1 text-[9px] text-muted-foreground">most recent first · click to inspect</div>
          {history.length === 0 && <div className="px-3 py-4 text-center text-[11px] text-muted-foreground">No activation history yet.</div>}
          {[...history].reverse().map((e, i) => {
            const info = e.fn ? catalog.functions[e.fn] : undefined;
            const color = colorFor(info?.subsystem || "Other");
            const isLatest = i === 0;
            return (
              <button
                key={`${i}-${e.fn}`}
                onClick={() => e.fn && onPick(e.fn)}
                className={`flex w-full items-center gap-1.5 rounded px-2 py-1 text-left hover:bg-muted/60 ${isLatest ? "bg-foreground/10" : ""}`}
                title={info?.summary || e.fn || ""}
              >
                <span className={`h-1.5 w-1.5 flex-none rounded-full ${isLatest ? "animate-pulse" : ""}`} style={{ background: color }} />
                <span className="flex-1 truncate font-mono text-[10px] text-foreground/85">{e.fn}</span>
                {e.lane === "executive" && (
                  <span className="rounded px-1 text-[8px] font-semibold" style={{ background: "#f59e0b22", color: "#f59e0b" }} title="Executive lane (autopilot)">exec</span>
                )}
                {e.agentic && <span className="rounded bg-signal-ok/15 px-1 text-[8px] font-semibold text-signal-ok">act</span>}
                {e.reward != null && (
                  <span
                    className="font-mono text-[9px] tabular-nums"
                    style={{ color: e.reward >= 0.45 ? "hsl(var(--signal-ok))" : e.reward < 0.2 ? "hsl(var(--signal-error))" : "hsl(var(--muted-foreground))" }}
                  >
                    {Math.round(e.reward * 100)}
                  </span>
                )}
                {e.ts && (
                  <span className="w-9 flex-none text-right font-mono text-[9px] tabular-nums text-muted-foreground/60" title={new Date(e.ts).toLocaleString()}>
                    {relTime(e.ts)}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

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
