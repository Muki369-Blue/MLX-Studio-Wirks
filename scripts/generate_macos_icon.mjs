#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const __filename = fileURLToPath(import.meta.url);
const rootDir = path.resolve(path.dirname(__filename), '..');
const assetsDir = path.join(rootDir, 'assets');
const iconsetDir = path.join(assetsDir, 'MLX-Moxy-Wirks.iconset');
const svgPath = path.join(assetsDir, 'MLX-Moxy-Wirks.svg');
const quicklookPng = `${svgPath}.png`;
const basePng = path.join(assetsDir, 'MLX-Moxy-Wirks-1024.png');

const iconSizes = [
  { name: 'icon_16x16.png', size: 16 },
  { name: 'icon_16x16@2x.png', size: 32 },
  { name: 'icon_32x32.png', size: 32 },
  { name: 'icon_32x32@2x.png', size: 64 },
  { name: 'icon_128x128.png', size: 128 },
  { name: 'icon_128x128@2x.png', size: 256 },
  { name: 'icon_256x256.png', size: 256 },
  { name: 'icon_256x256@2x.png', size: 512 },
  { name: 'icon_512x512.png', size: 512 },
  { name: 'icon_512x512@2x.png', size: 1024 },
];

function run(command, args) {
  const result = spawnSync(command, args, { stdio: 'pipe', encoding: 'utf8' });
  if (result.status !== 0) {
    throw new Error(`${command} failed: ${result.stderr || result.stdout}`);
  }
}

async function build() {
  await fs.mkdir(assetsDir, { recursive: true });
  await fs.mkdir(iconsetDir, { recursive: true });

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 720 720">
  <defs>
    <linearGradient id="ring" x1="120" y1="100" x2="600" y2="620" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#6f8fe8"/>
      <stop offset="1" stop-color="#4a6fda"/>
    </linearGradient>
    <linearGradient id="ink" x1="180" y1="180" x2="560" y2="560" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#111c40"/>
      <stop offset="1" stop-color="#1e3a8a"/>
    </linearGradient>
    <linearGradient id="core" x1="250" y1="250" x2="470" y2="480" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#95b6ff"/>
      <stop offset="1" stop-color="#6c91f0"/>
    </linearGradient>
  </defs>

  <rect width="720" height="720" fill="#f4f8ff"/>

  <circle cx="360" cy="360" r="306" fill="none" stroke="url(#ring)" stroke-width="26"/>

  <path d="M140 248 L320 110 L322 208" fill="none" stroke="url(#ink)" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M580 248 L400 110" fill="none" stroke="url(#ink)" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M170 522 L326 376 L360 450 L394 376 L550 522" fill="none" stroke="url(#core)" stroke-width="18" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M210 560 L300 470 L360 548 L420 470 L510 560" fill="none" stroke="#6f8fe8" stroke-width="10" stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>
  <path d="M286 378 L434 378" fill="none" stroke="#75a4ff" stroke-width="9" stroke-linecap="round"/>

  <path d="M155 242 L122 272" fill="none" stroke="#0f172a" stroke-width="9" stroke-linecap="round"/>
  <path d="M563 242 L598 272" fill="none" stroke="#0f172a" stroke-width="9" stroke-linecap="round"/>
  <path d="M177 540 L145 578" fill="none" stroke="#0f172a" stroke-width="9" stroke-linecap="round"/>
  <path d="M543 540 L575 578" fill="none" stroke="#0f172a" stroke-width="9" stroke-linecap="round"/>
</svg>`;
  await fs.writeFile(svgPath, svg, 'utf8');

  run('qlmanage', ['-t', '-s', '1024', '-o', assetsDir, svgPath]);
  await fs.rename(quicklookPng, basePng);

  for (const { name, size } of iconSizes) {
    const target = path.join(iconsetDir, name);
    run('sips', ['-z', String(size), String(size), basePng, '--out', target]);
  }
}

build().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
