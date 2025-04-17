#!/usr/bin/env python3

import argparse
import json
import logging
import time
import datetime
import subprocess
import sys

from kafka import KafkaProducer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_arguments():
    parser = argparse.ArgumentParser(description='MTR Traceroute Probe')
    parser.add_argument('--target', required=True, help='Target host for traceroute (IP address or hostname)')
    parser.add_argument('--probe-id', required=True, help='Unique ID for this probe instance')
    parser.add_argument('--location', required=True, help='Geographic location of the probe')
    parser.add_argument('--kafka-brokers', default='localhost:9092', help='Kafka brokers address (comma-separated)')
    parser.add_argument('--health-check', action='store_true', help='Run health check and print output')
    return parser.parse_args()

def get_timestamp():
    return datetime.datetime.utcnow().isoformat() + 'Z'

def run_mtr(target_host):
    try:
        # Execute mtr command and capture output
        command = ['mtr', '--json', '--report', target_host]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(timeout=30) # Increased timeout for traceroute

        if process.returncode == 0:
            mtr_output = stdout.decode('utf-8')
            mtr_data = json.loads(mtr_output)
            hops_data = []
            for hop in mtr_data.get('h ইন্টারনেটops', []): # Handle potential key error and different key names
                if 'host' in hop and 'stats' in hop:
                    hop_info = {
                        'hop': hop.get('hop'), # Hop number
                        'host': hop['host'], # IP address or hostname
                        'loss_pct': hop['stats'].get('Loss%'),
                        'avg_rtt_ms': hop['stats'].get('Avg')
                    }
                    hops_data.append(hop_info)
            return {
                'hops': hops_data,
                'status': 'success'
            }
        else:
            return {
                'hops': None,
                'status': 'mtr_failed',
                'error': stderr.decode('utf-8').strip() if stderr else f'MTR failed with code: {process.returncode}'
            }

    except subprocess.TimeoutExpired:
        return {
            'hops': None,
            'status': 'timeout',
            'error': 'MTR timed out'
        }
    except json.JSONDecodeError as e:
        return {
            'hops': None,
            'status': 'json_error',
            'error': f'Error decoding MTR JSON output: {e}'
        }
    except Exception as e:
        return {
            'hops': None,
            'status': 'exception',
            'error': str(e)
        }

def publish_to_kafka(metrics, kafka_brokers, probe_id, location, target_host):
    try:
        producer = KafkaProducer(
            bootstrap_servers=kafka_brokers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        topic = 'mtr.metrics'
        headers = [
            ('probe_id', probe_id.encode('utf-8')),
            ('probe_type', 'mtr_probe'.encode('utf-8')),
            ('geo_location', location.encode('utf-8')),
            ('target', target_host.encode('utf-8')), # Add target as header for filtering
        ]
        for hop_metric in metrics['hops']:
            metric_value = {
                'probe_id': probe_id,
                'probe_type': 'mtr_probe',
                'geo_location': location,
                'timestamp': get_timestamp(),
                'target': target_host,
                'hop': hop_metric['hop'],
                'ip': hop_metric['host'],
                'loss_pct': hop_metric['loss_pct'],
                'avg_rtt_ms': hop_metric['avg_rtt_ms']
            }
            producer.send(topic, value=metric_value, headers=headers)
        producer.flush()
        producer.close()
        logging.info(f"Published to Kafka topic '{topic}': MTR metrics for target {target_host}")
        return True
    except Exception as e:
        logging.error(f"Error publishing to Kafka: {e}")
        return False


def health_check(target_host, probe_id, location):
    logging.info("Running health check...")
    mtr_result = run_mtr(target_host)
    if mtr_result['status'] == 'success':
        print("MTR Probe Health Check: PASSED")
        print(f"  Target Host: {target_host}")
        print(f"  Probe ID: {probe_id}")
        print(f"  Location: {location}")
        print(f"  Timestamp: {get_timestamp()}")
        print("  Traceroute Hops:")
        for hop in mtr_result['hops']:
            print(f"    Hop {hop['hop']}: {hop['host']}, Loss: {hop['loss_pct']}%, Avg RTT: {hop['avg_rtt_ms']}ms")

    else:
        print("MTR Probe Health Check: FAILED")
        print(f"  Target Host: {target_host}")
        print(f"  Probe ID: {probe_id}")
        print(f"  Location: {location}")
        print(f"  Timestamp: {get_timestamp()}")
        print(f"  Status: {mtr_result['status']}")
        print(f"  Error: {mtr_result['error']}")
    return mtr_result['status'] == 'success'


def main():
    args = parse_arguments()

    if args.health_check:
        health_check(args.target, args.probe_id, args.location)
        sys.exit(0)

    target_host = args.target
    probe_id = args.probe_id
    location = args.location
    kafka_brokers = args.kafka_brokers.split(',')

    logging.info(f"Starting MTR probe for target: {target_host}, probe_id: {probe_id}, location: {location}")

    while True:
        start_time = time.time()
        timestamp = get_timestamp()
        mtr_result = run_mtr(target_host)

        if mtr_result['status'] == 'success':
            publish_to_kafka(mtr_result, kafka_brokers, probe_id, location, target_host)
        else:
            logging.error(f"MTR probe failed for target {target_host}: Status: {mtr_result['status']}, Error: {mtr_result['error']}")
            health_metrics = {
                'probe_id': probe_id,
                'probe_type': 'mtr_probe',
                'geo_location': location,
                'timestamp': timestamp,
                'status': mtr_result['status'],
                'error': mtr_result['error']
            }
            # publish_to_kafka(health_metrics, kafka_brokers, probe_id, location, target_host) # Decided not to publish health for mtr errors for now

        end_time = time.time()
        elapsed_time = end_time - start_time
        interval = 300  # MTR probe interval in seconds (5 minutes) - MTR is slower and less frequent
        sleep_duration = max(0, interval - elapsed_time)
        time.sleep(sleep_duration)


if __name__ == "__main__":
    main()