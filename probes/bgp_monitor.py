#!/usr/bin/env python3

import argparse
import json
import logging
import time
import datetime
import pybgpstream
import sys

from kafka import KafkaProducer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_arguments():
    parser = argparse.ArgumentParser(description='BGP Route Monitor Probe')
    parser.add_argument('--collector', default='routeviews', help='BGP collector to use (e.g., routeviews, ris)')
    parser.add_argument('-- রশিদ-instance', default='route-views.linx', help='Collector instance (e.g., route-views.eqix, rrc00)') # Changed option name to collector-instance
    parser.add_argument('--prefix', default='0.0.0.0/0', help='Prefix to monitor (e.g., 8.8.8.0/24)')
    parser.add_argument('--probe-id', required=True, help='Unique ID for this probe instance')
    parser.add_argument('--location', required=True, help='Geographic location of the probe')
    parser.add_argument('--kafka-brokers', default='localhost:9092', help='Kafka brokers address (comma-separated)')
    parser.add_argument('--health-check', action='store_true', help='Run health check and print output')
    return parser.parse_args()

def get_timestamp():
    return datetime.datetime.utcnow().isoformat() + 'Z'

def monitor_bgp_routes(collector_name, collector_instance, prefix_filter):
    try:
        updates = []
        stream = pybgpstream.BGPStream(
            data_type="updates",
            collector=collector_name,
            collector_instance=collector_instance,
            prefix_filter=prefix_filter,
            record_interval=60 # Reduced record_interval for faster health checks
        )

        for rec in stream:
            for elem in rec:
                update_info = {
                    'prefix': str(elem.fields['prefix']),
                    'peer_asn': int(elem.peer_asn) if elem.peer_asn else None,
                    'origin_asn': int(elem.fields['as-path'].split()[-1]) if elem.fields['as-path'] else None, # Extract origin ASN from AS_PATH
                    'as_path': str(elem.fields['as-path']),
                    'next_hop': str(elem.fields['next-hop']),
                    'communities': [str(comm) for comm in elem.fields['communities']],
                    'timestamp': elem.time,
                    'type': elem.type, # 'A' for announcement, 'W' for withdrawal
                    'collector': collector_name,
                    'collector_instance': collector_instance
                }
                updates.append(update_info)
        return {
            'updates': updates,
            'status': 'success'
        }
    except Exception as e:
        return {
            'updates': None,
            'status': 'bgpstream_error',
            'error': str(e)
        }

def publish_to_kafka(metrics, kafka_brokers, probe_id, location, collector_name, collector_instance):
    try:
        producer = KafkaProducer(
            bootstrap_servers=kafka_brokers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        topic = 'bgp.updates'
        headers = [
            ('probe_id', probe_id.encode('utf-8')),
            ('probe_type', 'bgp_monitor'.encode('utf-8')),
            ('geo_location', location.encode('utf-8')),
            ('collector', collector_name.encode('utf-8')),
            ('collector_instance', collector_instance.encode('utf-8')),
        ]
        for update_metric in metrics['updates']:
            metric_value = {
                'probe_id': probe_id,
                'probe_type': 'bgp_monitor',
                'geo_location': location,
                'timestamp': get_timestamp(),
                'prefix': update_metric['prefix'],
                'origin_asn': update_metric['origin_asn'],
                'as_path': update_metric['as_path'],
                'event': update_metric['type'],
                'collector': collector_name,
                'collector_instance': collector_instance
            }
            producer.send(topic, value=metric_value, headers=headers)
        producer.flush()
        producer.close()
        logging.info(f"Published to Kafka topic '{topic}': BGP updates for collector {collector_name}, instance {collector_instance}")
        return True
    except Exception as e:
        logging.error(f"Error publishing to Kafka: {e}")
        return False


def health_check(collector_name, collector_instance, prefix_filter, probe_id, location):
    logging.info("Running health check...")
    bgp_result = monitor_bgp_routes(collector_name, collector_instance, prefix_filter)
    if bgp_result['status'] == 'success':
        print("BGP Monitor Probe Health Check: PASSED")
        print(f"  Collector: {collector_name}")
        print(f"  Instance: {collector_instance}")
        print(f"  Prefix Filter: {prefix_filter}")
        print(f"  Probe ID: {probe_id}")
        print(f"  Location: {location}")
        print(f"  Timestamp: {get_timestamp()}")
        if bgp_result['updates']:
            print("  Last BGP Update:")
            last_update = bgp_result['updates'][0] # Print only the first update for brevity
            print(f"    Prefix: {last_update['prefix']}")
            print(f"    Origin ASN: {last_update['origin_asn']}")
            print(f"    AS Path: {last_update['as_path']}")
            print(f"    Event Type: {last_update['type']}")
        else:
            print("  No BGP updates received in health check interval.")

    else:
        print("BGP Monitor Probe Health Check: FAILED")
        print(f"  Collector: {collector_name}")
        print(f"  Instance: {collector_instance}")
        print(f"  Prefix Filter: {prefix_filter}")
        print(f"  Probe ID: {probe_id}")
        print(f"  Location: {location}")
        print(f"  Timestamp: {get_timestamp()}")
        print(f"  Status: {bgp_result['status']}")
        print(f"  Error: {bgp_result['error']}")
    return bgp_result['status'] == 'success'


def main():
    args = parse_arguments()

    if args.health_check:
        health_check(args.collector, args.collector_instance, args.prefix, args.probe_id, args.location)
        sys.exit(0)

    collector_name = args.collector
    collector_instance = args.collector_instance
    prefix_filter = args.prefix
    probe_id = args.probe_id
    location = args.location
    kafka_brokers = args.kafka_brokers.split(',')

    logging.info(f"Starting BGP monitor for collector: {collector_name}, instance: {collector_instance}, prefix: {prefix_filter}, probe_id: {probe_id}, location: {location}")

    while True:
        start_time = time.time()
        timestamp = get_timestamp()
        bgp_result = monitor_bgp_routes(collector_name, collector_instance, prefix_filter)

        if bgp_result['status'] == 'success':
            if bgp_result['updates']:
                publish_to_kafka(bgp_result, kafka_brokers, probe_id, location, collector_name, collector_instance)
            else:
                logging.info("No BGP updates received in this interval.")
        else:
            logging.error(f"BGP monitor failed for collector {collector_name}, instance {collector_instance}, prefix {prefix_filter}: Status: {bgp_result['status']}, Error: {bgp_result['error']}")
            health_metrics = {
                'probe_id': probe_id,
                'probe_type': 'bgp_monitor',
                'geo_location': location,
                'timestamp': timestamp,
                'status': bgp_result['status'],
                'error': bgp_result['error']
            }
            # publish_to_kafka(health_metrics, kafka_brokers, probe_id, location, collector_name, collector_instance) # Decided not to publish health for bgp errors for now

        end_time = time.time()
        elapsed_time = end_time - start_time
        interval = 300  # BGP probe interval in seconds (5 minutes) - BGP updates are less frequent
        sleep_duration = max(0, interval - elapsed_time)
        time.sleep(sleep_duration)


if __name__ == "__main__":
    main()