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
    parser = argparse.ArgumentParser(description='ICMP Ping Probe')
    parser.add_argument('--target', required=True, help='Target host to ping (IP address or hostname)')
    parser.add_argument('--probe-id', required=True, help='Unique ID for this probe instance')
    parser.add_argument('--location', required=True, help='Geographic location of the probe (e.g., city, country)')
    parser.add_argument('--kafka-brokers', default='localhost:9092', help='Kafka brokers address (comma-separated)')
    parser.add_argument('--health-check', action='store_true', help='Run health check and print output')
    return parser.parse_args()

def get_timestamp():
    return datetime.datetime.utcnow().isoformat() + 'Z'

def ping(target_host):
    try:
        # Use subprocess to execute the ping command
        command = ['ping', '-c', '5', '-n', '-q', target_host] # 5 packets, numeric output, quiet output
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(timeout=15)

        if process.returncode == 0:
            output = stdout.decode('utf-8')
            # Parse ping output to extract metrics (using simplified parsing for example output)
            lines = output.strip().split('\n')
            if len(lines) >= 2:
                packet_loss_line = lines[-2] # e.g., '5 packets transmitted, 5 received, 0% packet loss, min/avg/max/mdev = 0.059/0.068/0.076/0.006 ms'
                rtt_line = lines[-1] # e.g., 'rtt min/avg/max/mdev = 0.059/0.068/0.076/0.006 ms'

                loss_pct = float(packet_loss_line.split('%')[0].split(',')[-1].strip()) # Extract packet loss percentage
                avg_rtt_ms = float(rtt_line.split('/')[4]) # Extract average RTT

                return {
                    'rtt_ms': avg_rtt_ms,
                    'loss_pct': loss_pct,
                    'status': 'success'
                }
            else:
                return {
                    'rtt_ms': None,
                    'loss_pct': None,
                    'status': 'parse_error',
                    'error': 'Unexpected ping output format'
                }
        else:
            return {
                'rtt_ms': None,
                'loss_pct': 100.0, # Assume 100% loss on ping failure
                'status': 'ping_failed',
                'error': stderr.decode('utf-8').strip() if stderr else f'Ping failed with code: {process.returncode}'
            }

    except subprocess.TimeoutExpired:
        return {
            'rtt_ms': None,
            'loss_pct': 100.0,
            'status': 'timeout',
            'error': 'Ping timed out'
        }
    except Exception as e:
        return {
            'rtt_ms': None,
            'loss_pct': 100.0,
            'status': 'exception',
            'error': str(e)
        }

def publish_to_kafka(metrics, kafka_brokers, probe_id, location):
    try:
        producer = KafkaProducer(
            bootstrap_servers=kafka_brokers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        topic = 'icmp.metrics'
        headers = [
            ('probe_id', probe_id.encode('utf-8')),
            ('probe_type', 'icmp_probe'.encode('utf-8')),
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

def health_check(target_host, probe_id, location):
    logging.info("Running health check...")
    ping_result = ping(target_host)
    if ping_result['status'] == 'success':
        print("ICMP Probe Health Check: PASSED")
        print(f"  Target Host: {target_host}")
        print(f"  Probe ID: {probe_id}")
        print(f"  Location: {location}")
        print(f"  Timestamp: {get_timestamp()}")
        print(f"  Average RTT: {ping_result['rtt_ms']:.2f} ms")
        print(f"  Packet Loss: {ping_result['loss_pct']:.2f}%")
    else:
        print("ICMP Probe Health Check: FAILED")
        print(f"  Target Host: {target_host}")
        print(f"  Probe ID: {probe_id}")
        print(f"  Location: {location}")
        print(f"  Timestamp: {get_timestamp()}")
        print(f"  Status: {ping_result['status']}")
        print(f"  Error: {ping_result['error']}")
    return ping_result['status'] == 'success'

def main():
    args = parse_arguments()

    if args.health_check:
        health_check(args.target, args.probe_id, args.location)
        sys.exit(0)

    target_host = args.target
    probe_id = args.probe_id
    location = args.location
    kafka_brokers = args.kafka_brokers.split(',')

    logging.info(f"Starting ICMP probe for target: {target_host}, probe_id: {probe_id}, location: {location}")

    while True:
        start_time = time.time()
        timestamp = get_timestamp()
        ping_result = ping(target_host)

        if ping_result['status'] == 'success':
            metrics = {
                'probe_id': probe_id,
                'probe_type': 'icmp_probe',
                'geo_location': location,
                'timestamp': timestamp,
                'target': target_host,
                'rtt_ms': ping_result['rtt_ms'],
                'loss_pct': ping_result['loss_pct']
            }
            publish_to_kafka(metrics, kafka_brokers, probe_id, location)
        else:
            logging.error(f"Ping failed for target {target_host}: Status: {ping_result['status']}, Error: {ping_result['error']}")
            health_metrics = {
                'probe_id': probe_id,
                'probe_type': 'icmp_probe',
                'geo_location': location,
                'timestamp': timestamp,
                'status': ping_result['status'],
                'error': ping_result['error']
            }
            publish_to_kafka(health_metrics, kafka_brokers, probe_id, location) # Still publish health status

        end_time = time.time()
        elapsed_time = end_time - start_time
        interval = 60 # Probe interval in seconds
        sleep_duration = max(0, interval - elapsed_time)
        time.sleep(sleep_duration)

if __name__ == "__main__":
    main()