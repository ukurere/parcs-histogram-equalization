#!/bin/bash
# Startup script for the PARCS master VM (Container-Optimized OS).
# --net=host: the web UI listens on the VM's port 8080 and workers reach the master by its VM IP.
# COS has its own host firewall (iptables) that accepts only SSH by default:
# open the web UI port and all traffic from the VPC (worker registration, Pyro RPC).
iptables -C INPUT -p tcp --dport 8080 -j ACCEPT 2>/dev/null || iptables -A INPUT -p tcp --dport 8080 -j ACCEPT
iptables -C INPUT -s 10.128.0.0/9 -j ACCEPT 2>/dev/null || iptables -A INPUT -s 10.128.0.0/9 -j ACCEPT
docker rm -f parcs 2>/dev/null
docker run -d --name parcs --restart=always --net=host \
  -e PARCS_ARGS="master" hummer12007/parcs-node
