#!/usr/bin/env python3

import argparse
import json
import logging
import time
import datetime
import requests
import sys

from kafka import KafkaProducer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_arguments():
    parser = argparse.ArgumentParser(description='HTTP Uptime Probe')
    parser.add_argument('--url', required=True, help='URL to check (e.g., http://google.com)')
    parser.add_argument('--probe-id', required=True, help='Unique ID for this probe instance')
    parser.add_argument('--location', required=True, help='Geographic location of the probe')
    parser.add_argument('--kafka-brokers', default='localhost:9092', help='Kafka brokers address (comma-separated)')
    parser.add_argument('--health-check', action='store_true', help='Run health check and print output')
    return parser.parse_args()

def get_timestamp():
    return datetime.datetime.utcnow().isoformat() + 'Z'

def check_http_uptime(url):
    try:
        start_time = time.time()
        response = requests.get(url, timeout=10)
        response_time_ms = (time.time() - start_time) * 1000
        return {
            'status_code': response.status_code,
            'response_time_ms': response_time_ms,
            'status': 'success',
            'error': None
        }
    except requests.exceptions.RequestException as e:
        return {
            'status_code': None,
            'response_time_ms': None,
            'status': 'request_failed',
            'error': str(e)
        }

def publish_to_kafka(metrics, kafka_brokers, probe_id, location):
    try:
        producer = KafkaProducer(
            bootstrap_servers=kafka_brokers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        topic = 'http.metrics'
        headers = [
            ('probe_id', probe_id.encode('utf-8')),
            ('probe_type', 'http_probe'.encode('utf-8')),
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

def health_check(url, probe_id, location):
    logging.info("Running health check...")
    http_result = check_http_uptime(url)
    if http_result['status'] == 'success':
        print("HTTP Probe Health Check: PASSED")
        print(f"  URL: {url}")
        print(f"  Probe ID: {probe_id}")
        print(f"  Location: {location}")
        print(f"  Timestamp: {get_timestamp()}")
        print(f"  Status Code: {http_result['status_code']}")
        print(f"  Response Time: {http_result['response_time_ms']:.2f} ms")
    else:
        print("HTTP Probe Health Check: FAILED")
        print(f"  URL: {url}")
        print(f"  Probe ID: {probe_id}")
        print(f"  Location: {location}")
        print(f"  Timestamp: {get_timestamp()}")
        print(f"  Status: {http_result['status']}")
        print(f"  Error: {http_result['error']}")
    return http_result['status'] == 'success'

def main():
    args = parse_arguments()

    if args.health_check:
        health_check(args.url, args.probe_id, args.location)
        sys.exit(0)

    url = args.url
    probe_id = args.probe_id
    location = args.location
    kafka_brokers = args.kafka_brokers.split(',')

    logging.info(f"Starting HTTP probe for URL: {url}, probe_id: {probe_id}, location: {location}")

    while True:
        start_time = time.time()
        timestamp = get_timestamp()
        http_result = check_http_uptime(url)

        metrics = {
            'probe_id': probe_id,
            'probe_type': 'http_probe',
            'geo_location': location,
            'timestamp': timestamp,
            'url': url,
            'status_code': http_result['status_code'],
            'response_time_ms': http_result['response_time_ms'],
            'status': http_result['status'],
            'error': http_result['error']
        }
        publish_to_kafka(metrics, kafka_brokers, probe_id, location)

        end_time = time.time()
        elapsed_time = end_time - start_time
        interval = 60  # Probe interval in seconds
        sleep_duration = max(0, interval - elapsed_time)
        time.sleep(sleep_duration)

if __name__ == "__main__":
    main()