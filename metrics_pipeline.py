"""
Metrics Data Pipeline

This module provides a high-level interface for:
1. Collecting metrics from Prometheus
2. Aggregating and processing metrics
3. Preparing data for machine learning
4. Storing processed data for analysis
"""

import json
import csv
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
import pandas as pd
import logging

from metrics_fetcher import (
    MetricsCollector,
    MetricsStream,
    MetricPoint,
    PrometheusClient
)

logger = logging.getLogger(__name__)


class MetricsDataframe:
    """Convert collected metrics to pandas DataFrame for analysis"""
    
    def __init__(self, metrics: Dict[str, List[MetricPoint]]):
        """
        Initialize from collected metrics
        
        Args:
            metrics: Dictionary of metric name -> list of MetricPoints
        """
        self.metrics = metrics
        self.df = None
        self._build_dataframe()
    
    def _build_dataframe(self) -> None:
        """Build pandas DataFrame from metrics"""
        rows = []
        
        for metric_name, points in self.metrics.items():
            for point in points:
                row = {
                    'timestamp': datetime.fromtimestamp(point.timestamp),
                    'metric_name': point.metric_name,
                    'value': point.value,
                }
                
                # Add labels as separate columns
                for label_key, label_value in point.metric_labels.items():
                    row[f"label_{label_key}"] = label_value
                
                rows.append(row)
        
        self.df = pd.DataFrame(rows)
        
        if not self.df.empty:
            self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])
            self.df = self.df.sort_values('timestamp')
    
    def get_dataframe(self) -> pd.DataFrame:
        """Return the DataFrame"""
        return self.df
    
    def get_metric_values(self, metric_name: str) -> np.ndarray:
        """Get all values for a specific metric"""
        if self.df is None or self.df.empty:
            return np.array([])
        
        metric_df = self.df[self.df['metric_name'] == metric_name]
        return metric_df['value'].values
    
    def get_metric_timeseries(self, metric_name: str) -> Tuple[np.ndarray, np.ndarray]:
        """
        Get time series for a metric
        
        Returns:
            Tuple of (timestamps, values)
        """
        if self.df is None or self.df.empty:
            return np.array([]), np.array([])
        
        metric_df = self.df[self.df['metric_name'] == metric_name].copy()
        metric_df = metric_df.sort_values('timestamp')
        
        # Convert timestamps to seconds since start
        if len(metric_df) > 0:
            start_time = metric_df['timestamp'].iloc[0]
            timestamps = (metric_df['timestamp'] - start_time).dt.total_seconds().values
        else:
            timestamps = np.array([])
        
        return timestamps, metric_df['value'].values
    
    def save_to_csv(self, filepath: str) -> None:
        """Save DataFrame to CSV"""
        if self.df is not None:
            self.df.to_csv(filepath, index=False)
            logger.info(f"Saved metrics to CSV: {filepath}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistical summary of all metrics"""
        if self.df is None or self.df.empty:
            return {}
        
        stats = {}
        for metric_name in self.df['metric_name'].unique():
            values = self.get_metric_values(metric_name)
            stats[metric_name] = {
                'count': len(values),
                'mean': float(np.mean(values)),
                'std': float(np.std(values)),
                'min': float(np.min(values)),
                'max': float(np.max(values)),
                'median': float(np.median(values)),
            }
        
        return stats


class MetricsBuffer:
    """Buffer for collecting metrics over time with circular buffer"""
    
    def __init__(self, max_size: int = 1000):
        """
        Initialize metrics buffer
        
        Args:
            max_size: Maximum number of metric points to store
        """
        self.max_size = max_size
        self.buffer: List[Dict[str, Any]] = []
    
    def add_metrics(self, metrics: Dict[str, List[MetricPoint]]) -> None:
        """Add a batch of metrics to buffer"""
        for metric_name, points in metrics.items():
            for point in points:
                self.buffer.append({
                    'timestamp': point.timestamp,
                    'metric_name': point.metric_name,
                    'labels': point.metric_labels,
                    'value': point.value,
                    'collected_at': datetime.now().isoformat()
                })
        
        # Keep buffer size under max_size (remove oldest entries)
        if len(self.buffer) > self.max_size:
            self.buffer = self.buffer[-self.max_size:]
    
    def get_buffer(self) -> List[Dict[str, Any]]:
        """Get current buffer contents"""
        return self.buffer.copy()
    
    def get_last_n(self, n: int) -> List[Dict[str, Any]]:
        """Get last N metric points"""
        return self.buffer[-n:] if self.buffer else []
    
    def clear(self) -> None:
        """Clear buffer"""
        self.buffer.clear()
    
    def save_to_jsonl(self, filepath: str) -> None:
        """Save buffer to JSONL file"""
        with open(filepath, 'w') as f:
            for item in self.buffer:
                f.write(json.dumps(item) + '\n')
        logger.info(f"Saved {len(self.buffer)} metrics to {filepath}")


class MetricsExporter:
    """Export metrics in various formats"""
    
    @staticmethod
    def export_jsonl(metrics: Dict[str, List[MetricPoint]], filepath: str) -> None:
        """Export to JSONL format"""
        with open(filepath, 'w') as f:
            for metric_name, points in metrics.items():
                for point in points:
                    f.write(json.dumps({
                        'timestamp': point.timestamp,
                        'metric_name': point.metric_name,
                        'labels': point.metric_labels,
                        'value': point.value,
                    }) + '\n')
        logger.info(f"Exported {sum(len(p) for p in metrics.values())} points to {filepath}")
    
    @staticmethod
    def export_csv(metrics: Dict[str, List[MetricPoint]], filepath: str) -> None:
        """Export to CSV format"""
        # First pass: collect all possible fieldnames
        all_fieldnames = {'timestamp', 'metric_name', 'value'}
        for metric_name, points in metrics.items():
            for point in points:
                all_fieldnames.update({f"label_{k}" for k in point.metric_labels.keys()})
        
        # Sort fieldnames for consistent output
        fieldnames = sorted(all_fieldnames)
        
        # Second pass: write CSV with all fieldnames
        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, restval='')
            writer.writeheader()
            
            for metric_name, points in metrics.items():
                for point in points:
                    row = {
                        'timestamp': point.timestamp,
                        'metric_name': point.metric_name,
                        'value': point.value,
                    }
                    row.update({f"label_{k}": v for k, v in point.metric_labels.items()})
                    writer.writerow(row)
        
        logger.info(f"Exported metrics to CSV: {filepath}")
    
    @staticmethod
    def export_json_array(metrics: Dict[str, List[MetricPoint]], filepath: str) -> None:
        """Export to JSON array format"""
        data = []
        for metric_name, points in metrics.items():
            for point in points:
                data.append({
                    'timestamp': point.timestamp,
                    'metric_name': point.metric_name,
                    'labels': point.metric_labels,
                    'value': point.value,
                })
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Exported {len(data)} metrics to JSON: {filepath}")


