#!/usr/bin/env node

import { createHash, randomBytes } from "node:crypto";
import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { homedir } from "node:os";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const PACKAGE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const BUNDLED_RELEASE_ROOT = join(PACKAGE_ROOT, "release");
const BUNDLED_MANIFEST_PATH = join(BUNDLED_RELEASE_ROOT, "manifest.json");
const DEFAULT_INSTALL_DIR = join(homedir(), ".koda");

async function main() {
  const [command = "help", ...rest] = process.argv.slice(2);

  try {
    switch (command) {
      case "install":
        await installCommand(rest);
        break;
      case "update":
        await updateCommand(rest);
        break;
      case "up":
        await upCommand(rest);
        break;
      case "down":
        await downCommand(rest);
        break;
      case "doctor":
        await doctorCommand(rest);
        break;
      case "logs":
        await logsCommand(rest);
        break;
      case "version":
        await versionCommand(rest);
        break;
      case "uninstall":
        await uninstallCommand(rest);
        break;
      case "auth":
        await authCommand(rest);
        break;
      case "help":
      default:
        printHelp();
        break;
    }
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}

function printHelp() {
  console.log(`Koda CLI

Usage:
  koda install [--dir <path>] [--manifest <path>] [--headless]
  koda up [--dir <path>]
  koda down [--dir <path>]
  koda doctor [--dir <path>] [--json]
  koda auth issue-code [--dir <path>]
  koda update [--dir <path>] [--manifest <path>]
  koda logs [--dir <path>] [service...]
  koda version [--dir <path>]
  koda uninstall [--dir <path>] [--purge]
`);
}

function consumeOption(args, name, fallback = undefined) {
  const flagIndex = args.findIndex((item) => item === name);
  if (flagIndex === -1) {
    return fallback;
  }
  const value = args[flagIndex + 1];
  if (!value || value.startsWith("--")) {
    throw new Error(`Missing value for ${name}.`);
  }
  args.splice(flagIndex, 2);
  return value;
}

function consumeFlag(args, name) {
  const flagIndex = args.findIndex((item) => item === name);
  if (flagIndex === -1) {
    return false;
  }
  args.splice(flagIndex, 1);
  return true;
}

function resolveInstallDir(args) {
  const raw = consumeOption(args, "--dir", DEFAULT_INSTALL_DIR);
  return resolve(raw);
}

async function readJsonFile(path) {
  return JSON.parse(await readFile(path, "utf-8"));
}

async function loadManifest(manifestArg) {
  const manifestPath = manifestArg ? resolve(manifestArg) : BUNDLED_MANIFEST_PATH;
  const manifest = await readJsonFile(manifestPath);
  return {
    manifest,
    manifestPath,
    releaseRoot: dirname(manifestPath),
  };
}

function randomSecretUrlSafe(bytes = 32) {
  return randomBytes(bytes).toString("base64url");
}

function randomAlphaNumeric(length = 20) {
  const alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
  const bytes = randomBytes(length);
  let output = "";
  for (const byte of bytes) {
    output += alphabet[byte % alphabet.length];
  }
  return output;
}

async function copyReleaseBundle(releaseRoot, installDir) {
  await mkdir(installDir, { recursive: true });
  await cp(join(releaseRoot, "bundle"), join(installDir, "bundle"), {
    recursive: true,
    force: true,
  });
  await cp(join(releaseRoot, "manifest.json"), join(installDir, "manifest.json"), {
    force: true,
  });
  const checksumsPath = join(releaseRoot, "CHECKSUMS.txt");
  if (existsSync(checksumsPath)) {
    await cp(checksumsPath, join(installDir, "CHECKSUMS.txt"), { force: true });
  }
}

async function writeBootstrapEnvIfMissing(installDir) {
  const targetPath = join(installDir, ".env");
  if (existsSync(targetPath)) {
    return targetPath;
  }

  const templatePath = join(installDir, "bundle", ".env.bootstrap");
  let envText = await readFile(templatePath, "utf-8");
  envText = envText
    .replace("replace-with-a-random-token", randomSecretUrlSafe(32))
    .replace("replace-with-a-random-runtime-token", randomSecretUrlSafe(32))
    .replace("replace-with-a-random-web-session-secret", randomSecretUrlSafe(32))
    .replace("replace-with-a-random-postgres-password", randomSecretUrlSafe(24))
    .replace("replace-with-a-random-object-storage-access-key", randomAlphaNumeric(20))
    .replace("replace-with-a-random-object-storage-secret", randomSecretUrlSafe(24));
  await writeFile(targetPath, envText, "utf-8");
  return targetPath;
}

async function writeReleaseEnv(installDir, manifest) {
  const imageMap = {
    KODA_APP_IMAGE: manifest.images.app,
    KODA_WEB_IMAGE: manifest.images.web,
    KODA_MEMORY_IMAGE: manifest.images.memory,
    KODA_SECURITY_IMAGE: manifest.images.security,
    KODA_POSTGRES_IMAGE: manifest.images.postgres,
    KODA_SEAWEEDFS_IMAGE: manifest.images.seaweedfs,
    KODA_AWSCLI_IMAGE: manifest.images.awscli,
    KODA_RELEASE_VERSION: manifest.version,
  };
  const body = Object.entries(imageMap)
    .map(([key, value]) => `${key}=${value}`)
    .join("\n");
  const path = join(installDir, ".release.env");
  await writeFile(path, `${body}\n`, "utf-8");
  return path;
}

function parseEnvFile(text) {
  const payload = {};
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }
    const separator = trimmed.indexOf("=");
    if (separator === -1) {
      continue;
    }
    payload[trimmed.slice(0, separator)] = trimmed.slice(separator + 1);
  }
  return payload;
}

