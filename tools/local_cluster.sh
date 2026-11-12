#!/usr/bin/env bash
# Local PARCS cluster in Docker (master + N workers) — same image and
# PARCS_ARGS as on Google Cloud. Handy for debugging before spending credits.
#
#   bash tools/local_cluster.sh up 4     # web UI: http://localhost:8080
#   bash tools/local_cluster.sh down
set -e
IMAGE=hummer12007/parcs-node
NET=parcsnet
MASTER_IP=172.28.0.2
N=${2:-4}

case "$1" in
  up)
    docker network create --subnet 172.28.0.0/24 $NET >/dev/null 2>&1 || true
    docker run -d --name master --network $NET --ip $MASTER_IP -p 8080:8080 \
      -e PARCS_ARGS="master" $IMAGE
    sleep 5
    for i in $(seq 1 "$N"); do
      docker run -d --name worker$i --network $NET --ip 172.28.0.1$i \
        -e PARCS_ARGS="worker $MASTER_IP" $IMAGE
    done
    echo "PARCS web UI: http://localhost:8080"
    ;;
  down)
    docker rm -f master $(docker ps -a --format '{{.Names}}' | grep '^worker') 2>/dev/null || true
    docker network rm $NET 2>/dev/null || true
    ;;
  *) echo "usage: $0 up [N] | down"; exit 1 ;;
esac
