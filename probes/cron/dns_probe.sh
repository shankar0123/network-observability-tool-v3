#!/bin/bash

# Run DNS Probe every minute

while true; do
  /usr/bin/env python3 /probes/dns_probe.py --probe-id=dns-probe-01 --location="New York" --resolver=8.8.8.8 --query=google.com --kafka-brokers=kafka:9093
  sleep 60
done