class MetricsAggregator:
    """Aggregate metrics at different time windows"""
    
    @staticmethod
    def aggregate_by_window(
        metrics: Dict[str, List[MetricPoint]],
        window_seconds: int = 60
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Aggregate metrics into time windows
        
        Args:
            metrics: Dictionary of collected metrics
            window_seconds: Size of aggregation window in seconds
            
        Returns:
            Dictionary mapping metric name to windowed aggregates
        """
        aggregated = {}
        
        for metric_name, points in metrics.items():
            if not points:
                aggregated[metric_name] = []
                continue
            
            # Sort by timestamp
            sorted_points = sorted(points, key=lambda p: p.timestamp)
            
            # Group into windows
            windows = {}
            for point in sorted_points:
                window_id = int(point.timestamp // window_seconds)
                if window_id not in windows:
                    windows[window_id] = []
                windows[window_id].append(point.value)
            
            # Compute aggregates for each window
            windowed_data = []
            for window_id in sorted(windows.keys()):
                values = windows[window_id]
                windowed_data.append({
                    'window_id': window_id,
                    'window_start_timestamp': window_id * window_seconds,
                    'count': len(values),
                    'mean': float(np.mean(values)),
                    'std': float(np.std(values)) if len(values) > 1 else 0.0,
                    'min': float(np.min(values)),
                    'max': float(np.max(values)),
                    'sum': float(np.sum(values)),
                })
            
            aggregated[metric_name] = windowed_data
        
        return aggregated


class MetricsPipeline:
    """Complete pipeline: collect -> process -> export -> prepare for ML"""
    
    def __init__(
        self,
        prometheus_url: str = "http://localhost:9090",
        output_dir: str = "./data/metrics",
        interval_seconds: int = 5,
    ):
        """
        Initialize metrics pipeline
        
        Args:
            prometheus_url: Prometheus server URL
            output_dir: Output directory for data
            interval_seconds: Collection interval
        """
        self.collector = MetricsCollector(prometheus_url, output_dir, interval_seconds)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.buffer = MetricsBuffer(max_size=5000)
    
    def run_collection(
        self,
        duration_seconds: int = 60,
        interval_seconds: int = 5,
        export_formats: List[str] = None
    ) -> Dict[str, Path]:
        """
        Run complete metrics collection pipeline
        
        Args:
            duration_seconds: How long to collect metrics
            interval_seconds: Collection interval
            export_formats: List of export formats ['jsonl', 'csv', 'json']
            
        Returns:
            Dictionary mapping export format to file paths
        """
        if export_formats is None:
            export_formats = ['jsonl', 'csv', 'json']
        
        logger.info(f"Starting metrics collection for {duration_seconds}s")
        
        # Calculate iterations needed
        num_iterations = max(1, duration_seconds // interval_seconds)
        
        # Collect metrics
        stream = MetricsStream(
            self.collector,
            interval_seconds=interval_seconds,
            max_iterations=num_iterations
        )
        
        def collect_callback(metrics):
            self.buffer.add_metrics(metrics)
        
        stream.start(on_metrics_callback=collect_callback)
        
        # Get collected metrics
        all_metrics_list = self.buffer.get_buffer()
        
        # Convert to metrics dict format for export
        metrics_by_name = {}
        for item in all_metrics_list:
            metric_name = item['metric_name']
            if metric_name not in metrics_by_name:
                metrics_by_name[metric_name] = []
            
            point = MetricPoint(
                timestamp=item['timestamp'],
                metric_name=metric_name,
                metric_labels=item.get('labels', {}),
                value=item['value']
            )
            metrics_by_name[metric_name].append(point)
        
        # Export in requested formats
        exported_files = {}
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if 'jsonl' in export_formats:
            filepath = self.output_dir / f"metrics_{timestamp}.jsonl"
            MetricsExporter.export_jsonl(metrics_by_name, str(filepath))
            exported_files['jsonl'] = filepath
        
        if 'csv' in export_formats:
            filepath = self.output_dir / f"metrics_{timestamp}.csv"
            MetricsExporter.export_csv(metrics_by_name, str(filepath))
            exported_files['csv'] = filepath
        
        if 'json' in export_formats:
            filepath = self.output_dir / f"metrics_{timestamp}.json"
            MetricsExporter.export_json_array(metrics_by_name, str(filepath))
            exported_files['json'] = filepath
        
        logger.info(f"Collection complete. Collected {len(all_metrics_list)} metric points")
        
        return exported_files
    
    def analyze_collected_data(self) -> Dict[str, Any]:
        """Analyze currently buffered metrics"""
        buffer_data = self.buffer.get_buffer()
        
        # Convert to metrics format
        metrics_by_name = {}
        for item in buffer_data:
            metric_name = item['metric_name']
            if metric_name not in metrics_by_name:
                metrics_by_name[metric_name] = []
            
            point = MetricPoint(
                timestamp=item['timestamp'],
                metric_name=metric_name,
                metric_labels=item.get('labels', {}),
                value=item['value']
            )
            metrics_by_name[metric_name].append(point)
        
        # Create dataframe
        df_handler = MetricsDataframe(metrics_by_name)
        stats = df_handler.get_statistics()
        
        return {
            'total_points': len(buffer_data),
            'unique_metrics': len(metrics_by_name),
            'statistics': stats,
            'timestamp': datetime.now().isoformat()
        }


# Example usage

def example_complete_pipeline():
    """Example: Run complete metrics pipeline"""
    print("\n=== Metrics Collection Pipeline ===\n")
    
    pipeline = MetricsPipeline(
        output_dir="./data/metrics_output",
        interval_seconds=5
    )
    
    # Run collection for 120 seconds
    print("Collecting metrics for 120 seconds...")
    exported_files = pipeline.run_collection(
        duration_seconds=120,
        interval_seconds=5,
        export_formats=['jsonl', 'csv', 'json']
    )
    
    # Print exported files
    print("\nExported files:")
    for fmt, filepath in exported_files.items():
        print(f"  {fmt}: {filepath}")
    
    # Analyze
    print("\nAnalyzing collected data...")
    analysis = pipeline.analyze_collected_data()
    
    print(f"\nCollection Statistics:")
    print(f"  Total points: {analysis['total_points']}")
    print(f"  Unique metrics: {analysis['unique_metrics']}")
    print(f"\nMetric statistics:")
    for metric_name, stats in analysis['statistics'].items():
        print(f"  {metric_name}:")
        print(f"    count: {stats['count']}")
        print(f"    mean: {stats['mean']:.4f}")
        print(f"    std: {stats['std']:.4f}")
        print(f"    range: [{stats['min']:.4f}, {stats['max']:.4f}]")


if __name__ == "__main__":
    example_complete_pipeline()
