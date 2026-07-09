import * as THREE from "three";
import { colorFor } from "@/lib/cognitive";
import { FnCatalog } from "@/lib/telemetry";

const ANCHOR_R = 2.0;
export const NODE_R = 2.75;
/** The opaque core globe — sits under the node shell, occludes the far hemisphere. */
export const CORE_R = 2.45;
/** Default camera distance — the globe fills the frame; detail comes from zooming
 *  into a cluster (click its name) rather than from a busy overview. */
export const CAM_Z = 7.6;

const GOLDEN = Math.PI * (3 - Math.sqrt(5));

/**
 * Flight-path arc between two nodes: starts and ends AT the node positions and
 * lifts above the shell in between — short intra-cluster hops hug the surface,
 * long cross-sphere transitions arc high enough to clear the globe (the roads
 * used to ride a shell *below* the nodes, so they never visually touched what
 * they connect). Slerp for direction + a sine-bumped radial profile; adaptive
 * tessellation so long arcs stay smooth and short ones stay cheap.
 */
export function arcPoints(a: THREE.Vector3, b: THREE.Vector3): THREE.Vector3[] {
  const ra = a.length() || NODE_R;
  const rb = b.length() || NODE_R;
  const da = a.clone().divideScalar(ra);
  const db = b.clone().divideScalar(rb);
  const dot = THREE.MathUtils.clamp(da.dot(db), -1, 1);
  const omega = Math.acos(dot);
  const n = Math.max(10, Math.min(56, Math.round(omega * 34) + 8));
  const lift = 0.05 + 0.42 * Math.pow(omega / Math.PI, 0.9);
  const so = Math.sin(omega);
  const pts: THREE.Vector3[] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    let dir: THREE.Vector3;
    if (so < 1e-4) {
      dir = da.clone().lerp(db, t).normalize();
    } else {
      const s1 = Math.sin((1 - t) * omega) / so;
      const s2 = Math.sin(t * omega) / so;
      dir = da.clone().multiplyScalar(s1).add(db.clone().multiplyScalar(s2));
    }
    const r = THREE.MathUtils.lerp(ra, rb, t) + Math.sin(Math.PI * t) * lift;
    pts.push(dir.multiplyScalar(r));
  }
  return pts;
}

/**
 * Road styling normalized against the strongest visible edge, so the map reads
 * the same on a young run (tiny bonuses) and a mature one: the busiest routes
 * are always bright silver-blue trunks, one-offs stay faint hairlines.
 */
export function roadStyle(w: number, wMax: number) {
  const s = wMax > 0 ? Math.pow(THREE.MathUtils.clamp(w / wMax, 0, 1), 0.6) : 0;
  const g = Math.round(110 + s * 130);
  return {
    color: `rgb(${g},${Math.min(255, g + 7)},${Math.min(255, g + 22)})`,
    width: 0.5 + s * 2.4,
    opacity: 0.09 + s * 0.38,
    strength: s,
  };
}

// ── settings (fully customizable, persisted) ──────────────────────────────────
export type Settings = {
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
export const SKEY = "orrin.sphere.v2";
export function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(SKEY);
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch {
    /* ignore */
  }
  return DEFAULTS;
}

type LNode = { name: string; sub: string; color: string; pos: THREE.Vector3; count: number; reward: number };
export type Layout = {
  nodes: LNode[];
  byName: Map<string, LNode>;
  anchors: Record<string, THREE.Vector3>;
};

function rng(i: number) {
  const x = Math.sin(i * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
}

export function buildLayout(cat: FnCatalog): Layout {
  const subs = Object.keys(cat.subsystems).sort((a, b) => cat.subsystems[b].length - cat.subsystems[a].length);
  const anchors: Record<string, THREE.Vector3> = {};
  const N = subs.length;
  subs.forEach((s, i) => {
    const y = 1 - (i / Math.max(1, N - 1)) * 2;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const phi = i * GOLDEN;
    anchors[s] = new THREE.Vector3(Math.cos(phi) * r, y, Math.sin(phi) * r).multiplyScalar(ANCHOR_R);
  });
  const nodes: LNode[] = [];
  const byName = new Map<string, LNode>();
  subs.forEach((s, si) => {
    const aDir = anchors[s].clone().normalize();
    const t1 = new THREE.Vector3().crossVectors(aDir, new THREE.Vector3(0, 1, 0));
    if (t1.lengthSq() < 1e-4) t1.set(1, 0, 0);
    t1.normalize();
    const t2 = new THREE.Vector3().crossVectors(aDir, t1).normalize();
    // Phyllotaxis disc per cluster: deterministic, evenly packed, no overlaps —
    // the cluster's footprint grows with member count so dense subsystems get
    // room instead of piling up. Nodes sit EXACTLY on the shell (the old random
    // radial jitter is what made the roads look detached).
    const members = [...cat.subsystems[s]].sort();
    const clusterR = Math.min(0.9, 0.18 + Math.sqrt(members.length) * 0.09);
    const spin = rng(si + 1) * Math.PI * 2; // per-cluster rotation so discs don't align
    members.forEach((name, i) => {
      const ang = spin + i * GOLDEN;
      const rad = clusterR * Math.sqrt((i + 0.5) / members.length);
      const dir = aDir
        .clone()
        .add(t1.clone().multiplyScalar(Math.cos(ang) * rad))
        .add(t2.clone().multiplyScalar(Math.sin(ang) * rad))
        .normalize();
      const pos = dir.multiplyScalar(NODE_R);
      const info = cat.functions[name];
      const node: LNode = { name, sub: s, color: colorFor(s), pos, count: info?.count ?? 0, reward: info?.avg_reward ?? 0 };
      nodes.push(node);
      byName.set(name, node);
    });
  });
  return { nodes, byName, anchors };
}

// Compressed size range: usage still reads (busy nodes are clearly bigger) but
// the spread stays calm — distinguishing nodes comes from spacing, not bulk.
export function sizeOf(n: LNode, by: Settings["sizeBy"]) {
  if (by === "uniform") return 1;
  if (by === "reward") return 0.65 + Math.max(0, Math.min(1, n.reward)) * 1.2;
  return 0.65 + Math.min(1.5, Math.log2(1 + n.count) * 0.3); // usage
}