async function readInstallEnv(installDir) {
  const text = await readFile(join(installDir, ".env"), "utf-8");
  return parseEnvFile(text);
}

function composeArgs(installDir) {
  return [
    "compose",
    "--project-directory",
    installDir,
    "--env-file",
    join(installDir, ".env"),
    "--env-file",
    join(installDir, ".release.env"),
    "-f",
    join(installDir, "bundle", "docker-compose.release.yml"),
  ];
}

function runCommand(command, args, { cwd, stdio = "inherit", env } = {}) {
  const result = spawnSync(command, args, {
    cwd,
    stdio,
    env: env ? { ...process.env, ...env } : process.env,
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} failed with exit code ${result.status}.`);
  }
  return result;
}

function commandExists(command) {
  const result = spawnSync("sh", ["-lc", `command -v ${command}`], {
    stdio: "ignore",
  });
  return result.status === 0;
}

async function waitForHttp(url, label) {
  const timeoutAt = Date.now() + 120_000;
  while (Date.now() < timeoutAt) {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (response.ok) {
        return;
      }
    } catch {}
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 2_000));
  }
  throw new Error(`Timed out waiting for ${label} at ${url}.`);
}

function sha256(text) {
  return createHash("sha256").update(text).digest("hex");
}

async function verifyBundledChecksums(installDir, manifest) {
  const checksumsPath = join(installDir, manifest.bundle.checksums_file);
  if (!existsSync(checksumsPath)) {
    return;
  }
  const checksumText = await readFile(checksumsPath, "utf-8");
  for (const line of checksumText.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }
    const [expected, ...rest] = trimmed.split(/\s+/);
    const relativePath = rest.join(" ").trim();
    const absolutePath = join(installDir, relativePath);
    const actual = sha256(await readFile(absolutePath));
    if (actual !== expected) {
      throw new Error(`Checksum mismatch for ${relativePath}.`);
    }
  }
}

async function collectDoctorPayload(installDir) {
  const env = await readInstallEnv(installDir);
  const controlPlanePort = env.CONTROL_PLANE_PORT || "8090";
  const webPort = env.WEB_PORT || "3000";
  const payload = {
    install_dir: installDir,
    control_plane_url: `http://127.0.0.1:${controlPlanePort}`,
    health_url: `http://127.0.0.1:${controlPlanePort}/health`,
    dashboard_url: `http://127.0.0.1:${webPort}`,
    setup_url: `http://127.0.0.1:${webPort}/control-plane`,
  };

  const checks = {};
  const healthResponse = await fetch(payload.health_url, { cache: "no-store" });
  checks.control_plane = {
    ok: healthResponse.ok,
    status: healthResponse.status,
  };
  const dashboardResponse = await fetch(payload.dashboard_url, { cache: "no-store" });
  checks.dashboard = {
    ok: dashboardResponse.ok,
    status: dashboardResponse.status,
  };
  const onboardingResponse = await fetch(`${payload.control_plane_url}/api/control-plane/onboarding/status`, {
    cache: "no-store",
  });
  checks.onboarding = {
    ok: onboardingResponse.ok,
    status: onboardingResponse.status,
  };
  return {
    ok: Object.values(checks).every((item) => item.ok),
    ...payload,
    checks,
  };
}

