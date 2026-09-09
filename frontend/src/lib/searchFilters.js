import { tagIndex } from "./tagCatalog.js";

export const GROUPS = {
  type: { title: "案例类型", parameter: "typeName" },
  audience: { title: "学段", parameter: "audience" },
  authority: { title: "信源等级", parameter: "authority" },
  materialType: { title: "类型", parameter: "materialType" },
  tags: { title: "标签", parameter: "tag" },
  time: { title: "更新时间", parameter: "publishedWithin" },
};

export const GROUPS_BY_KIND = {
  all: ["time"],
  case: ["type", "audience", "time"],
  knowledge: [],
  material: ["authority", "materialType", "tags", "time"],
};

export const TAG_KINDS = ["all", "case"];
export const TAG_MODES = [
  { value: "all", label: "全部符合（AND）" },
  { value: "any", label: "任一符合（OR）" },
];

const LABELS = {
  grad: "研究生", ug: "本科", embed: "专业课融入",
  original: "原始权威来源", secondary: "可靠二手来源", pending: "待核验线索",
  "7d": "一周内", "30d": "一月内", "365d": "一年内",
};

export function emptyFilters() {
  return {
    type: [], audience: [], authority: [], materialType: [], tags: [], time: "",
    tagIds: [], tagMode: "all",
  };
}

export function filterLabel(value) {
  return LABELS[value] || value;
}

function queryValues(query, name) {
  const value = query[name];
  return (Array.isArray(value) ? value : [value]).filter(item => typeof item === "string" && item);
}

function tagFiltersFromQuery(query) {
  return {
    tagIds: queryValues(query, "tagIds").slice(0, 20),
    tagMode: query.tagMode === "any" ? "any" : "all",
  };
}

export function filtersFromQuery(query, kind) {
  const filters = emptyFilters();
  GROUPS_BY_KIND[kind].forEach((group) => {
    const values = queryValues(query, GROUPS[group].parameter);
    filters[group] = group === "time" ? values[0] || "" : values;
  });
  if (TAG_KINDS.includes(kind)) Object.assign(filters, tagFiltersFromQuery(query));
  return filters;
}

function selectedValues(filters, group) {
  return group === "time" ? [filters.time].filter(Boolean) : filters[group];
}

function tagQuery(filters, kind) {
  if (!TAG_KINDS.includes(kind) || !filters.tagIds?.length) return {};
  const query = { tagIds: filters.tagIds };
  if (filters.tagMode === "any") query.tagMode = "any";
  return query;
}

export function filterQuery(filters, kind) {
  return {
    ...Object.fromEntries(GROUPS_BY_KIND[kind].flatMap((group) => {
      const values = selectedValues(filters, group);
      return values.length ? [[GROUPS[group].parameter, group === "time" ? values[0] : values]] : [];
    })),
    ...tagQuery(filters, kind),
  };
}

function facetRows(facets, group) {
  return facets[GROUPS[group].parameter] || [];
}

function options(facets, filters, group) {
  const rows = facetRows(facets, group);
  const known = new Set(rows.map(row => row.value));
  return [...rows, ...selectedValues(filters, group)
    .filter(value => !known.has(value)).map(value => ({ value, count: 0 }))];
}

export function facetGroups(facets, filters, kind) {
  return GROUPS_BY_KIND[kind].map((key) => ({
    key, title: GROUPS[key].title,
    options: options(facets, filters, key).map(row => ({
      ...row, label: filterLabel(row.value),
    })),
  })).filter(group => group.options.length);
}

export function tagCounts(facets) {
  return new Map((facets.tagCatalog || []).map(row => [row.value, row.count]));
}

export function selected(filters, group, value) {
  if (group === "tagCatalog") return (filters.tagIds || []).includes(value);
  return group === "time" ? filters.time === value : filters[group].includes(value);
}

function updateTagIds(filters, value, checked) {
  const current = filters.tagIds || [];
  const tagIds = checked
    ? [...new Set([...current, value])].slice(0, 20)
    : current.filter(item => item !== value);
  return { ...filters, tagIds };
}

export function updateFilter(filters, group, value, checked) {
  if (group === "tagCatalog") return updateTagIds(filters, value, checked);
  if (group === "time") return { ...filters, time: checked ? value : "" };
  const values = checked
    ? [...new Set([...filters[group], value])]
    : filters[group].filter(item => item !== value);
  return { ...filters, [group]: values };
}

export function updateTagMode(filters, mode) {
  return { ...filters, tagMode: mode === "any" ? "any" : "all" };
}

export function filterChips(filters, kind, catalog = []) {
  const names = tagIndex(catalog);
  const tagChips = (filters.tagIds || []).map(value => ({
    group: "tagCatalog", value, label: names.get(value)?.name || value,
  }));
  const facetChips = GROUPS_BY_KIND[kind].flatMap(group => (
    selectedValues(filters, group).map(value => ({
      group, value, label: filterLabel(value),
    }))
  ));
  return [...tagChips, ...facetChips];
}
