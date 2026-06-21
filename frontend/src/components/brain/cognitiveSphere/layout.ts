import * as THREE from "three";
import { colorFor } from "@/lib/cognitive";
import { FnCatalog } from "@/lib/telemetry";

const ANCHOR_R = 2.0;
const NODE_R = 2.75;
const ROAD_R = NODE_R - 0.34; // roads ride a shell just UNDER the nodes

// Great-circle arc on the inner road shell — clean gray/white "roads" the nodes
// sit on top of, hugging the surface (no flashy arch).
export function arcPoints(a: THREE.Vector3, b: THREE.Vector3, n = 16): THREE.Vector3[] {
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
export function roadColor(w: number): string {
  const g = Math.round(90 + Math.min(120, w * 280)); // 90 (dim gray) → ~210 (soft white)
  return `rgb(${g},${g + 4},${g + 9})`;
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

export function sizeOf(n: LNode, by: Settings["sizeBy"]) {
  if (by === "uniform") return 1;
  if (by === "reward") return 0.7 + Math.max(0, Math.min(1, n.reward)) * 1.8;
  return 0.7 + Math.min(2.2, Math.log2(1 + n.count) * 0.42); // usage
}
