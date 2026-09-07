import { strToU8, zipSync } from "fflate";

export const SKILL_ID = "sizheng-case-generator";

export function buildSkillZip(files) {
  const data = Object.fromEntries(Object.entries(files).map(([name, text]) => [name, strToU8(text)]));
  return Buffer.from(zipSync(data));
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
    [`${dir}/references/examples/生态保护案例-本科生教学设计.txt`]: "教学设计范例：主题——生态保护与生物多样性。",
  });
}
