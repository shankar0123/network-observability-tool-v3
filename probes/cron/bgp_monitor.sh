#!/bin/bash

# Run BGP Monitor Probe every 5 minutes

while true; do
  /usr/bin/env python3 /probes/bgp_monitor.py --probe-id=bgp-monitor-01 --location="New York" --collector=routeviews --collector-instance=route-views.linx --prefix=0.0.0.0/0 --kafka-brokers=kafka:9093
  sleep 300 # 5 minutes
done