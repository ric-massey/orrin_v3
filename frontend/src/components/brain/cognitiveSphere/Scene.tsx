import { useEffect, useMemo, useRef } from "react";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { Html, Line, OrbitControls } from "@react-three/drei";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import * as THREE from "three";
import { colorFor } from "@/lib/cognitive";
import { FnCatalog, FnEvent } from "@/lib/telemetry";
import { CAM_Z, CORE_R, NODE_R, type Layout, type Settings, arcPoints, roadStyle, sizeOf } from "./layout";

function CameraRig({ focus, resetTick, controls }: { focus: THREE.Vector3 | null; resetTick: number; controls: React.MutableRefObject<any> }) {
  const { camera } = useThree();
  const target = useRef(new THREE.Vector3());
  const want = useRef(new THREE.Vector3(0, 0, CAM_Z));
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
      want.current.set(0, 0, CAM_Z);
    }
    until.current = performance.now() + 950;
  }, [focus, resetTick]);
  useFrame(() => {
    if (performance.now() > until.current) return; // idle → you have full control
    camera.position.lerp(want.current, 0.14);
    if (controls.current) controls.current.target.lerp(target.current, 0.14);
  });
  return null;
}

// ── the core globe ────────────────────────────────────────────────────────────
// An opaque, near-black glass body under the node shell: gives the map an actual
// planet to sit on, occludes the far hemisphere (so the view reads as a surface,
// not a tangle of both sides at once — this also stops phantom hovers on nodes
// you can't see), and carries a soft fresnel rim + a faint graticule so scale
// and rotation are always legible.
const GLOBE_VERT = /* glsl */ `
  varying vec3 vN;
  varying vec3 vV;
  varying vec3 vP;
  void main() {
    vec4 wp = modelMatrix * vec4(position, 1.0);
    vN = normalize(mat3(modelMatrix) * normal);
    vV = normalize(cameraPosition - wp.xyz);
    vP = normalize(position);
    gl_Position = projectionMatrix * viewMatrix * wp;
  }
`;
const GLOBE_FRAG = /* glsl */ `
  uniform vec3 uBase;
  uniform vec3 uRim;
  uniform vec3 uGridColor;
  uniform float uGrid;
  varying vec3 vN;
  varying vec3 vV;
  varying vec3 vP;
  float gridLine(float x, float period) {
    float h = abs(fract(x / period + 0.5) - 0.5) * period; // distance to nearest line
    float aa = min(fwidth(x), 0.02) * 1.3;                 // cap: atan seam makes fwidth explode
    return 1.0 - smoothstep(0.0, aa + 0.005, h);
  }
  void main() {
    float ndv = clamp(dot(normalize(vN), normalize(vV)), 0.0, 1.0);
    float fres = pow(1.0 - ndv, 2.0);
    float lat = asin(clamp(vP.y, -1.0, 1.0));
    float lon = atan(vP.z, vP.x);
    float g = max(gridLine(lat, ${(Math.PI / 6).toFixed(6)}), gridLine(lon, ${(Math.PI / 6).toFixed(6)}));
    float gridVis = (1.0 - fres) * uGrid;
    vec3 col = uBase + uRim * fres + uGridColor * g * gridVis;
    gl_FragColor = vec4(col, 1.0);
  }
`;

function useGlobeMaterial() {
  return useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: GLOBE_VERT,
        fragmentShader: GLOBE_FRAG,
        uniforms: {
          uBase: { value: new THREE.Color("#101828") },
          uRim: { value: new THREE.Color("#4571b5") },
          uGridColor: { value: new THREE.Color("#31517e") },
          uGrid: { value: 0.5 },
        },
      }),
    [],
  );
}

// ── directional flow on the busiest roads ─────────────────────────────────────
// Small additive pulses that travel from→to along the strongest learned
// transitions: the roads stop being static string and read as *directed traffic*.
type Road = { key: string; points: THREE.Vector3[]; color: string; width: number; opacity: number; strength: number };

