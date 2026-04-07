// Plain JS file — NOT processed by Turbopack/bundler.
// Reads the control plane API token from a file at runtime.
import { readFileSync } from "node:fs";

let cached = null;

function getServerToken() {
  if (cached !== null) return cached;
  try {
    cached = readFileSync("/tmp/.cp-token", "utf-8").trim();
  } catch {
    cached = "";
  }
  return cached;
}

export { getServerToken };
