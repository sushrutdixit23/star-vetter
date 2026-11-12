import fs from "fs";
import path from "path";
import type { PhysicsData } from "./physicsTypes";

// Reads the figure data export_physics.py writes into public/data/. Runs at build time, like lib/data.ts.
export function getPhysicsFigures(): PhysicsData | null {
  const p = path.join(process.cwd(), "public", "data", "physics.json");
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, "utf-8")) as PhysicsData;
}
