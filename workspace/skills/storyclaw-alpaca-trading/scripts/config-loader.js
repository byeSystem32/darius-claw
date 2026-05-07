#!/usr/bin/env node
/**
 * Multi-User Config Loader
 * Loads Alpaca credentials from OpenClaw secrets, /srv/darius-claw.env,
 * an OpenClaw workspace secret file, or a local .env file.
 */

const fs = require("fs");
const path = require("path");

const DEFAULT_BASE_URL = "https://paper-api.alpaca.markets";
const DEFAULT_DATA_URL = "https://data.alpaca.markets";
const OPENCLAW_ENV_PATHS = [
  "/home/node/.openclaw/workspace/config/darius-claw.env",
  "/home/node/.openclaw/workspace/.openclaw/darius-claw.env",
  "/srv/darius-claw.env",
  process.env.OPENCLAW_ENV_PATH,
].filter(Boolean);
const API_KEY_NAMES = ["ALPACA_API_KEY", "APCA_API_KEY_ID"];
const API_SECRET_NAMES = ["ALPACA_API_SECRET", "ALPACA_API_SECRET_KEY", "APCA_API_SECRET_KEY"];

function parseEnvFile(envPath) {
  if (!fs.existsSync(envPath)) return {};

  return fs
    .readFileSync(envPath, "utf8")
    .split(/\r?\n/)
    .reduce((values, line) => {
      let trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) return values;
      if (trimmed.startsWith("export ")) {
        trimmed = trimmed.slice("export ".length).trim();
      }

      const separator = trimmed.indexOf("=");
      if (separator === -1) return values;

      const key = trimmed.slice(0, separator).trim();
      let value = trimmed.slice(separator + 1).trim();
      if (
        (value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))
      ) {
        value = value.slice(1, -1);
      }

      values[key] = value;
      return values;
    }, {});
}

function firstConfiguredValue(sources, names) {
  for (const source of sources) {
    for (const name of names) {
      if (source[name]) return source[name];
    }
  }

  return "";
}

function describeEnvFile(envPath) {
  const values = parseEnvFile(envPath);
  return {
    envPath,
    exists: fs.existsSync(envPath),
    hasApiKey: API_KEY_NAMES.some((name) => !!values[name]),
    hasApiSecret: API_SECRET_NAMES.some((name) => !!values[name]),
  };
}

function loadUserConfig(exitOnMissing = true) {
  const USER_ID = process.env.USER_ID || process.env.TELEGRAM_USER_ID;
  const localEnvPath = path.join(__dirname, "..", ".env");
  const envFilePaths = [localEnvPath, ...OPENCLAW_ENV_PATHS];
  const envConfigs = envFilePaths.map(parseEnvFile);
  const configSources = [process.env, ...envConfigs.reverse()];

  const config = {
    apiKey: firstConfiguredValue(configSources, API_KEY_NAMES),
    apiSecret: firstConfiguredValue(configSources, API_SECRET_NAMES),
    baseUrl: firstConfiguredValue(configSources, ["ALPACA_BASE_URL"]) || DEFAULT_BASE_URL,
    dataUrl: firstConfiguredValue(configSources, ["ALPACA_DATA_URL"]) || DEFAULT_DATA_URL,
    userId: USER_ID || process.env.USERNAME || "default",
  };

  const exists = !!config.apiKey && !!config.apiSecret;
  if (!exists) {
    if (exitOnMissing) {
      console.error("❌ Alpaca API credentials not configured");
      console.error("   OpenClaw: add ALPACA_API_KEY and ALPACA_API_SECRET to one of:");
      OPENCLAW_ENV_PATHS.forEach((envPath) => {
        const file = describeEnvFile(envPath);
        const status = file.exists
          ? `found, key=${file.hasApiKey ? "yes" : "no"}, secret=${file.hasApiSecret ? "yes" : "no"}`
          : "not found";
        console.error(`     - ${envPath} (${status})`);
      });
      console.error(`   Local fallback: copy .env.example to ${localEnvPath}`);
      console.error("   Required: ALPACA_API_KEY and ALPACA_API_SECRET");
      console.error("   Also accepted: APCA_API_KEY_ID and APCA_API_SECRET_KEY");
      process.exit(1);
    }
  }

  return {
    config,
    userId: config.userId,
    credentialsPath: [...envFilePaths].reverse().find((envPath) => fs.existsSync(envPath)),
    exists,
  };
}

// Check if user is configured (soft mode, doesn't exit)
function checkUserConfigured() {
  return loadUserConfig(false);
}

function getStatePath(userId, filename = "state.json") {
  const stateDir = path.join(__dirname, "..", "state");
  if (!fs.existsSync(stateDir)) {
    fs.mkdirSync(stateDir, { recursive: true });
  }
  return path.join(stateDir, `${userId}.${filename}`);
}

module.exports = { loadUserConfig, checkUserConfigured, getStatePath };
