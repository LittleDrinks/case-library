# syntax=docker/dockerfile:1.7

FROM alpine:3.22

RUN apk add --no-cache ca-certificates curl
ADD --chmod=755 https://github.com/minio/minio/releases/download/RELEASE.2025-09-07T16-13-09Z/minio.linux-amd64.RELEASE.2025-09-07T16-13-09Z /usr/local/bin/minio

ENTRYPOINT ["minio"]
