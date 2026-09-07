export function tagIndex(catalog) {
  return new Map(catalog.flatMap(group => group.tags.map(tag => [tag.id, {
    name: tag.name, groupId: group.id, groupName: group.name,
  }])));
}
