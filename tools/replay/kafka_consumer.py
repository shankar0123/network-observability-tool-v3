#!/usr/bin/env python3

import argparse
import json
import logging
from datetime import datetime

from kafka import KafkaConsumer
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_arguments():
    parser = argparse.ArgumentParser(description='Kafka Consumer to InfluxDB Replay Tool')
    parser.add_argument('--kafka-brokers', default='localhost:9092', help='Kafka brokers address (comma-separated)')
    parser.add_argument('--topics', required=True, help='Comma-separated list of Kafka topics to consume')
    parser.add_argument('--probe-id', help='Filter by probe_id')
    parser.add_argument('--metric-type', help='Filter by metric type (e.g., icmp, dns, http, mtr, bgp, agent)')
    parser.add_argument('--start-date', help='Start date for replay (ISO 8601 format, e.g., 2025-04-15T00:00:00Z)')
    parser.add_argument('--end-date', help='End date for replay (ISO 8601 format, e.g., 2025-04-16T23:59:59Z)')
    parser.add_argument('--influxdb-url', default='http://localhost:8086', help='InfluxDB URL')
    parser.add_argument('--influxdb-token', required=True, help='InfluxDB token')
    parser.add_argument('--influxdb-org', required=True, help='InfluxDB organization')
    parser.add_argument('--influxdb-bucket', default='network_metrics', help='InfluxDB bucket')
    return parser.parse_args()

def main():
    args = parse_arguments()

    kafka_brokers = args.kafka_brokers.split(',')
    topics = args.topics.split(',')
    probe_id_filter = args.probe_id
    metric_type_filter = args.metric_type
    start_date_str = args.start_date
    end_date_str = args.end_date
    influxdb_url = args.influxdb_url
    influxdb_token = args.influxdb_token
    influxdb_org = args.influxdb_org
    influxdb_bucket = args.influxdb_bucket

    start_datetime = datetime.fromisoformat(start_date_str) if start_date_str else None
    end_datetime = datetime.fromisoformat(end_date_str) if end_date_str else None

    consumer = KafkaConsumer(
        *topics,
        bootstrap_servers=kafka_brokers,
        auto_offset_reset='earliest', # Start from the beginning of topics
        enable_auto_commit=True,
        group_id='kafka-consumer-replay-group', # Consumer group for replay tool
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        consumer_timeout_ms=1000 # Timeout to check for new messages
    )

    influxdb_client = InfluxDBClient(url=influxdb_url, token=influxdb_token, org=influxdb_org)
    write_api = influxdb_client.write_api(write_options=SYNCHRONOUS)

    logging.info(f"Consuming from Kafka topics: {topics}, brokers: {kafka_brokers}")
    if probe_id_filter:
        logging.info(f"Filtering by probe_id: {probe_id_filter}")
    if metric_type_filter:
        logging.info(f"Filtering by metric_type: {metric_type_filter}")
    if start_date_str and end_date_str:
        logging.info(f"Filtering by date range: {start_date_str} to {end_date_str}")

    try:
        for message in consumer:
            metric = message.value
            headers = {header[0].decode('utf-8'): header[1].decode('utf-8') for header in message.headers} if message.headers else {}
            topic = message.topic

            # Apply filters
            if probe_id_filter and metric.get('probe_id') != probe_id_filter:
                continue
            if metric_type_filter and metric_type_filter not in topic: # Basic metric type filtering from topic name
                continue

            timestamp_str = metric.get('timestamp')
            if timestamp_str:
                metric_datetime = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00')) # Handle UTC timezone
                if start_datetime and metric_datetime < start_datetime:
                    continue
                if end_datetime and metric_datetime > end_datetime:
                    continue
                timestamp_utc = metric_datetime.utc_datetime()
            else:
                timestamp_utc = datetime.utc_now()
                logging.warning("Timestamp not found in message, using current time.")


            # Create InfluxDB Point
            point = Point(topic)
            for key, value in metric.items():
                if key not in ['timestamp', 'probe_type', 'geo_location']: # Avoid adding tags for these fields for now
                    if isinstance(value, (int, float)):
                        point.field(key, value)
                    elif value is not None:
                        point.field(key, str(value)) # Handle string values explicitly

            # Add tags from metric and headers
            if 'probe_id' in metric:
                point.tag("probe_id", metric['probe_id'])
            elif 'probe_id' in headers:
                 point.tag("probe_id", headers['probe_id'])
            if 'probe_type' in headers:
                point.tag("probe_type", headers['probe_type'])
            if 'geo_location' in headers:
                point.tag("geo_location", headers['geo_location'])


            point.time(timestamp_utc) # Use message timestamp or current time if not found

            # Write to InfluxDB
            write_api.write(bucket=influxdb_bucket, org=influxdb_org, record=point)
            logging.info(f"Replayed metric to InfluxDB: {metric} from topic {topic}")

    except KeyboardInterrupt:
        logging.info("Stopping Kafka consumer and replay tool.")
    finally:
        consumer.close()
        influxdb_client.close()
        logging.info("Kafka consumer and InfluxDB client closed.")

if __name__ == "__main__":
    main()