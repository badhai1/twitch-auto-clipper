const API_ROOT = "https://api.github.com";
const API_VERSION = "2022-11-28";
const USER_AGENT = "TwitchAutoClipper/1.0 (+https://github.com/badhai1/twitch-auto-clipper)";
const OWNER = "badhai1";
const REPOSITORY = "twitch-auto-clipper";
const PROBE_WORKFLOW = "dispatch-probe.yml";
const CLIPPER_WORKFLOW = "clipper.yml";

function encodeBase64Url(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/u, "");
}

function decodePem(pem) {
  const encoded = pem
    .replace(/-----BEGIN [^-]+-----/gu, "")
    .replace(/-----END [^-]+-----/gu, "")
    .replace(/\s/gu, "");
  const binary = atob(encoded);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function der(tag, value) {
  const lengthBytes = [];
  if (value.length < 128) {
    lengthBytes.push(value.length);
  } else {
    let remaining = value.length;
    const reversed = [];
    while (remaining > 0) {
      reversed.push(remaining & 0xff);
      remaining >>>= 8;
    }
    lengthBytes.push(0x80 | reversed.length, ...reversed.reverse());
  }
  return Uint8Array.from([tag, ...lengthBytes, ...value]);
}

function concatBytes(...parts) {
  const result = new Uint8Array(parts.reduce((length, part) => length + part.length, 0));
  let offset = 0;
  for (const part of parts) {
    result.set(part, offset);
    offset += part.length;
  }
  return result;
}

function pkcs8PrivateKey(pem) {
  const keyBytes = decodePem(pem);
  if (pem.includes("BEGIN PRIVATE KEY")) return keyBytes;
  if (!pem.includes("BEGIN RSA PRIVATE KEY")) {
    throw new Error("GitHub App private key must be an RSA PEM key.");
  }

  // GitHub downloads RSA keys as PKCS#1. WebCrypto imports PKCS#8, so wrap
  // the original RSA sequence in a PKCS#8 PrivateKeyInfo container.
  const version = Uint8Array.of(0x02, 0x01, 0x00);
  const rsaEncryption = Uint8Array.of(
    0x30, 0x0d, 0x06, 0x09, 0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x01, 0x01,
    0x05, 0x00,
  );
  return der(0x30, concatBytes(version, rsaEncryption, der(0x04, keyBytes)));
}

export async function createAppJwt({ appId, privateKeyPem, nowSeconds = Math.floor(Date.now() / 1000) }) {
  if (!appId || !privateKeyPem) throw new Error("GitHub App credentials are not configured.");
  const header = encodeBase64Url(
    new TextEncoder().encode(JSON.stringify({ alg: "RS256", typ: "JWT" })),
  );
  const payload = encodeBase64Url(
    new TextEncoder().encode(
      JSON.stringify({ iat: nowSeconds - 60, exp: nowSeconds + 9 * 60, iss: String(appId) }),
    ),
  );
  const signingInput = `${header}.${payload}`;
  const key = await crypto.subtle.importKey(
    "pkcs8",
    pkcs8PrivateKey(privateKeyPem),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    key,
    new TextEncoder().encode(signingInput),
  );
  return `${signingInput}.${encodeBase64Url(new Uint8Array(signature))}`;
}

function dispatchDetails(mode, scheduledTime) {
  const scheduledAt = new Date(scheduledTime);
  if (!Number.isFinite(scheduledAt.getTime())) {
    throw new Error("Cloudflare did not provide a valid scheduled time.");
  }
  const scheduledAtIso = scheduledAt.toISOString();

  if (mode === "probe") {
    return {
      workflow: PROBE_WORKFLOW,
      payload: { ref: "main", inputs: { scheduled_at: scheduledAtIso } },
      scheduledAtIso,
    };
  }
  if (mode === "clipper") {
    return {
      workflow: CLIPPER_WORKFLOW,
      // Explicit false is required because the workflow's manual default is a dry run.
      payload: {
        ref: "main",
        inputs: { dry_run: "false", scheduled_at: scheduledAtIso },
      },
      scheduledAtIso,
    };
  }
  throw new Error("TARGET_MODE must be either probe or clipper.");
}

async function installationToken(env, fetchImpl, nowSeconds) {
  if (!env.GITHUB_APP_ID || !env.GITHUB_INSTALLATION_ID || !env.GITHUB_APP_PRIVATE_KEY) {
    throw new Error("GitHub App variables and private-key secret must be configured.");
  }
  const jwt = await createAppJwt({
    appId: env.GITHUB_APP_ID,
    privateKeyPem: env.GITHUB_APP_PRIVATE_KEY,
    nowSeconds,
  });
  const response = await fetchImpl(
    `${API_ROOT}/app/installations/${encodeURIComponent(env.GITHUB_INSTALLATION_ID)}/access_tokens`,
    {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${jwt}`,
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": API_VERSION,
      },
      body: "{}",
    },
  );
  if (!response.ok) {
    const detail = await safeGitHubFailureDetail(response);
    throw new Error(
      `GitHub App token request failed (HTTP ${response.status}${detail}).`,
    );
  }
  const data = await response.json();
  if (!data.token) throw new Error("GitHub did not return an installation token.");
  return data.token;
}

export async function dispatchScheduled({
  env,
  scheduledTime,
  fetchImpl = globalThis.fetch,
  nowSeconds = Math.floor(Date.now() / 1000),
  logger = console,
}) {
  const mode = env.TARGET_MODE || "probe";
  const { workflow, payload, scheduledAtIso } = dispatchDetails(mode, scheduledTime);
  const token = await installationToken(env, fetchImpl, nowSeconds);
  const response = await fetchImpl(
    `${API_ROOT}/repos/${OWNER}/${REPOSITORY}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": API_VERSION,
      },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    const detail = await safeGitHubFailureDetail(response);
    throw new Error(
      `GitHub workflow dispatch failed (HTTP ${response.status}${detail}).`,
    );
  }
  logger.info(`Dispatch accepted: mode=${mode}; workflow=${workflow}; scheduled_at=${scheduledAtIso}.`);
  return { mode, workflow, scheduledAt: scheduledAtIso, status: response.status };
}

async function safeGitHubFailureDetail(response) {
  try {
    const body = await response.clone().json();
    if (typeof body?.message !== "string") return "";
    const message = body.message
      .replace(/-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/giu, "[redacted private key]")
      .replace(/\bBearer\s+\S+/giu, "Bearer [redacted]")
      .replace(/\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|cfat_[A-Za-z0-9_]+)\b/giu, "[redacted]")
      .replace(/\b[A-Za-z0-9+/_=-]{40,}\b/gu, "[redacted]")
      .replace(/[\r\n\t]+/gu, " ")
      .trim()
      .slice(0, 160);
    return message ? `; detail=${message}` : "";
  } catch {
    return "";
  }
}

export default {
  async scheduled(controller, env) {
    await dispatchScheduled({ env, scheduledTime: controller.scheduledTime });
  },
};
