const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

const mode = process.argv[2];
const projectRoot = path.join(__dirname, "..");
const templates = {
  local: path.join(projectRoot, "env", "local.env"),
  split: path.join(projectRoot, "env", "split.env"),
};

if (!mode || !templates[mode]) {
  console.error("Usage: node scripts/run-mode.js <local|split>");
  process.exit(1);
}

const source = templates[mode];
const target = path.join(projectRoot, ".env.local");

if (!fs.existsSync(source)) {
  console.error(`Missing env template: ${source}`);
  process.exit(1);
}

fs.copyFileSync(source, target);
console.log(`Wrote .env.local from env/${mode}.env`);

const nextBin = require.resolve("next/dist/bin/next");
const child = spawn(process.execPath, [nextBin, "dev"], {
  cwd: projectRoot,
  stdio: "inherit",
  env: process.env,
});

child.on("exit", (code) => process.exit(code ?? 0));