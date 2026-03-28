"""
Prometheus Metrics Fetcher

This module provides utilities to fetch metrics from Prometheus at regular intervals
and store them for further processing (e.g., machine learning).

Features:
- Fetch multiple metrics at configurable intervals
- Handle Prometheus API errors gracefully
- Store metrics with timestamps
- Support for instantaneous and range queries
- Rate limiting to avoid overwhelming Prometheus
"""

import requests
import time
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    """Represents a single metric measurement at a point in time"""
    timestamp: float
    metric_name: str
    metric_labels: Dict[str, str]
    value: float
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


class PrometheusClient:
    """Client for querying Prometheus API"""
    
    def __init__(self, prometheus_url: str = "http://localhost:9090"):
        """
        Initialize Prometheus client
        
        Args:
            prometheus_url: Base URL of Prometheus server
        """
        self.prometheus_url = prometheus_url
        self.query_endpoint = f"{prometheus_url}/api/v1/query"
        self.query_range_endpoint = f"{prometheus_url}/api/v1/query_range"
        self.timeout = 10  # seconds
        
    def is_healthy(self) -> bool:
        """Check if Prometheus is accessible"""
        try:
            response = requests.get(
                f"{self.prometheus_url}/-/healthy",
                timeout=self.timeout
            )
            return response.status_code == 200
        except requests.RequestException as e:
            logger.error(f"Prometheus health check failed: {e}")
            return False
    
    def instant_query(self, query: str) -> List[Dict[str, Any]]:
        """
        Execute instant query (current value)
        
        Args:
            query: PromQL query string
            
        Returns:
            List of metric results
        """
        try:
            response = requests.get(
                self.query_endpoint,
                params={"query": query},
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") != "success":
                logger.error(f"Query failed: {data.get('error')}")
                return []
            
            return data.get("data", {}).get("result", [])
        
        except requests.RequestException as e:
            logger.error(f"Query '{query}' failed: {e}")
            return []
    
    def range_query(
        self,
        query: str,
        start_time: float,
        end_time: float,
        step: str = "5s"
    ) -> List[Dict[str, Any]]:
        """
        Execute range query (time series data)
        
        Args:
            query: PromQL query string
            start_time: Start timestamp (unix epoch)
            end_time: End timestamp (unix epoch)
            step: Query resolution step (e.g., "5s", "1m")
            
        Returns:
            List of metric results with time series data
        """
        try:
            response = requests.get(
                self.query_range_endpoint,
                params={
                    "query": query,
                    "start": int(start_time),
                    "end": int(end_time),
                    "step": step
                },
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") != "success":
                logger.error(f"Range query failed: {data.get('error')}")
                return []
            
            return data.get("data", {}).get("result", [])
        
        except requests.RequestException as e:
            logger.error(f"Range query '{query}' failed: {e}")
            return []
    
    def parse_result(self, result: Dict[str, Any]) -> Optional[MetricPoint]:
        """
        Parse a single metric result into MetricPoint
        
        Args:
            result: Single result from Prometheus API
            
        Returns:
            MetricPoint or None if parsing fails
        """
        try:
            metric_labels = result.get("metric", {})
            metric_name = metric_labels.pop("__name__", "unknown")
            
            # For instant queries, value is [timestamp, value]
            value_data = result.get("value", [None, None])
            
            if value_data[0] is None or value_data[1] is None:
                return None
            
            timestamp = float(value_data[0])
            value = float(value_data[1])
            
            return MetricPoint(
                timestamp=timestamp,
                metric_name=metric_name,
                metric_labels=metric_labels,
                value=value
            )
        except (ValueError, KeyError, TypeError) as e:
            logger.error(f"Failed to parse metric result: {e}")
            return None


class MetricsCollector:
    """Collects metrics from Prometheus at regular intervals"""
    
    def __init__(
        self,
        prometheus_url: str = "http://localhost:9090",
        output_dir: str = "./data/metrics",
        interval_seconds: int = 5
    ):
        """
        Initialize metrics collector
        
        Args:
            prometheus_url: Prometheus server URL
            output_dir: Directory to store collected metrics
            interval_seconds: Collection interval in seconds
        """
        self.client = PrometheusClient(prometheus_url)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.interval_seconds = interval_seconds
        self.is_running = False
        
        # Default metrics to collect
        self.metric_queries = {
            # Chaos modes
            "chaos_mode": "chaos_mode",
            
            # HTTP metrics
            "http_requests_total": "rate(http_requests_total[1m])",
            "http_request_latency_p50": "histogram_quantile(0.50, rate(http_request_latency_seconds_bucket[1m]))",
            "http_request_latency_p95": "histogram_quantile(0.95, rate(http_request_latency_seconds_bucket[1m]))",
            "http_request_latency_p99": "histogram_quantile(0.99, rate(http_request_latency_seconds_bucket[1m]))",
            "http_error_rate": "sum(rate(http_requests_total{code=~\"[45]..\"}[1m])) / sum(rate(http_requests_total[1m]))",
            
            # Resource metrics
            "leak_mb": "leak_mb",
            "open_fds_simulated": "open_fds_simulated",
            "disk_fill_mb": "disk_fill_mb",
            "db_inflight": "db_inflight",
            
            # Container metrics (CPU)
            "container_cpu_rate": "rate(container_cpu_usage_seconds_total[1m])",
            
            # Container metrics (Memory)
            "container_memory_mb": "container_memory_usage_bytes / 1024 / 1024",
            
            # Retry metrics
            "retry_calls_rate": "rate(retry_calls_total[1m])",
            "retry_calls_ok_rate": "rate(retry_calls_total{result=\"ok\"}[1m])",
            "retry_calls_failed_rate": "rate(retry_calls_total{result=\"failed\"}[1m])",
        }
    
    def add_metric(self, name: str, query: str) -> None:
        """
        Add a custom metric to collect
        
        Args:
            name: Friendly name for the metric
            query: PromQL query string
        """
        self.metric_queries[name] = query
        logger.info(f"Added metric: {name}")
    
    def remove_metric(self, name: str) -> None:
        """Remove a metric from collection"""
        if name in self.metric_queries:
            del self.metric_queries[name]
            logger.info(f"Removed metric: {name}")
    
    def collect_once(self) -> Dict[str, List[MetricPoint]]:
        """
        Collect all metrics once
        
        Returns:
            Dictionary mapping metric names to lists of MetricPoints
        """
        if not self.client.is_healthy():
            logger.error("Prometheus is not accessible")
            return {}
        
        collected_metrics = {}
        
        for metric_name, query in self.metric_queries.items():
            logger.debug(f"Collecting metric: {metric_name}")
            results = self.client.instant_query(query)
            
            metric_points = []
            for result in results:
                point = self.client.parse_result(result)
                if point:
                    point.metric_name = metric_name
                    metric_points.append(point)
            
            collected_metrics[metric_name] = metric_points
            logger.info(f"Collected {len(metric_points)} data points for {metric_name}")
        
        return collected_metrics
    
    def save_metrics(
        self,
        metrics: Dict[str, List[MetricPoint]],
        filename: Optional[str] = None
    ) -> Path:
        """
        Save collected metrics to file
        
        Args:
            metrics: Dictionary of collected metrics
            filename: Output filename (auto-generated if None)
            
        Returns:
            Path to saved file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"metrics_{timestamp}.jsonl"
        
        filepath = self.output_dir / filename
        
        with open(filepath, "w") as f:
            for metric_name, metric_points in metrics.items():
                for point in metric_points:
                    # Store as JSONL (one JSON object per line)
                    f.write(json.dumps({
                        "metric_name": point.metric_name,
                        "timestamp": point.timestamp,
                        "labels": point.metric_labels,
                        "value": point.value,
                        "collected_at": datetime.now().isoformat()
                    }) + "\n")
        
        logger.info(f"Saved metrics to {filepath}")
        return filepath
    
    def collect_and_save(self) -> Path:
        """
        Collect metrics once and save to file
        
        Returns:
            Path to saved metrics file
        """
        metrics = self.collect_once()
        return self.save_metrics(metrics)
    
    def get_metrics_summary(self, metrics: Dict[str, List[MetricPoint]]) -> Dict[str, Any]:
        """
        Generate a summary of collected metrics
        
        Args:
            metrics: Dictionary of collected metrics
            
        Returns:
            Summary statistics
        """
        summary = {
            "timestamp": datetime.now().isoformat(),
            "total_metrics_collected": len(metrics),
            "metrics": {}
        }
        
        for metric_name, metric_points in metrics.items():
            if metric_points:
                values = [p.value for p in metric_points]
                summary["metrics"][metric_name] = {
                    "count": len(values),
                    "current": values[-1] if values else None,
                    "min": min(values),
                    "max": max(values),
                    "avg": sum(values) / len(values),
                }
            else:
                summary["metrics"][metric_name] = {
                    "count": 0,
                    "current": None,
                }
        
        return summary


class MetricsStream:
    """Continuously collect metrics at regular intervals"""
    
    def __init__(
        self,
        collector: MetricsCollector,
        interval_seconds: int = 5,
        max_iterations: Optional[int] = None
    ):
        """
        Initialize metrics stream
        
        Args:
            collector: MetricsCollector instance
            interval_seconds: Collection interval
            max_iterations: Maximum number of collections (None = infinite)
        """
        self.collector = collector
        self.interval_seconds = interval_seconds
        self.max_iterations = max_iterations
        self.is_running = False
        self.iteration_count = 0
    
    def start(self, on_metrics_callback=None) -> None:
        """
        Start collecting metrics continuously
        
        Args:
            on_metrics_callback: Optional callback function called with metrics dict
        """
        self.is_running = True
        self.iteration_count = 0
        logger.info(f"Starting metrics collection every {self.interval_seconds}s")
        
        try:
            while self.is_running:
                if self.max_iterations and self.iteration_count >= self.max_iterations:
                    logger.info("Reached max iterations, stopping")
                    break
                
                start_time = time.time()
                
                # Collect metrics
                metrics = self.collector.collect_once()
                
                # Call callback if provided
                if on_metrics_callback:
                    on_metrics_callback(metrics)
                
                self.iteration_count += 1
                
                # Calculate sleep time to maintain consistent interval
                elapsed = time.time() - start_time
                sleep_time = max(0, self.interval_seconds - elapsed)
                
                if sleep_time > 0:
                    logger.debug(f"Collection took {elapsed:.2f}s, sleeping {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                else:
                    logger.warning(f"Collection took {elapsed:.2f}s, exceeding interval {self.interval_seconds}s")
        
        except KeyboardInterrupt:
            logger.info("Metrics collection interrupted by user")
            self.stop()
    
    def stop(self) -> None:
        """Stop collecting metrics"""
        self.is_running = False
        logger.info(f"Metrics collection stopped after {self.iteration_count} iterations")


# Example usage functions

def example_single_collection():
    """Example: Collect metrics once"""
    print("\n=== Example 1: Single Collection ===")
    
    collector = MetricsCollector()
    
    # Check if Prometheus is available
    if not collector.client.is_healthy():
        print("ERROR: Prometheus is not accessible at http://localhost:9090")
        print("Make sure Docker containers are running: docker compose up -d")
        return
    
    # Collect metrics
    metrics = collector.collect_once()
    
    # Print summary
    summary = collector.get_metrics_summary(metrics)
    print(json.dumps(summary, indent=2))
    
    # Save to file
    filepath = collector.save_metrics(metrics)
    print(f"\nMetrics saved to: {filepath}")


def example_streaming_collection():
    """Example: Stream metrics for 60 seconds"""
    print("\n=== Example 2: Streaming Collection (60 seconds) ===")
    
    collector = MetricsCollector()
    
    if not collector.client.is_healthy():
        print("ERROR: Prometheus is not accessible")
        return
    
    # Counter for tracking
    collection_count = 0
    all_metrics = {}
    
    def process_metrics(metrics):
        nonlocal collection_count, all_metrics
        collection_count += 1
        print(f"Collection #{collection_count}")
        
        # Store metrics for later processing
        for metric_name, points in metrics.items():
            if metric_name not in all_metrics:
                all_metrics[metric_name] = []
            all_metrics[metric_name].extend(points)
        
        # Print summary
        summary = collector.get_metrics_summary(metrics)
        for metric_name, stats in summary["metrics"].items():
            if stats["count"] > 0:
                print(f"  {metric_name}: {stats['current']:.4f}")
    
    # Stream for 60 seconds (12 collections at 5s interval)
    stream = MetricsStream(
        collector,
        interval_seconds=5,
        max_iterations=12
    )
    
    stream.start(on_metrics_callback=process_metrics)
    
    # Save all collected metrics
    collector.save_metrics(all_metrics, "streaming_metrics.jsonl")
    print(f"\nCollected {collection_count} batches of metrics")


def example_custom_metrics():
    """Example: Collect custom metrics"""
    print("\n=== Example 3: Custom Metrics ===")
    
    collector = MetricsCollector()
    
    # Add custom metrics
    collector.add_metric("custom_cpu_usage", "rate(container_cpu_usage_seconds_total[30s])")
    collector.add_metric("custom_memory_percent", "container_memory_usage_bytes / container_spec_memory_limit_bytes * 100")
    
    if not collector.client.is_healthy():
        print("ERROR: Prometheus is not accessible")
        return
    
    metrics = collector.collect_once()
    
    # Print results
    for metric_name, points in metrics.items():
        print(f"\n{metric_name}:")
        for point in points:
            labels_str = ", ".join([f"{k}={v}" for k, v in point.metric_labels.items()])
            print(f"  {labels_str}: {point.value}")


if __name__ == "__main__":
    import sys
    
    print("Prometheus Metrics Fetcher - Examples")
    print("=====================================\n")
    
    if len(sys.argv) > 1:
        example = sys.argv[1]
        if example == "1":
            example_single_collection()
        elif example == "2":
            example_streaming_collection()
        elif example == "3":
            example_custom_metrics()
        else:
            print("Usage: python metrics_fetcher.py [1|2|3]")
            print("  1 - Single collection example")
            print("  2 - Streaming collection example (60s)")
            print("  3 - Custom metrics example")
    else:
        print("Running default: single collection\n")
        example_single_collection()
