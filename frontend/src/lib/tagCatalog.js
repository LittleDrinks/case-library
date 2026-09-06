export function tagIndex(catalog) {
  return new Map(catalog.flatMap(group => group.tags.map(tag => [tag.id, {
    name: tag.name, groupId: group.id, groupName: group.name,
  }])));
}

export function tagLabel(catalog, id) {
  return tagIndex(catalog).get(id)?.name || id;
}

export function catalogSections(catalog, facetRows, selectedIds) {
  const counts = new Map((facetRows || []).map(row => [row.value, row.count]));
  const selected = new Set(selectedIds);
  return catalog.map(group => ({
    id: group.id,
    name: group.name,
    required: group.requiredForSubmission,
    options: group.tags.map(tag => ({
      value: tag.id,
      label: tag.name,
      count: counts.get(tag.id) || 0,
      selected: selected.has(tag.id),
    })),
  }));
}
