#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const __filename = fileURLToPath(import.meta.url);
const rootDir = path.resolve(path.dirname(__filename), '..');
const assetsDir = path.join(rootDir, 'assets');
const iconsetDir = path.join(assetsDir, 'MLX-Moxy-Wirks.iconset');
const sourceSvgPath = path.join(rootDir, 'static', 'logo-moxy-wirks.svg');
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
  await fs.rm(iconsetDir, { recursive: true, force: true });
  await fs.mkdir(iconsetDir, { recursive: true });
  await fs.rm(quicklookPng, { force: true });
  await fs.rm(basePng, { force: true });

  const sourceSvg = await fs.readFile(sourceSvgPath, 'utf8');
  const normalizedSvg = sourceSvg.replace(
    /<svg\b([^>]*)>/,
    (match, attrs) => {
      let nextAttrs = attrs;
      if (!/\bwidth=/.test(nextAttrs)) {
        nextAttrs += ' width="1024"';
      }
      if (!/\bheight=/.test(nextAttrs)) {
        nextAttrs += ' height="1024"';
      }
      return `<svg${nextAttrs}>`;
    },
  );
  await fs.writeFile(svgPath, normalizedSvg, 'utf8');

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