const FLOW_MAX = 10;
function FlowDots({ roads }: { roads: Road[] }) {
  const top = useMemo(
    () => roads.filter((r) => r.strength > 0.22).sort((a, b) => b.strength - a.strength).slice(0, FLOW_MAX),
    [roads],
  );
  const refs = useRef<(THREE.Mesh | null)[]>([]);
  useFrame(() => {
    const now = performance.now();
    top.forEach((r, i) => {
      const m = refs.current[i];
      if (!m) return;
      const period = 3200 - r.strength * 1400; // busier roads flow faster
      const t = ((now + i * 517) % period) / period;
      const f = t * (r.points.length - 1);
      const k = Math.min(r.points.length - 2, Math.floor(f));
      m.position.copy(r.points[k]).lerp(r.points[k + 1], f - k);
      const mat = m.material as THREE.MeshBasicMaterial;
      mat.opacity = (0.18 + r.strength * 0.4) * Math.sin(Math.PI * t); // ease in/out at the ends
      m.scale.setScalar(0.7 + r.strength * 0.6);
    });
  });
  return (
    <group>
      {top.map((r, i) => (
        <mesh key={r.key} ref={(el) => (refs.current[i] = el)}>
          <sphereGeometry args={[0.028, 10, 10]} />
          <meshBasicMaterial color="#cfe0ff" transparent opacity={0} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
        </mesh>
      ))}
    </group>
  );
}

// ── traveling light (the deliberate lane's comet) ─────────────────────────────
// Follows the same flight-path arc the roads use (it used to cut straight
// chords, detached from the road system), with a fading ghost trail.
const TRAIL = 9;
function TravelingLight({ layout, activeFn, fnRecent }: { layout: Layout; activeFn: string | null; fnRecent: FnEvent[] }) {
  const head = useRef<THREE.Mesh>(null);
  const halo = useRef<THREE.Mesh>(null);
  const trail = useRef<(THREE.Mesh | null)[]>([]);
  const start = useRef(performance.now());
  const path = useMemo<THREE.Vector3[]>(() => {
    if (!activeFn) return [];
    const cur = layout.byName.get(activeFn);
    if (!cur) return [];
    const prevName = [...fnRecent].reverse().find((e) => e.fn !== activeFn)?.fn;
    const prev = prevName ? layout.byName.get(prevName) : undefined;
    if (!prev) return [cur.pos];
    return arcPoints(prev.pos, cur.pos);
  }, [activeFn, fnRecent, layout]);
  useEffect(() => void (start.current = performance.now()), [activeFn]);

  const sample = (t: number): THREE.Vector3 => {
    if (path.length === 1) return path[0];
    const f = THREE.MathUtils.clamp(t, 0, 1) * (path.length - 1);
    const i = Math.min(path.length - 2, Math.floor(f));
    return path[i].clone().lerp(path[i + 1], f - i);
  };

  useFrame(() => {
    if (!head.current) return;
    const on = path.length > 0;
    head.current.visible = on;
    if (halo.current) halo.current.visible = on;
    trail.current.forEach((m) => m && (m.visible = on && path.length > 1));
    if (!on) return;
    const t = Math.min(1, (performance.now() - start.current) / 1100);
    const p = sample(t);
    head.current.position.copy(p);
    if (halo.current) {
      halo.current.position.copy(p);
      halo.current.scale.setScalar(1 + Math.sin(performance.now() / 180) * 0.25);
    }
    trail.current.forEach((m, i) => {
      if (!m) return;
      m.position.copy(sample(t - (i + 1) * 0.045));
      const mat = m.material as THREE.MeshBasicMaterial;
      mat.opacity = 0.4 * (1 - (i + 1) / (TRAIL + 1)) * (t >= 1 ? Math.max(0, 1.6 - t) : 1);
    });
  });
  return (
    <group>
      <mesh ref={head}>
        <sphereGeometry args={[0.07, 16, 16]} />
        <meshBasicMaterial color="#ffffff" toneMapped={false} />
      </mesh>
      <mesh ref={halo}>
        <sphereGeometry args={[0.15, 16, 16]} />
        <meshBasicMaterial color="#ffffff" transparent opacity={0.25} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
      </mesh>
      {Array.from({ length: TRAIL }, (_, i) => (
        <mesh key={i} ref={(el) => (trail.current[i] = el)}>
          <sphereGeometry args={[0.042 - i * 0.003, 10, 10]} />
          <meshBasicMaterial color="#dbe7ff" transparent opacity={0} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
        </mesh>
      ))}
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
        <sphereGeometry args={[0.065, 16, 16]} />
        <meshBasicMaterial color={EXEC_COLOR} transparent opacity={0.7} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
      </mesh>
      <mesh ref={ring}>
        <sphereGeometry args={[0.065, 12, 12]} />
        <meshBasicMaterial color={EXEC_COLOR} wireframe transparent opacity={0.25} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
      </mesh>
    </group>
  );
}

