// Original code-native mark; generated binaries stay outside the source/public tree.
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');
function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  }
  return (crc ^ 0xffffffff) >>> 0;
}
function chunk(type, bytes) {
  const tag = Buffer.from(type);
  const result = Buffer.alloc(bytes.length + 12);
  result.writeUInt32BE(bytes.length); tag.copy(result, 4); bytes.copy(result, 8);
  result.writeUInt32BE(crc32(Buffer.concat([tag, bytes])), result.length - 4);
  return result;
}
function createIcon(directory) {
  const size = 256;
  const pixels = Buffer.alloc((size * 4 + 1) * size);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const paper = x > 57 && x < 199 && y > 44 && y < 211;
    const line = x > 83 && x < 174 && ((y > 80 && y < 91) || (y > 116 && y < 127) || (y > 152 && y < 163));
    const color = line ? [107, 132, 122] : paper ? [250, 251, 249] : [107, 132, 122];
    const offset = y * (size * 4 + 1) + 1 + x * 4;
    pixels.set([...color, 255], offset);
  }
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size); header.writeUInt32BE(size, 4); header[8] = 8; header[9] = 6;
  const png = Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', header), chunk('IDAT', zlib.deflateSync(pixels)), chunk('IEND', Buffer.alloc(0))]);
  fs.writeFileSync(path.join(directory, 'app.png'), png);
  const ico = Buffer.alloc(22);
  ico.writeUInt16LE(1, 2); ico.writeUInt16LE(1, 4); ico.writeUInt16LE(1, 10); ico.writeUInt16LE(32, 12);
  ico.writeUInt32LE(png.length, 14); ico.writeUInt32LE(22, 18);
  fs.writeFileSync(path.join(directory, 'app.ico'), Buffer.concat([ico, png]));
}
module.exports = { createIcon };
