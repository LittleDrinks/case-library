FROM mongo:7

COPY scripts/mongo-init.sh /usr/local/bin/mongo-init
ENTRYPOINT ["mongo-init"]
