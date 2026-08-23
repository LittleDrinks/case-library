import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
} from "d3-force";

const BASE_BOUNDS = { width: 1000, height: 520 };

function cloneNode(node, bounds) {
  return {
    ...node,
    x: node.x * bounds.width / BASE_BOUNDS.width,
    y: node.y * bounds.height / BASE_BOUNDS.height,
  };
}

function nodePadding(node) {
  if (node.type === "query") return { x: 76, y: 30 };
  if (node.type === "topic") return { x: 60, y: 25 };
  return { x: 68, y: 28 };
}

function collisionRadius(node, width) {
  const mobile = width < 500;
  if (node.type === "query") return mobile ? 64 : 76;
  if (node.type === "topic") return mobile ? 52 : 60;
  return mobile ? 58 : 68;
}

function chargeStrength(node) {
  return node.type === "query" ? -920 : -480;
}

function linkDistance(link) {
  return link.label === "共同主题" ? 145 : 220;
}

function linkStrength(link) {
  return link.label === "共同主题" ? 0.34 : 0.22;
}

function clampAxis(node, axis, minimum, maximum) {
  const next = Math.max(minimum, Math.min(maximum, node[axis]));
  if (next !== node[axis]) node[`v${axis}`] = 0;
  node[axis] = next;
}

function clampNode(node, bounds) {
  const padding = nodePadding(node);
  clampAxis(node, "x", padding.x, bounds.width - padding.x);
  clampAxis(node, "y", padding.y, bounds.height - padding.y);
}

function render(context) {
  context.nodes.forEach((node) => clampNode(node, context.bounds));
  context.onTick(context.nodes, context.links, context.bounds);
}

function installForces(context) {
  const { bounds, links, nodes } = context;
  return forceSimulation(nodes)
    .force("link", forceLink(links).id((node) => node.id).distance(linkDistance).strength(linkStrength))
    .force("charge", forceManyBody().strength(chargeStrength).distanceMax(700))
    .force("collide", forceCollide((node) => collisionRadius(node, bounds.width)).iterations(3))
    .force("center", forceCenter(bounds.width / 2, bounds.height / 2))
    .force("x", forceX(bounds.width / 2).strength(0.035))
    .force("y", forceY(bounds.height / 2).strength(0.055))
    .velocityDecay(0.38).alphaDecay(0.035)
    .on("tick", () => render(context));
}

function rescaleNode(node, previous, bounds) {
  node.x = node.x * bounds.width / previous.width;
  node.y = node.y * bounds.height / previous.height;
  if (node.fx != null) node.fx = node.fx * bounds.width / previous.width;
  if (node.fy != null) node.fy = node.fy * bounds.height / previous.height;
}

function resize(context, width, height) {
  const previous = { ...context.bounds };
  Object.assign(context.bounds, { width, height });
  context.nodes.forEach((node) => rescaleNode(node, previous, context.bounds));
  context.simulation.force("center").x(width / 2).y(height / 2);
  context.simulation.force("x").x(width / 2);
  context.simulation.force("y").y(height / 2);
  context.simulation.force("collide").radius((node) => collisionRadius(node, width));
  context.simulation.alpha(0.7).restart();
  render(context);
}

function pin(context, id, x, y) {
  const node = context.nodes.find((candidate) => candidate.id === id);
  if (!node) return;
  Object.assign(node, { x, y, fx: x, fy: y });
  clampNode(node, context.bounds);
  Object.assign(node, { fx: node.x, fy: node.y });
  context.simulation.alphaTarget(0.18).restart();
  render(context);
}

function release(context, id) {
  const node = context.nodes.find((candidate) => candidate.id === id);
  if (node) Object.assign(node, { fx: null, fy: null });
  context.simulation.alphaTarget(0).alpha(0.45).restart();
}

function layoutApi(context) {
  return {
    nodes: context.nodes,
    links: context.links,
    resize: (width, height) => resize(context, width, height),
    pin: (id, x, y) => pin(context, id, x, y),
    release: (id) => release(context, id),
    stop: () => context.simulation.stop(),
  };
}

export function createForceLayout(graph, bounds, onTick) {
  const size = { ...BASE_BOUNDS, ...bounds };
  const context = {
    bounds: size,
    links: graph.links.map((link) => ({ ...link })),
    nodes: graph.nodes.map((node) => cloneNode(node, size)),
    onTick,
  };
  context.simulation = installForces(context);
  render(context);
  return layoutApi(context);
}
