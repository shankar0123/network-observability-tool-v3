#!/bin/bash

# Run ICMP Probe every minute

while true; do
  /usr/bin/env python3 /probes/icmp_probe.py --probe-id=icmp-probe-01 --location="New York" --target=8.8.8.8 --kafka-brokers=kafka:9093
  sleep 60
done