// ── subsystem names on the map ────────────────────────────────────────────────
// The legend tells you the colors, but a map you can't read without
// cross-referencing isn't a map. Visibility is a plain hemisphere test against
// the camera (the globe hides the far side anyway), driven per-frame via style
// opacity so React never re-renders during rotation. Clicking a name flies the
// camera into that cluster — the intended way to inspect a module up close.
function AnchorLabels({ layout, hiddenSubs, focusSub, onPickSub }: { layout: Layout; hiddenSubs: Record<string, boolean>; focusSub: string | null; onPickSub: (s: string) => void }) {
  const divs = useRef<Record<string, HTMLDivElement | null>>({});
  const { camera } = useThree();
  const entries = useMemo(
    () =>
      Object.entries(layout.anchors)
        .filter(([sub]) => !hiddenSubs[sub])
        .map(([sub, a]) => ({ sub, dir: a.clone().normalize(), pos: a.clone().normalize().multiplyScalar(NODE_R + 0.5) })),
    [layout.anchors, hiddenSubs],
  );
  const camDir = useRef(new THREE.Vector3());
  useFrame(() => {
    camDir.current.copy(camera.position).normalize();
    for (const e of entries) {
      const el = divs.current[e.sub];
      if (!el) continue;
      const facing = e.dir.dot(camDir.current); // 1 = dead center, 0 = limb, <0 = far side
      const vis = THREE.MathUtils.clamp((facing - 0.05) / 0.35, 0, e.sub === focusSub ? 1 : 0.9);
      el.style.opacity = String(vis);
      el.style.pointerEvents = vis > 0.25 ? "auto" : "none"; // don't catch clicks while invisible
    }
  });
  return (
    <>
      {entries.map((e) => (
        <Html key={`a-${e.sub}`} position={e.pos} center distanceFactor={11} zIndexRange={[15, 0]}>
          <div
            ref={(el) => (divs.current[e.sub] = el)}
            onClick={(ev) => {
              ev.stopPropagation();
              onPickSub(e.sub);
            }}
            className="cursor-pointer select-none whitespace-nowrap text-[9px] font-semibold uppercase tracking-[0.18em] transition-transform hover:scale-110"
            style={{ color: colorFor(e.sub), opacity: 0, textShadow: "0 0 10px rgba(0,0,0,0.95), 0 0 3px rgba(0,0,0,0.9)" }}
            title={`Fly to ${e.sub}`}
          >
            {e.sub}
          </div>
        </Html>
      ))}
    </>
  );
}

