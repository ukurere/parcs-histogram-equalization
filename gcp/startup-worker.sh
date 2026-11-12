#!/bin/bash
# Startup script for a PARCS worker VM (Container-Optimized OS).
# Master's internal IP is read from instance metadata key "parcs-master-ip".
MASTER_IP=$(curl -s -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/attributes/parcs-master-ip")
# COS host firewall accepts only SSH by default: allow all traffic from the VPC
# (master -> worker HTTP API on a random port, Pyro RPC on random ports).
iptables -C INPUT -s 10.128.0.0/9 -j ACCEPT 2>/dev/null || iptables -A INPUT -s 10.128.0.0/9 -j ACCEPT
# --net=host: generate_config.sh registers the worker on the master with `hostname -I`,
# so the container must see the VM's real internal IP.
docker rm -f parcs 2>/dev/null
docker run -d --name parcs --restart=always --net=host \
  -e PARCS_ARGS="worker ${MASTER_IP}" hummer12007/parcs-node
