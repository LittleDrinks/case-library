# syntax=docker/dockerfile:1.7

FROM golang:1.24-bookworm AS age-client

ENV GOPROXY=https://goproxy.cn,direct
RUN GOBIN=/out CGO_ENABLED=0 go install filippo.io/age/cmd/age@v1.3.1 \
    && GOBIN=/out CGO_ENABLED=0 go install filippo.io/age/cmd/age-keygen@v1.3.1

FROM mongo:7

ADD --chmod=755 https://github.com/minio/mc/releases/download/RELEASE.2025-08-13T08-35-41Z/mc.linux-amd64.RELEASE.2025-08-13T08-35-41Z /usr/local/bin/mc
COPY --from=age-client /out/age /out/age-keygen /usr/local/bin/
COPY --chmod=755 scripts/backup-bundle-tool.sh /usr/local/bin/backup-bundle-tool
COPY scripts/backup-manifest.jq /usr/local/share/backup-manifest.jq

ENTRYPOINT ["/usr/local/bin/backup-bundle-tool"]