async function doctorCommand(args) {
  const jsonOutput = consumeFlag(args, "--json");
  const installDir = resolveInstallDir(args);
  const payload = await collectDoctorPayload(installDir);
  if (jsonOutput) {
    console.log(JSON.stringify(payload, null, 2));
    return;
  }
  console.log(`Install dir: ${payload.install_dir}`);
  console.log(`Dashboard:   ${payload.dashboard_url}`);
  console.log(`Setup:       ${payload.setup_url}`);
  console.log(`Health:      ${payload.health_url}`);
  console.log("");
  for (const [name, result] of Object.entries(payload.checks)) {
    console.log(`${result.ok ? "OK" : "FAIL"} ${name} (${result.status})`);
  }
  if (!payload.ok) {
    throw new Error("Doctor checks failed.");
  }
}

async function issueBootstrapCode(installDir) {
  const env = await readInstallEnv(installDir);
  const controlPlanePort = env.CONTROL_PLANE_PORT || "8090";
  const webPort = env.WEB_PORT || "3000";
  const recoveryToken = String(env.CONTROL_PLANE_API_TOKEN || "").trim();
  if (!recoveryToken) {
    throw new Error("CONTROL_PLANE_API_TOKEN is required to issue a setup code.");
  }
  const response = await fetch(`http://127.0.0.1:${controlPlanePort}/api/control-plane/auth/bootstrap/codes`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${recoveryToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ label: "npm_cli" }),
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.code) {
    throw new Error(String(payload.error || "Could not issue a setup code."));
  }
  return {
    url: `http://127.0.0.1:${webPort}/control-plane`,
    code: payload.code,
    expires_at: payload.expires_at || null,
  };
}

function maybeOpenBrowser(url) {
  if (process.env.CI === "true") {
    return false;
  }
  const commands = process.platform === "darwin"
    ? [["open", [url]]]
    : process.platform === "win32"
      ? [["cmd", ["/c", "start", url]]]
      : [["xdg-open", [url]]];
  for (const [command, args] of commands) {
    if (!commandExists(command)) {
      continue;
    }
    const result = spawnSync(command, args, { stdio: "ignore", detached: true });
    if (!result.error) {
      return true;
    }
  }
  return false;
}