function Pulse({ pos, color, r = 0.12 }: { pos: THREE.Vector3; color: string; r?: number }) {
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
  focusSub,
  onPickSub,
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
  focusSub: string | null;
  onPickSub: (s: string) => void;
  resetTick: number;
  controls: React.MutableRefObject<any>;
}) {
  const nodeGeo = useMemo(() => new THREE.SphereGeometry(0.036, 16, 16), []);
  const globeMat = useGlobeMaterial();
  const globeRef = useRef<THREE.Mesh>(null);

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

  // Roads: node-to-node flight paths, styled against the strongest visible edge
  // so trunk routes read bright and one-offs stay hairlines (see layout.ts).
  const roads = useMemo<Road[]>(() => {
    if (!settings.lines) return [];
    const drawable = (catalog.edges || []).filter((e) => {
      if (!visible.has(e.from) || !visible.has(e.to)) return false;
      return layout.byName.has(e.from) && layout.byName.has(e.to);
    });
    const wMax = drawable.reduce((m, e) => Math.max(m, e.weight || 0), 0);
    return drawable.map((e) => {
      const a = layout.byName.get(e.from)!;
      const b = layout.byName.get(e.to)!;
      const st = roadStyle(e.weight || 0, wMax);
      return { key: `${e.from}>${e.to}`, points: arcPoints(a.pos, b.pos), ...st };
    });
  }, [catalog.edges, visible, layout, settings.lines]);

  // Camera focus: a picked node wins; else a picked cluster (fly to its anchor
  // on the node shell — the "zoom into this module" gesture).
  const focusPos = useMemo(() => {
    if (focusNode) return layout.byName.get(focusNode)?.pos ?? null;
    if (focusSub && layout.anchors[focusSub] && !settings.hiddenSubs[focusSub]) {
      return layout.anchors[focusSub].clone().normalize().multiplyScalar(NODE_R);
    }
    return null;
  }, [focusNode, focusSub, layout, settings.hiddenSubs]);
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
      <fog attach="fog" args={["#0a0d14", 8, 19]} />
      <ambientLight intensity={0.5} />
      <hemisphereLight args={["#3a4a6b", "#0a0d14", 0.35]} />
      <pointLight position={[6, 7, 8]} intensity={0.9} />
      <pointLight position={[-7, -4, -6]} intensity={0.45} color="#5b8cff" />
      <pointLight position={[0, 8, -4]} intensity={0.25} color="#ff7ad9" />
      <OrbitControls
        ref={controls}
        makeDefault
        enablePan={false}
        enableDamping
        dampingFactor={0.08}
        autoRotate={settings.autoRotate && !hovered && !focusNode && !focusSub}
        autoRotateSpeed={0.25}
        minDistance={3.3}
        maxDistance={12}
        zoomSpeed={0.3}
        zoomToCursor
      />
      <CameraRig focus={focusPos} resetTick={resetTick} controls={controls} />

      {/* the core globe (also the pointer/label occluder for the far side) */}
      <mesh ref={globeRef} material={globeMat}>
        <sphereGeometry args={[CORE_R, 64, 64]} />
      </mesh>

      {roads.map((r) => (
        <Line key={r.key} points={r.points} color={r.color} lineWidth={r.width} transparent opacity={r.opacity} />
      ))}
      {settings.effects && roads.length > 0 && <FlowDots roads={roads} />}

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
              emissiveIntensity={(isActive ? 1.5 : isHover || isFocus ? 0.95 : dim ? 0.18 : 0.5) * (settings.effects ? 1 : 0.45)}
              metalness={0.3}
              roughness={0.35}
              transparent
              opacity={dim ? 0.55 : 1}
            />
          </mesh>
        );
      })}

      {activePos && <Pulse pos={activePos} color={activeColor} />}
      {focusPos && focusNode !== activeFn && <Pulse pos={focusPos} color="#ffffff" r={0.14} />}
      <TravelingLight layout={layout} activeFn={activeFn} fnRecent={fnRecent} />
      {/* executive (procedural) lane lights — Fix 1 / Gap 2; with multi-goal
          pursuit there can be up to K of them per tick (one per advanced goal) */}
      {execFns.map((fn) => (
        <ExecutiveLight key={fn} layout={layout} execFn={fn} />
      ))}

      {settings.labels !== "none" && (
        <AnchorLabels layout={layout} hiddenSubs={settings.hiddenSubs} focusSub={focusSub} onPickSub={onPickSub} />
      )}

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
          <Bloom luminanceThreshold={0.5} luminanceSmoothing={0.9} intensity={0.55} mipmapBlur radius={0.6} />
        </EffectComposer>
      )}
    </>
  );
}
