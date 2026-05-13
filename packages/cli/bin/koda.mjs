#!/usr/bin/env node

import { createHash, randomBytes } from "node:crypto";
import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { homedir, tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const PACKAGE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const BUNDLED_RELEASE_ROOT = join(PACKAGE_ROOT, "release");
const BUNDLED_MANIFEST_PATH = join(BUNDLED_RELEASE_ROOT, "manifest.json");
const DEFAULT_INSTALL_DIR = join(homedir(), ".koda");
const LOOPBACK_HOST = "localhost";

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
  koda install [--dir <path>] [--manifest <path>] [--headless] [--reset-volumes]
  koda up [--dir <path>]
  koda down [--dir <path>]
  koda doctor [--dir <path>] [--json]
  koda auth issue-code [--dir <path>]
  koda update [--dir <path>] [--manifest <path>]
  koda logs [--dir <path>] [service...]
  koda version [--dir <path>]
  koda uninstall [--dir <path>] [--purge]

Options:
  --reset-volumes  Destroy any pre-existing Docker volumes managed by the
                   target install before bringing the stack up. Use this when
                   reinstalling and the previous Postgres password no longer
                   matches the volume on disk.
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
  let output = "";
  const maxUnbiasedByte = 256 - (256 % alphabet.length);

  while (output.length < length) {
    const bytes = randomBytes(length - output.length);
    for (const byte of bytes) {
      if (byte >= maxUnbiasedByte) {
        continue;
      }
      output += alphabet[byte % alphabet.length];
      if (output.length === length) {
        break;
      }
    }
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
    KODA_ARTIFACT_IMAGE: manifest.images.artifact,
    KODA_RETRIEVAL_IMAGE: manifest.images.retrieval,
    KODA_RUNTIME_KERNEL_IMAGE: manifest.images.runtime_kernel,
    KODA_POSTGRES_IMAGE: manifest.images.postgres,
    KODA_SEAWEEDFS_IMAGE: manifest.images.seaweedfs,
    KODA_AWSCLI_IMAGE: manifest.images.awscli,
    KODA_RELEASE_VERSION: manifest.version,
  };
  const missing = Object.entries(imageMap)
    .filter(([, value]) => !value)
    .map(([key]) => key);
  if (missing.length > 0) {
    throw new Error(
      `Release manifest is missing required image refs: ${missing.join(", ")}. ` +
        "Re-run `python scripts/release_metadata.py --write` and rebuild the bundle.",
    );
  }
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

function loopbackUrl(port, path = "") {
  return `http://${LOOPBACK_HOST}:${port}${path}`;
}

function composeProjectName(installDir) {
  // Mirrors the docker compose project-name normalization rules: lowercase the
  // basename, drop characters outside [a-z0-9_-], and trim leading separators
  // so we can ask `docker volume ls` for volumes labeled with this project.
  const base = basename(installDir).toLowerCase();
  const filtered = base.replace(/[^a-z0-9_-]/g, "");
  return filtered.replace(/^[_-]+/, "");
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

function composeUpEnv() {
  const limit = process.env.COMPOSE_PARALLEL_LIMIT;
  return {
    COMPOSE_PARALLEL_LIMIT: limit && limit.trim() ? limit : "1",
  };
}

function listManagedVolumes(projectName) {
  if (!projectName) {
    return [];
  }
  const result = spawnSync(
    "docker",
    [
      "volume",
      "ls",
      "--quiet",
      "--filter",
      `label=com.docker.compose.project=${projectName}`,
    ],
    { encoding: "utf-8", stdio: ["ignore", "pipe", "pipe"] },
  );
  if (result.error || result.status !== 0) {
    return [];
  }
  return String(result.stdout || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function resetManagedVolumes(installDir) {
  // Prefer compose-aware teardown so we honor labels and dependencies. The
  // command is a no-op when nothing exists, which matches the "fresh install"
  // expectation users have when they pass --reset-volumes.
  const composeFile = join(installDir, "bundle", "docker-compose.release.yml");
  if (existsSync(composeFile) && existsSync(join(installDir, ".env"))) {
    const result = spawnSync(
      "docker",
      [...composeArgs(installDir), "down", "-v", "--remove-orphans"],
      { cwd: installDir, stdio: "inherit" },
    );
    if (result.status === 0) {
      return;
    }
  }

  const projectName = composeProjectName(installDir);
  const volumes = listManagedVolumes(projectName);
  if (volumes.length === 0) {
    return;
  }
  const removal = spawnSync("docker", ["volume", "rm", "-f", ...volumes], {
    stdio: "inherit",
  });
  if (removal.status !== 0) {
    throw new Error(
      `Failed to remove managed volumes for project '${projectName}'. ` +
        `Try: docker volume rm ${volumes.join(" ")}`,
    );
  }
}

function describeReinstallConflict(installDir, volumes) {
  const projectName = composeProjectName(installDir);
  return [
    `Detected pre-existing Docker volumes for compose project '${projectName}' but no .env in ${installDir}.`,
    "These volumes were created by a previous install and still hold the old Postgres credentials. ",
    "A fresh install would generate new random passwords that the existing volume will reject.",
    "",
    "Pick one:",
    `  • Reuse the previous install: copy its .env back to ${installDir}/.env, then re-run koda install.`,
    `  • Wipe and start clean:       koda install --dir ${installDir} --reset-volumes`,
    `  • Inspect the volumes:        docker volume ls --filter label=com.docker.compose.project=${projectName}`,
    "",
    `Volumes detected: ${volumes.join(", ")}`,
  ].join("\n");
}

async function probePostgresAuth(installDir, env) {
  // Run a single auth-only query through the postgres container. We pass the
  // password via -e so it never lands on the docker exec argv.
  const args = [
    ...composeArgs(installDir),
    "exec",
    "-T",
    "-e",
    `PGPASSWORD=${env.POSTGRES_PASSWORD || ""}`,
    "postgres",
    "psql",
    "-h",
    "localhost",
    "-U",
    String(env.POSTGRES_USER || ""),
    "-d",
    String(env.POSTGRES_DB || ""),
    "-tAc",
    "SELECT 1",
  ];
  const result = spawnSync("docker", args, {
    cwd: installDir,
    encoding: "utf-8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  const stdout = String(result.stdout || "").trim();
  const stderr = String(result.stderr || "").trim();
  return {
    ok: result.status === 0 && stdout === "1",
    output: stderr || stdout || `psql exited with code ${result.status ?? "?"}`,
  };
}

function describePostgresAuthFailure(installDir, output) {
  const projectName = composeProjectName(installDir);
  return [
    "Postgres rejected the credentials in .env.",
    "This usually means a Docker volume from a previous install still holds the old password hash.",
    "",
    `psql output:`,
    output,
    "",
    "Pick one:",
    `  • Reuse the previous install: restore the matching .env into ${installDir}/.env, then re-run.`,
    `  • Wipe and start clean:       koda install --dir ${installDir} --reset-volumes`,
    `  • Inspect the volumes:        docker volume ls --filter label=com.docker.compose.project=${projectName}`,
  ].join("\n");
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

function runCommandCapture(command, args, { cwd, env } = {}) {
  return spawnSync(command, args, {
    cwd,
    encoding: "utf-8",
    stdio: ["ignore", "pipe", "pipe"],
    env: env ? { ...process.env, ...env } : process.env,
  });
}

function commandExists(command) {
  const result = spawnSync("sh", ["-lc", `command -v ${command}`], {
    stdio: "ignore",
  });
  return result.status === 0;
}

function trimCommandOutput(text, limit = 1600) {
  const trimmed = String(text || "").trim();
  if (!trimmed || trimmed.length <= limit) {
    return trimmed;
  }
  return `${trimmed.slice(0, limit)}\n...`;
}

function dockerStartHint() {
  if (process.platform === "darwin" || process.platform === "win32") {
    return "Start Docker Desktop and wait until it says Docker is running, then run this command again.";
  }
  return "Start the Docker service, then run this command again.";
}

function isDockerDaemonUnavailableOutput(text) {
  const normalized = String(text || "").toLowerCase();
  return [
    "cannot connect to the docker daemon",
    "cannot connect to docker daemon",
    "is the docker daemon running",
    "docker daemon is not running",
    "docker desktop is not running",
    "error during connect",
  ].some((snippet) => normalized.includes(snippet));
}

function dockerDaemonUnavailableError(output = "") {
  const dockerOutput = trimCommandOutput(output);
  const message = [
    "Koda needs Docker to start its local services, but the Docker daemon is not reachable.",
    dockerStartHint(),
    "Check with: docker info",
  ];
  if (dockerOutput) {
    message.push("", "Docker said:", dockerOutput);
  }
  return new Error(message.join("\n"));
}

function ensureDockerReady() {
  const result = runCommandCapture("docker", ["info", "--format", "{{json .ServerVersion}}"]);
  if (result.error) {
    if (result.error.code === "ENOENT") {
      throw new Error(
        [
          "Koda needs Docker to start its local services, but the Docker CLI was not found.",
          "Install Docker Desktop or Docker Engine, then run this command again.",
          "Check with: docker --version",
        ].join("\n"),
      );
    }
    throw result.error;
  }
  if (result.status === 0) {
    return;
  }

  throw dockerDaemonUnavailableError(`${result.stderr || ""}\n${result.stdout || ""}`);
}

function runDockerCompose(installDir, args, options = {}) {
  ensureDockerReady();
  return runCommand("docker", [...composeArgs(installDir), ...args], {
    cwd: installDir,
    ...options,
  });
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
  const dashboardUrl = loopbackUrl(webPort);
  const payload = {
    install_dir: installDir,
    control_plane_url: loopbackUrl(controlPlanePort),
    health_url: loopbackUrl(controlPlanePort, "/health"),
    dashboard_url: dashboardUrl,
    setup_url: `${dashboardUrl}/setup`,
    dashboard_setup_url: `${dashboardUrl}/setup`,
    legacy_setup_url: loopbackUrl(controlPlanePort, "/setup"),
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
  const onboardingPayload = await onboardingResponse.json().catch(() => ({}));
  checks.onboarding = {
    ok: onboardingResponse.ok,
    status: onboardingResponse.status,
    has_owner: Boolean(onboardingPayload.has_owner),
    bootstrap_required: Boolean(onboardingPayload.bootstrap_required),
    bootstrap_file_path: onboardingPayload.bootstrap_file_path || null,
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
  console.log(`Setup:       ${payload.dashboard_setup_url}`);
  console.log(`Bridge:      ${payload.legacy_setup_url}`);
  console.log(`Health:      ${payload.health_url}`);
  console.log("");
  for (const [name, result] of Object.entries(payload.checks)) {
    console.log(`${result.ok ? "OK" : "FAIL"} ${name} (${result.status})`);
  }
  if (!payload.ok) {
    throw new Error("Doctor checks failed.");
  }
}

async function readBootstrapCodeFromContainer(installDir, env) {
  const stateRoot = String(env.STATE_ROOT_DIR || "/var/lib/koda/state").trim() || "/var/lib/koda/state";
  const bootstrapPath = `${stateRoot.replace(/\/$/, "")}/control_plane/bootstrap.txt`;
  const result = runCommandCapture(
    "docker",
    [
      ...composeArgs(installDir),
      "exec",
      "-T",
      "app",
      "sh",
      "-lc",
      `cat ${JSON.stringify(bootstrapPath)} 2>/dev/null`,
    ],
    { cwd: installDir },
  );
  const code = String(result.stdout || "").trim().split(/\s+/)[0] || "";
  if (result.status === 0 && code) {
    return {
      code,
      expires_at: null,
      source: "bootstrap_file",
      bootstrap_file_path: bootstrapPath,
    };
  }
  return {
    code: "",
    error: String(result.stderr || result.stdout || `Could not read ${bootstrapPath} from the app container.`).trim(),
    bootstrap_file_path: bootstrapPath,
  };
}

async function issueBootstrapCode(installDir) {
  const env = await readInstallEnv(installDir);
  const controlPlanePort = env.CONTROL_PLANE_PORT || "8090";
  const webPort = env.WEB_PORT || "3000";
  const recoveryToken = String(env.CONTROL_PLANE_API_TOKEN || "").trim();
  const failures = [];
  if (recoveryToken) {
    try {
      const response = await fetch(loopbackUrl(controlPlanePort, "/api/control-plane/auth/bootstrap/codes"), {
        method: "POST",
        headers: {
          Authorization: `Bearer ${recoveryToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ label: "npm_cli" }),
        cache: "no-store",
      });
      const payload = await response.json().catch(() => ({}));
      if (response.ok && payload.code) {
        return {
          url: `${loopbackUrl(webPort)}/setup`,
          code: payload.code,
          expires_at: payload.expires_at || null,
          source: "api",
        };
      }
      failures.push(String(payload.error || `API returned HTTP ${response.status}.`));
    } catch (error) {
      failures.push(error instanceof Error ? error.message : String(error));
    }
  } else {
    failures.push("CONTROL_PLANE_API_TOKEN is missing.");
  }

  await fetch(loopbackUrl(controlPlanePort, "/api/control-plane/onboarding/status"), {
    cache: "no-store",
  }).catch(() => null);
  const fallback = await readBootstrapCodeFromContainer(installDir, env);
  if (fallback.code) {
    return {
      url: `${loopbackUrl(webPort)}/setup`,
      code: fallback.code,
      expires_at: fallback.expires_at,
      source: fallback.source,
      bootstrap_file_path: fallback.bootstrap_file_path,
      warnings: failures,
    };
  }
  failures.push(fallback.error);
  throw new Error(
    [
      "Could not issue or read a setup code.",
      ...failures.map((failure) => `- ${failure}`),
      `Try: koda logs --dir ${installDir} app`,
      `Bootstrap file inside the app container: ${fallback.bootstrap_file_path}`,
    ].join("\n"),
  );
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
  const resetVolumes = consumeFlag(args, "--reset-volumes");
  const manifestArg = consumeOption(args, "--manifest", undefined);
  const installDir = resolveInstallDir(args);
  const { manifest, releaseRoot } = await loadManifest(manifestArg);

  ensureDockerReady();

  // The .env we are about to mint will only match a fresh Postgres data
  // directory. If the user already has volumes from a prior install but no
  // .env (typical after `koda uninstall` without --purge, or a manual rm of
  // ~/.koda), abort with an actionable message instead of waiting for the app
  // healthcheck to time out on auth failures.
  const envExistedBefore = existsSync(join(installDir, ".env"));
  if (resetVolumes) {
    resetManagedVolumes(installDir);
  } else if (!envExistedBefore) {
    const volumes = listManagedVolumes(composeProjectName(installDir));
    if (volumes.length > 0) {
      throw new Error(describeReinstallConflict(installDir, volumes));
    }
  }

  await copyReleaseBundle(releaseRoot, installDir);
  await writeBootstrapEnvIfMissing(installDir);
  await writeReleaseEnv(installDir, manifest);
  await verifyBundledChecksums(installDir, manifest);

  try {
    runDockerCompose(installDir, ["up", "-d"], {
      env: composeUpEnv(),
    });
  } catch (error) {
    const env = await readInstallEnv(installDir).catch(() => ({}));
    const probe = await probePostgresAuth(installDir, env).catch(() => null);
    if (probe && !probe.ok) {
      if (isDockerDaemonUnavailableOutput(probe.output)) {
        throw dockerDaemonUnavailableError(probe.output);
      }
      throw new Error(describePostgresAuthFailure(installDir, probe.output));
    }
    throw error;
  }

  const env = await readInstallEnv(installDir);
  await waitForHttp(loopbackUrl(env.CONTROL_PLANE_PORT || "8090", "/health"), "the control plane");
  await waitForHttp(loopbackUrl(env.WEB_PORT || "3000"), "the web dashboard");

  await doctorCommand(["--dir", installDir]);
  const bootstrap = await issueBootstrapCode(installDir);

  console.log("");
  console.log(`Koda ${manifest.version} installed.`);
  console.log(`Dashboard: ${bootstrap.url}`);
  console.log(`Setup code: ${bootstrap.code}`);
  if (bootstrap.source === "bootstrap_file" && bootstrap.bootstrap_file_path) {
    console.log(`Source: ${bootstrap.bootstrap_file_path}`);
  }
  for (const warning of bootstrap.warnings || []) {
    console.log(`Note: ${warning}`);
  }
  if (bootstrap.expires_at) {
    console.log(`Expires at: ${bootstrap.expires_at}`);
  }

  if (!headless) {
    maybeOpenBrowser(bootstrap.url);
  }
}

async function upCommand(args) {
  const installDir = resolveInstallDir(args);
  runDockerCompose(installDir, ["up", "-d"], {
    env: composeUpEnv(),
  });
}

async function downCommand(args) {
  const installDir = resolveInstallDir(args);
  runDockerCompose(installDir, ["down"]);
}

async function logsCommand(args) {
  const installDir = resolveInstallDir(args);
  runDockerCompose(installDir, ["logs", "-f", ...args]);
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
  if (payload.source === "bootstrap_file" && payload.bootstrap_file_path) {
    console.log(`Source: ${payload.bootstrap_file_path}`);
  }
  for (const warning of payload.warnings || []) {
    console.log(`Note: ${warning}`);
  }
  if (payload.expires_at) {
    console.log(`Expires at: ${payload.expires_at}`);
  }
}

async function updateCommand(args) {
  const manifestArg = consumeOption(args, "--manifest", undefined);
  const installDir = resolveInstallDir(args);
  const { manifest, releaseRoot } = await loadManifest(manifestArg);
  let backupRoot = null;
  let backupDir = null;

  ensureDockerReady();

  if (existsSync(installDir)) {
    backupRoot = await mkdtemp(join(tmpdir(), "koda-rollback-"));
    backupDir = join(backupRoot, basename(installDir));
    await cp(installDir, backupDir, { recursive: true, force: true });
  }

  try {
    await copyReleaseBundle(releaseRoot, installDir);
    await writeReleaseEnv(installDir, manifest);
    await verifyBundledChecksums(installDir, manifest);
    runDockerCompose(installDir, ["up", "-d"], {
      env: composeUpEnv(),
    });
    await doctorCommand(["--dir", installDir]);
    if (backupRoot !== null) {
      await rm(backupRoot, { recursive: true, force: true });
    }
  } catch (error) {
    if (backupDir !== null && existsSync(backupDir)) {
      await rm(installDir, { recursive: true, force: true });
      await cp(backupDir, installDir, { recursive: true, force: true });
      runDockerCompose(installDir, ["up", "-d"], {
        env: composeUpEnv(),
      });
      if (backupRoot !== null) {
        await rm(backupRoot, { recursive: true, force: true });
      }
    }
    throw error;
  }
}

async function uninstallCommand(args) {
  const purge = consumeFlag(args, "--purge");
  const installDir = resolveInstallDir(args);
  if (existsSync(join(installDir, "bundle", "docker-compose.release.yml"))) {
    runDockerCompose(installDir, ["down", "-v"]);
  }
  if (purge) {
    await rm(installDir, { recursive: true, force: true });
  }
}

await main();
