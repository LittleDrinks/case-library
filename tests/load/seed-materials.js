const TARGET_MATERIALS = 12_480;
const BATCH_SIZE = 500;
const TYPES = ["政策文件", "统计数据", "视频影像", "图片", "学术论文"];

function accessLevel(index) {
  if (index % 5 === 0) return "private";
  return index % 5 === 1 ? "public" : "campus";
}

function material(index) {
  const sequence = String(index + 1).padStart(5, "0");
  return {
    id: `load-material-${sequence}`,
    title: `思政教学负载素材 ${sequence}`,
    summary: "课程思政、科技创新与人才培养的容量测试资料。",
    excerpt: "用于验证目标目录规模下的检索、分面与访问控制性能。",
    source: `负载来源 ${index % 64}`,
    sourceUrl: `https://example.test/materials/${sequence}`,
    tags: ["思政", TYPES[index % TYPES.length]],
    materialType: TYPES[index % TYPES.length],
    authority: index % 3 === 0 ? "original" : "secondary",
    accessLevel: accessLevel(index),
    status: "active",
    publishedAt: `2026-07-${String((index % 28) + 1).padStart(2, "0")}`,
    createdBy: "u-admin-demo",
    citedCount: index % 43,
    publicReferenceCount: 0,
  };
}

function insertBatch(start) {
  const end = Math.min(start + BATCH_SIZE, TARGET_MATERIALS);
  const indexes = Array.from({ length: end - start }, (_, offset) => start + offset);
  db.materials.insertMany(indexes.map(material), { ordered: false });
}

db.materials.deleteMany({});
db.search_outbox.deleteMany({});
db.search_revocations.deleteMany({});
db.search_control.deleteMany({});
for (let start = 0; start < TARGET_MATERIALS; start += BATCH_SIZE) insertBatch(start);
print(`seeded_materials=${db.materials.countDocuments({ status: "active" })}`);
