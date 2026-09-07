import { crc32 } from "node:zlib";

export const SKILL_ID = "sizheng-case-generator";
const UTF8_FLAG = 0x0800;

function entry(name, text) {
  const nameBytes = Buffer.from(name, "utf8");
  const data = Buffer.from(text, "utf8");
  const local = Buffer.alloc(30);
  local.writeUInt32LE(0x04034b50);
  local.writeUInt16LE(20, 4);
  local.writeUInt16LE(UTF8_FLAG, 6);
  local.writeUInt16LE(0, 8);
  local.writeUInt32LE(crc32(data), 14);
  local.writeUInt32LE(data.length, 18);
  local.writeUInt32LE(data.length, 22);
  local.writeUInt16LE(nameBytes.length, 26);
  return { nameBytes, data, local };
}

function central(offset, item) {
  const head = Buffer.alloc(46);
  head.writeUInt32LE(0x02014b50);
  head.writeUInt16LE(20, 4);
  head.writeUInt16LE(20, 6);
  head.writeUInt16LE(UTF8_FLAG, 8);
  head.writeUInt32LE(crc32(item.data), 16);
  head.writeUInt32LE(item.data.length, 20);
  head.writeUInt32LE(item.data.length, 24);
  head.writeUInt16LE(item.nameBytes.length, 28);
  head.writeUInt32LE(offset, 42);
  return head;
}

function endRecord(offset, size, count) {
  const tail = Buffer.alloc(22);
  tail.writeUInt32LE(0x06054b50);
  tail.writeUInt16LE(count, 8);
  tail.writeUInt16LE(count, 10);
  tail.writeUInt32LE(size, 12);
  tail.writeUInt32LE(offset, 16);
  return tail;
}

function localEntries(files) {
  const placed = [];
  let offset = 0;
  for (const [name, text] of Object.entries(files)) {
    const item = entry(name, text);
    const length = item.local.length + item.nameBytes.length + item.data.length;
    placed.push({ item, offset, length });
    offset += length;
  }
  return placed;
}

export function buildSkillZip(files) {
  const placed = localEntries(files);
  const parts = [];
  let size = 0;
  for (const { item, offset } of placed) {
    parts.push(item.local, item.nameBytes, item.data);
    const head = central(offset, item);
    parts.push(head, item.nameBytes);
    size += head.length + item.nameBytes.length;
  }
  const start = placed.reduce((total, { length }) => total + length, 0);
  parts.push(endRecord(start, size, placed.length));
  return Buffer.concat(parts);
}

export function teachingPackage() {
  const dir = "sizheng-case-generator";
  const skill = [
    "---",
    `name: "${SKILL_ID}"`,
    'description: "习近平文化思想课程思政案例生成技能，用于教学案例生成与修订。"',
    "---",
    "",
    "# 习近平文化思想课程思政案例生成技能",
    "",
    "详细规范见 references/ 目录，写作前必读。",
    "",
  ].join("\n");
  return buildSkillZip({
    [`${dir}/SKILL.md`]: skill,
    [`${dir}/references/模板规范.md`]: "# 模板规范\n\n选题原则、结构模块、行文风格、检查清单。",
  });
}
