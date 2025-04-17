#!/bin/bash

# Run MTR Probe every 5 minutes

while true; do
  /usr/bin/env python3 /probes/mtr_probe.py --probe-id=mtr-probe-01 --location="New York" --target=8.8.8.8 --kafka-brokers=kafka:9093
  sleep 300 # 5 minutes
done