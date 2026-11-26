import assert from "node:assert/strict";
import { generateKeyPairSync, verify } from "node:crypto";
import test from "node:test";

import { createAppJwt, dispatchScheduled } from "../dispatcher.mjs";

const scheduledTime = Date.parse("2026-11-26T12:03:00.000Z");
const nowSeconds = Math.floor(scheduledTime / 1000);

function makeKeyPair() {
  const pair = generateKeyPairSync("rsa", {
    modulusLength: 2048,
    privateKeyEncoding: { type: "pkcs1", format: "pem" },
    publicKeyEncoding: { type: "spki", format: "pem" },
  });
  return pair;
}

function decodeJwtPart(value) {
  return JSON.parse(Buffer.from(value, "base64url").toString("utf8"));
}

function verifyAppJwt(jwt, publicKey) {
  const [header, payload, signature] = jwt.split(".");
  const valid = verify(
    "RSA-SHA256",
    Buffer.from(`${header}.${payload}`),
    publicKey,
    Buffer.from(signature, "base64url"),
  );
  return { valid, header: decodeJwtPart(header), payload: decodeJwtPart(payload) };
}

function mockGitHub({ dispatchStatus = 204 } = {}) {
  const { privateKey, publicKey } = makeKeyPair();
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith("/access_tokens")) {
      const jwt = options.headers.Authorization.slice("Bearer ".length);
      const checked = verifyAppJwt(jwt, publicKey);
      assert.equal(checked.valid, true);
      assert.equal(checked.header.alg, "RS256");
      assert.equal(checked.payload.iss, "123456");
      assert.equal(checked.payload.iat, nowSeconds - 60);
      assert.equal(checked.payload.exp, nowSeconds + 9 * 60);
      return Response.json({ token: "installation-token" }, { status: 201 });
    }
    return new Response(null, { status: dispatchStatus });
  };
  return { calls, fetchImpl, privateKey };
}

test("probe mode dispatches only the secret-free probe workflow", async () => {
  const github = mockGitHub();
  const logs = [];
  const result = await dispatchScheduled({
    env: {
      GITHUB_APP_ID: "123456",
      GITHUB_INSTALLATION_ID: "654321",
      GITHUB_APP_PRIVATE_KEY: github.privateKey,
    },
    scheduledTime,
    fetchImpl: github.fetchImpl,
    nowSeconds,
    logger: { info: (message) => logs.push(message) },
  });

  assert.deepEqual(result, {
    mode: "probe",
    workflow: "dispatch-probe.yml",
    scheduledAt: "2026-11-26T12:03:00.000Z",
    status: 204,
  });
  assert.equal(github.calls.length, 2);
  assert.match(github.calls[0].url, /\/app\/installations\/654321\/access_tokens$/u);
  assert.match(github.calls[1].url, /\/actions\/workflows\/dispatch-probe\.yml\/dispatches$/u);
  assert.equal(github.calls[1].options.method, "POST");
  assert.deepEqual(JSON.parse(github.calls[1].options.body), {
    ref: "main",
    inputs: { scheduled_at: "2026-11-26T12:03:00.000Z" },
  });
  assert.doesNotMatch(logs.join("\n"), /installation-token|PRIVATE KEY|Bearer/u);
});

test("clipper mode explicitly disables the manual dry-run default", async () => {
  const github = mockGitHub();
  await dispatchScheduled({
    env: {
      TARGET_MODE: "clipper",
      GITHUB_APP_ID: "123456",
      GITHUB_INSTALLATION_ID: "654321",
      GITHUB_APP_PRIVATE_KEY: github.privateKey,
    },
    scheduledTime,
    fetchImpl: github.fetchImpl,
    nowSeconds,
    logger: { info() {} },
  });
  assert.match(github.calls[1].url, /\/actions\/workflows\/clipper\.yml\/dispatches$/u);
  assert.deepEqual(JSON.parse(github.calls[1].options.body), {
    ref: "main",
    inputs: { dry_run: "false", scheduled_at: "2026-11-26T12:03:00.000Z" },
  });
});

test("an invalid target mode fails before making GitHub requests", async () => {
  let requests = 0;
  await assert.rejects(
    dispatchScheduled({
      env: { TARGET_MODE: "unknown" },
      scheduledTime,
      fetchImpl: async () => {
        requests += 1;
        return Response.json({});
      },
    }),
    /TARGET_MODE/u,
  );
  assert.equal(requests, 0);
});

test("a missing GitHub App key fails without logging or dispatching", async () => {
  let requests = 0;
  await assert.rejects(
    createAppJwt({ appId: "123456", privateKeyPem: "" }),
    /credentials are not configured/u,
  );
  await assert.rejects(
    dispatchScheduled({
      env: { GITHUB_APP_ID: "123456", GITHUB_INSTALLATION_ID: "654321" },
      scheduledTime,
      fetchImpl: async () => {
        requests += 1;
        return Response.json({});
      },
    }),
    /variables and private-key secret/u,
  );
  assert.equal(requests, 0);
});

test("GitHub errors expose only the HTTP status, not response content", async () => {
  const github = mockGitHub({ dispatchStatus: 403 });
  await assert.rejects(
    dispatchScheduled({
      env: {
        GITHUB_APP_ID: "123456",
        GITHUB_INSTALLATION_ID: "654321",
        GITHUB_APP_PRIVATE_KEY: github.privateKey,
      },
      scheduledTime,
      fetchImpl: github.fetchImpl,
      nowSeconds,
      logger: { info() {} },
    }),
    (error) => error.message === "GitHub workflow dispatch failed (HTTP 403).",
  );
});