async function installCommand(args) {
  const headless = consumeFlag(args, "--headless");
  const manifestArg = consumeOption(args, "--manifest", undefined);
  const installDir = resolveInstallDir(args);
  const { manifest, releaseRoot } = await loadManifest(manifestArg);

  await copyReleaseBundle(releaseRoot, installDir);
  await writeBootstrapEnvIfMissing(installDir);
  await writeReleaseEnv(installDir, manifest);
  await verifyBundledChecksums(installDir, manifest);

  runCommand("docker", [...composeArgs(installDir), "up", "-d"], { cwd: installDir });

  const env = await readInstallEnv(installDir);
  await waitForHttp(`http://127.0.0.1:${env.CONTROL_PLANE_PORT || "8090"}/health`, "the control plane");
  await waitForHttp(`http://127.0.0.1:${env.WEB_PORT || "3000"}`, "the web dashboard");

  await doctorCommand(["--dir", installDir]);
  const bootstrap = await issueBootstrapCode(installDir);

  console.log("");
  console.log(`Koda ${manifest.version} installed.`);
  console.log(`Dashboard: ${bootstrap.url}`);
  console.log(`Setup code: ${bootstrap.code}`);
  if (bootstrap.expires_at) {
    console.log(`Expires at: ${bootstrap.expires_at}`);
  }

  if (!headless) {
    maybeOpenBrowser(bootstrap.url);
  }
}

async function upCommand(args) {
  const installDir = resolveInstallDir(args);
  runCommand("docker", [...composeArgs(installDir), "up", "-d"], { cwd: installDir });
}

async function downCommand(args) {
  const installDir = resolveInstallDir(args);
  runCommand("docker", [...composeArgs(installDir), "down"], { cwd: installDir });
}

async function logsCommand(args) {
  const installDir = resolveInstallDir(args);
  runCommand("docker", [...composeArgs(installDir), "logs", "-f", ...args], { cwd: installDir });
}

async function versionCommand(args) {
  const installDir = resolveInstallDir(args);
  const packageJson = await readJsonFile(join(PACKAGE_ROOT, "package.json"));
  console.log(`koda cli ${packageJson.version}`);
  if (existsSync(join(installDir, "manifest.json"))) {
    const manifest = await readJsonFile(join(installDir, "manifest.json"));
    console.log(`installed release ${manifest.version}`);
  }
}

async function authCommand(args) {
  const subcommand = args.shift();
  if (subcommand !== "issue-code") {
    throw new Error("Supported auth command: koda auth issue-code");
  }
  const installDir = resolveInstallDir(args);
  const payload = await issueBootstrapCode(installDir);
  console.log(`Dashboard: ${payload.url}`);
  console.log(`Setup code: ${payload.code}`);
  if (payload.expires_at) {
    console.log(`Expires at: ${payload.expires_at}`);
  }
}

async function updateCommand(args) {
  const manifestArg = consumeOption(args, "--manifest", undefined);
  const installDir = resolveInstallDir(args);
  const { manifest, releaseRoot } = await loadManifest(manifestArg);
  const backupDir = join(installDir, ".rollback");

  await rm(backupDir, { recursive: true, force: true });
  if (existsSync(installDir)) {
    await cp(installDir, backupDir, { recursive: true, force: true });
  }

  try {
    await copyReleaseBundle(releaseRoot, installDir);
    await writeReleaseEnv(installDir, manifest);
    await verifyBundledChecksums(installDir, manifest);
    runCommand("docker", [...composeArgs(installDir), "up", "-d"], { cwd: installDir });
    await doctorCommand(["--dir", installDir]);
    await rm(backupDir, { recursive: true, force: true });
  } catch (error) {
    if (existsSync(backupDir)) {
      await rm(installDir, { recursive: true, force: true });
      await cp(backupDir, installDir, { recursive: true, force: true });
      runCommand("docker", [...composeArgs(installDir), "up", "-d"], { cwd: installDir });
      await rm(backupDir, { recursive: true, force: true });
    }
    throw error;
  }
}

async function uninstallCommand(args) {
  const purge = consumeFlag(args, "--purge");
  const installDir = resolveInstallDir(args);
  if (existsSync(join(installDir, "bundle", "docker-compose.release.yml"))) {
    runCommand("docker", [...composeArgs(installDir), "down", "-v"], { cwd: installDir });
  }
  if (purge) {
    await rm(installDir, { recursive: true, force: true });
  }
}

await main();
