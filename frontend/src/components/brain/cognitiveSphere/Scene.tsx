import { useEffect, useMemo, useRef } from "react";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { Html, Line, OrbitControls } from "@react-three/drei";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import * as THREE from "three";
import { colorFor } from "@/lib/cognitive";
import { FnCatalog, FnEvent } from "@/lib/telemetry";
import { type Layout, type Settings, arcPoints, roadColor, sizeOf } from "./layout";

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
export function Scene({
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
  // strength, so heavily-travelled paths (its loops) swell into thick bright roads
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
