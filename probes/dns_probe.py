#!/usr/bin/env python3

import argparse
import json
import logging
import time
import datetime
import dns.resolver
import sys

from kafka import KafkaProducer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_arguments():
    parser = argparse.ArgumentParser(description='DNS Resolver Probe')
    parser.add_argument('--resolver', required=True, help='DNS resolver to query (IP address or hostname)')
    parser.add_argument('--query', default='google.com', help='DNS query to resolve')
    parser.add_argument('--probe-id', required=True, help='Unique ID for this probe instance')
    parser.add_argument('--location', required=True, help='Geographic location of the probe')
    parser.add_argument('--kafka-brokers', default='localhost:9092', help='Kafka brokers address (comma-separated)')
    parser.add_argument('--health-check', action='store_true', help='Run health check and print output')
    return parser.parse_args()

def get_timestamp():
    return datetime.datetime.utcnow().isoformat() + 'Z'

def resolve_dns(resolver_address, query_name):
    try:
        resolver = dns.resolver.Resolver()
        resolver.nameservers = [resolver_address]
        start_time = time.time()
        answers = resolver.resolve(query_name, 'A') # Resolve A records
        response_time_ms = (time.time() - start_time) * 1000
        ip_addresses = [answer.address for answer in answers]
        return {
            'response_time_ms': response_time_ms,
            'ip_addresses': ip_addresses,
            'status': 0, # 0 for success
            'error': None
        }
    except dns.resolver.NXDOMAIN:
        return {
            'response_time_ms': None,
            'ip_addresses': None,
            'status': 1, # 1 for NXDOMAIN error
            'error': 'NXDOMAIN'
        }
    except dns.resolver.Timeout:
        return {
            'response_time_ms': None,
            'ip_addresses': None,
            'status': 2, # 2 for Timeout error
            'error': 'Timeout'
        }
    except Exception as e:
        return {
            'response_time_ms': None,
            'ip_addresses': None,
            'status': 3, # 3 for other errors
            'error': str(e)
        }

def publish_to_kafka(metrics, kafka_brokers, probe_id, location):
    try:
        producer = KafkaProducer(
            bootstrap_servers=kafka_brokers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        topic = 'dns.metrics'
        headers = [
            ('probe_id', probe_id.encode('utf-8')),
            ('probe_type', 'dns_probe'.encode('utf-8')),
            ('geo_location', location.encode('utf-8')),
        ]
        producer.send(topic, value=metrics, headers=headers)
        producer.flush()
        producer.close()
        logging.info(f"Published to Kafka topic '{topic}': {metrics}")
        return True
    except Exception as e:
        logging.error(f"Error publishing to Kafka: {e}")
        return False

def health_check(resolver_address, query_name, probe_id, location):
    logging.info("Running health check...")
    dns_result = resolve_dns(resolver_address, query_name)
    if dns_result['status'] == 0:
        print("DNS Probe Health Check: PASSED")
        print(f"  Resolver: {resolver_address}")
        print(f"  Query: {query_name}")
        print(f"  Probe ID: {probe_id}")
        print(f"  Location: {location}")
        print(f"  Timestamp: {get_timestamp()}")
        print(f"  Response Time: {dns_result['response_time_ms']:.2f} ms")
        print(f"  Resolved IPs: {dns_result['ip_addresses']}")
    else:
        print("DNS Probe Health Check: FAILED")
        print(f"  Resolver: {resolver_address}")
        print(f"  Query: {query_name}")
        print(f"  Probe ID: {probe_id}")
        print(f"  Location: {location}")
        print(f"  Timestamp: {get_timestamp()}")
        print(f"  Status Code: {dns_result['status']}")
        print(f"  Error: {dns_result['error']}")
    return dns_result['status'] == 0

def main():
    args = parse_arguments()

    if args.health_check:
        health_check(args.resolver, args.query, args.probe_id, args.location)
        sys.exit(0)

    resolver_address = args.resolver
    query_name = args.query
    probe_id = args.probe_id
    location = args.location
    kafka_brokers = args.kafka_brokers.split(',')

    logging.info(f"Starting DNS probe for resolver: {resolver_address}, query: {query_name}, probe_id: {probe_id}, location: {location}")

    while True:
        start_time = time.time()
        timestamp = get_timestamp()
        dns_result = resolve_dns(resolver_address, query_name)

        metrics = {
            'probe_id': probe_id,
            'probe_type': 'dns_probe',
            'geo_location': location,
            'timestamp': timestamp,
            'resolver': resolver_address,
            'query': query_name,
            'response_time_ms': dns_result['response_time_ms'],
            'status': dns_result['status'],
            'error': dns_result['error']
        }
        publish_to_kafka(metrics, kafka_brokers, probe_id, location)

        end_time = time.time()
        elapsed_time = end_time - start_time
        interval = 60  # Probe interval in seconds
        sleep_duration = max(0, interval - elapsed_time)
        time.sleep(sleep_duration)

if __name__ == "__main__":
    main()