#!/usr/bin/env python3

import argparse
import json
import logging
import time
import datetime
import socket
import subprocess
import sys

from kafka import KafkaProducer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_arguments():
    parser = argparse.ArgumentParser(description='Agent Registry Updater')
    parser.add_argument('--probe-id', required=True, help='Unique ID for this probe instance')
    parser.add_argument('--location', required=True, help='Geographic location of the probe')
    parser.add_argument('--kafka-brokers', default='localhost:9092', help='Kafka brokers address (comma-separated)')
    parser.add_argument('--available-metrics', default='icmp,dns,http,mtr,bgp', help='Comma-separated list of available metrics for this agent')
    parser.add_argument('--version', default='1.0.0', help='Agent version')
    parser.add_argument('--health-check', action='store_true', help='Run health check and print output')
    return parser.parse_args()

def get_timestamp():
    return datetime.datetime.utcnow().isoformat() + 'Z'

def get_uptime():
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
            return int(uptime_seconds)
    except Exception:
        return None

def get_ip_address():
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return None

def publish_to_kafka(registry_info, kafka_brokers, probe_id, location):
    try:
        producer = KafkaProducer(
            bootstrap_servers=kafka_brokers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        topic = 'agent.registry'
        headers = [
            ('probe_id', probe_id.encode('utf-8')),
            ('probe_type', 'registry_updater'.encode('utf-8')),
            ('geo_location', location.encode('utf-8')),
        ]
        producer.send(topic, value=registry_info, headers=headers)
        producer.flush()
        producer.close()
        logging.info(f"Published to Kafka topic '{topic}': {registry_info}")
        return True
    except Exception as e:
        logging.error(f"Error publishing to Kafka: {e}")
        return False

def health_check(probe_id, location, available_metrics, version):
    logging.info("Running health check...")
    registry_info = {
        'probe_id': probe_id,
        'probe_type': 'registry_updater',
        'geo_location': location,
        'timestamp': get_timestamp(),
        'ip': get_ip_address(),
        'available_metrics': available_metrics.split(','),
        'version': version,
        'uptime': get_uptime()
    }
    print("Agent Registry Updater Health Check: OUTPUT") # Always output for registry updater health check
    print(json.dumps(registry_info, indent=2))
    return True # Always return true for registry updater health check as long as it runs

def main():
    args = parse_arguments()

    if args.health_check:
        health_check(args.probe_id, args.location, args.available_metrics, args.version)
        sys.exit(0)

    probe_id = args.probe_id
    location = args.location
    kafka_brokers = args.kafka_brokers.split(',')
    available_metrics = args.available_metrics
    version = args.version

    logging.info(f"Starting Agent Registry Updater for probe_id: {probe_id}, location: {location}")

    registry_info = {
        'probe_id': probe_id,
        'probe_type': 'registry_updater',
        'geo_location': location,
        'timestamp': get_timestamp(),
        'ip': get_ip_address(),
        'available_metrics': available_metrics.split(','),
        'version': version,
        'uptime': get_uptime()
    }
    publish_to_kafka(registry_info, kafka_brokers, probe_id, location)
    logging.info("Agent registry information published to Kafka. Exiting.")

if __name__ == "__main__":
    main()