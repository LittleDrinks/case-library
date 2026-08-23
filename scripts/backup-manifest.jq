{
  formatVersion: 1,
  createdAt: $created_at,
  gitSha: $git_sha,
  gitDirty: $git_dirty,
  appImageId: $app_image_id,
  database: {
    name: $database,
    archive: "mongo.archive.gz",
    sha256: $mongo_sha,
    collections: $inventory[0].collections
  },
  objectStore: {
    bucket: $bucket,
    count: $object_count,
    hashes: "objects.sha256",
    hashListSha256: $object_hashes_sha
  },
  referencedObjectKeys: $inventory[0].referencedObjectKeys
}
