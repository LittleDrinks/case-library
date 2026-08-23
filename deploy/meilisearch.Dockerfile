FROM getmeili/meilisearch:v1.45.1

COPY --chmod=755 deploy/meilisearch-entrypoint.sh /usr/local/bin/meilisearch-secret-entrypoint
ENTRYPOINT ["meilisearch-secret-entrypoint"]
