// Converts icon-source.svg → icon.png (1024x1024)
// Usage: node src-tauri/icons/convert-icon.mjs
// Requires: npm install sharp (run once in frontend-src/)

import sharp from 'sharp'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const svgPath = join(__dirname, 'icon-source.svg')
const outPath = join(__dirname, 'icon.png')

const svg = readFileSync(svgPath)

await sharp(svg)
  .resize(1024, 1024)
  .png()
  .toFile(outPath)

console.log('Written: ' + outPath)
