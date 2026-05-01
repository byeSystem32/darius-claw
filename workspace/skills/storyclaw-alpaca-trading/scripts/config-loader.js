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

function loadUserConfig(exitOnMissing = true) {
  const USER_ID = process.env.USER_ID || process.env.TELEGRAM_USER_ID;
  const localEnvPath = path.join(__dirname, "..", ".env");
  const envFilePaths = [localEnvPath, ...OPENCLAW_ENV_PATHS];
  const envConfig = envFilePaths.reduce(
    (values, envPath) => ({ ...values, ...parseEnvFile(envPath) }),
    {},
  );

  const config = {
    apiKey: process.env.ALPACA_API_KEY || envConfig.ALPACA_API_KEY || "",
    apiSecret: process.env.ALPACA_API_SECRET || envConfig.ALPACA_API_SECRET || "",
    baseUrl: process.env.ALPACA_BASE_URL || envConfig.ALPACA_BASE_URL || DEFAULT_BASE_URL,
    dataUrl: process.env.ALPACA_DATA_URL || envConfig.ALPACA_DATA_URL || DEFAULT_DATA_URL,
    userId: USER_ID || process.env.USERNAME || "default",
  };

  const exists = !!config.apiKey && !!config.apiSecret;
  if (!exists) {
    if (exitOnMissing) {
      console.error("❌ Alpaca API credentials not configured");
      console.error("   OpenClaw: add ALPACA_API_KEY and ALPACA_API_SECRET to one of:");
      OPENCLAW_ENV_PATHS.forEach((envPath) => console.error(`     - ${envPath}`));
      console.error(`   Local fallback: copy .env.example to ${localEnvPath}`);
      console.error("   Required: ALPACA_API_KEY and ALPACA_API_SECRET");
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
