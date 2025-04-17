#!/bin/bash

# Run Registry Updater on boot (one-time execution)

/usr/bin/env python3 /probes/registry_updater.py --probe-id=agent-registry-01 --location="New York" --kafka-brokers=kafka:9093 --available-metrics=icmp,dns,http,mtr,bgp --version=1.0.0