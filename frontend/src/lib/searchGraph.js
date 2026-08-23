const MAX_RESOURCES = 16;
const MAX_TOPICS = 6;

function itemTopics(item) {
  const byKind = {
    case: [item.typeName, item.course, ...(item.theoryPoints || [])],
    knowledge: [item.chapter, item.unit, item.edition],
    material: [item.materialType, ...(item.tags || [])],
  };
  const values = byKind[item.kind] || [];
  return [...new Set(values.filter(Boolean).map((value) => String(value).trim()))];
}

function topicCounts(items) {
  const counts = new Map();
  items.forEach((item) => itemTopics(item).forEach((topic) => {
    counts.set(topic, (counts.get(topic) || 0) + 1);
  }));
  return counts;
}

function selectedTopics(items) {
  return [...topicCounts(items)].filter(([, count]) => count > 1).sort((a, b) => b[1] - a[1])
    .slice(0, MAX_TOPICS).map(([topic]) => topic);
}

function radial(index, total, radiusX, radiusY) {
  const angle = (index / Math.max(total, 1)) * Math.PI * 2 - Math.PI / 2;
  return { x: 500 + Math.cos(angle) * radiusX, y: 260 + Math.sin(angle) * radiusY };
}

function resourceNode(item, index, total) {
  return {
    id: `resource:${item.kind}:${item.id}`, type: item.kind, label: item.title,
    item, ...radial(index, total, 400, 205),
  };
}

function topicNode(label, index, total) {
  return {
    id: `topic:${label}`, type: "topic", label,
    ...radial(index, total, 190, 105),
  };
}

function rootNode(query) {
  return { id: "query", type: "query", label: query || "公开资源", x: 500, y: 260 };
}

function resourceLinks(resources) {
  return resources.map((node) => ({ source: "query", target: node.id, label: "检索命中" }));
}

function topicLinks(resources, topics) {
  return resources.flatMap((node) => itemTopics(node.item)
    .filter((topic) => topics.includes(topic))
    .map((topic) => ({ source: node.id, target: `topic:${topic}`, label: "共同主题" })));
}

export function buildSearchGraph(query, items) {
  const visible = items.slice(0, MAX_RESOURCES);
  const topics = selectedTopics(visible);
  const resources = visible.map((item, index) => resourceNode(item, index, visible.length));
  const topicNodes = topics.map((topic, index) => topicNode(topic, index, topics.length));
  return {
    nodes: [rootNode(query), ...topicNodes, ...resources],
    links: [...resourceLinks(resources), ...topicLinks(resources, topics)],
    shown: visible.length, total: items.length,
  };
}
