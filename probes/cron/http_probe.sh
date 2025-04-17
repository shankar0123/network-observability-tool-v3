#!/bin/bash

# Run HTTP Probe every minute

while true; do
  /usr/bin/env python3 /probes/http_probe.py --probe-id=http-probe-01 --location="New York" --url=http://google.com --kafka-brokers=kafka:9093
  sleep 60
done
