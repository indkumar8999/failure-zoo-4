#!/usr/bin/env python3
"""
Practical Example: Metrics Collection Experiment

This script demonstrates:
1. Running a chaos experiment
2. Collecting metrics during the experiment
3. Processing and analyzing the results
4. Exporting data for ML pipeline
"""

import time
import json
import subprocess
from datetime import datetime
from pathlib import Path
from metrics_fetcher import MetricsCollector, MetricsStream
from metrics_pipeline import (
    MetricsPipeline,
    MetricsDataframe,
    MetricsBuffer,
    MetricsAggregator,
    MetricsExporter
)
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ExperimentRunner:
    """Runs experiments with concurrent metrics collection"""
    
    def __init__(self, output_dir: str = "./data/experiments"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pipeline = MetricsPipeline(
            output_dir=str(self.output_dir / "metrics")
        )
    
    def run_experiment(
        self,
        experiment_name: str,
        duration_seconds: int = 120,
        chaos_commands: list = None
    ):
        """
        Run an experiment with metrics collection
        
        Args:
            experiment_name: Name for this experiment
            duration_seconds: How long to collect metrics
            chaos_commands: List of chaos commands to execute
        """
        logger.info(f"Starting experiment: {experiment_name}")
        
        # Create experiment directory
        exp_dir = self.output_dir / experiment_name
        exp_dir.mkdir(exist_ok=True)
        
        # Execute chaos commands (in background)
        if chaos_commands:
            logger.info(f"Executing {len(chaos_commands)} chaos commands")
            for cmd in chaos_commands:
                logger.info(f"  → {cmd}")
                try:
                    subprocess.Popen(
                        cmd,
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                except Exception as e:
                    logger.error(f"Failed to execute: {cmd}: {e}")
        
        # Collect metrics
        logger.info(f"Collecting metrics for {duration_seconds}s...")
        collector = MetricsCollector(
            output_dir=str(exp_dir / "metrics"),
            interval_seconds=5
        )
        
        if not collector.client.is_healthy():
            logger.error("Prometheus is not accessible!")
            return None
        
        # Stream metrics
        buffer = MetricsBuffer(max_size=10000)
        
        def collect_callback(metrics):
            buffer.add_metrics(metrics)
            # Print progress
            total_points = len(buffer.buffer)
            logger.info(f"Collected {total_points} metric points")
        
        num_iterations = duration_seconds // 5
        stream = MetricsStream(
            collector,
            interval_seconds=5,
            max_iterations=num_iterations
        )
        
        stream.start(on_metrics_callback=collect_callback)
        
        # Process results
        logger.info("Processing collected metrics...")
        results = self._process_results(buffer, experiment_name, exp_dir)
        
        logger.info(f"Experiment complete: {experiment_name}")
        logger.info(f"Results saved to: {exp_dir}")
        
        return results
    
    def _process_results(self, buffer, experiment_name, exp_dir):
        """Process and export metrics"""
        
        # Convert buffer to metrics format
        buffer_data = buffer.get_buffer()
        metrics_by_name = {}
        
        for item in buffer_data:
            metric_name = item['metric_name']
            if metric_name not in metrics_by_name:
                metrics_by_name[metric_name] = []
            
            from metrics_fetcher import MetricPoint
            point = MetricPoint(
                timestamp=item['timestamp'],
                metric_name=metric_name,
                metric_labels=item.get('labels', {}),
                value=item['value']
            )
            metrics_by_name[metric_name].append(point)
        
        # Export formats
        from metrics_pipeline import MetricsExporter
        MetricsExporter.export_jsonl(
            metrics_by_name,
            str(exp_dir / "metrics.jsonl")
        )
        MetricsExporter.export_csv(
            metrics_by_name,
            str(exp_dir / "metrics.csv")
        )
        
        # Analyze
        df_handler = MetricsDataframe(metrics_by_name)
        stats = df_handler.get_statistics()
        
        # Aggregate by time window
        windowed = MetricsAggregator.aggregate_by_window(
            metrics_by_name,
            window_seconds=30  # 30-second windows
        )
        
        # Save analysis
        analysis = {
            'experiment': experiment_name,
            'timestamp': datetime.now().isoformat(),
            'duration_seconds': len(buffer_data) * 5 / len(metrics_by_name),
            'total_metric_points': len(buffer_data),
            'unique_metrics': len(metrics_by_name),
            'statistics': stats,
            'windowed_aggregates': {
                name: windows for name, windows in windowed.items()
            }
        }
        
        with open(exp_dir / "analysis.json", "w") as f:
            json.dump(analysis, f, indent=2, default=str)
        
        logger.info(f"Exported metrics to:")
        logger.info(f"  - JSONL: {exp_dir / 'metrics.jsonl'}")
        logger.info(f"  - CSV: {exp_dir / 'metrics.csv'}")
        logger.info(f"  - Analysis: {exp_dir / 'analysis.json'}")
        
        return analysis


# Predefined experiments

def cpu_saturation_experiment(runner: ExperimentRunner):
    """CPU saturation chaos experiment"""
    return runner.run_experiment(
        experiment_name="cpu_saturation",
        duration_seconds=120,
        chaos_commands=[
            "docker compose run --rm chaos cpu on 4"
        ]
    )


def memory_leak_experiment(runner: ExperimentRunner):
    """Memory leak chaos experiment"""
    return runner.run_experiment(
        experiment_name="memory_leak",
        duration_seconds=120,
        chaos_commands=[
            "docker compose run --rm chaos memleak on 50"
        ]
    )


def retry_storm_experiment(runner: ExperimentRunner):
    """Retry storm chaos experiment"""
    return runner.run_experiment(
        experiment_name="retry_storm",
        duration_seconds=120,
        chaos_commands=[
            "docker compose run --rm chaos retrystorm on 50"
        ]
    )


def combined_chaos_experiment(runner: ExperimentRunner):
    """Combined chaos: CPU + Memory + Network"""
    return runner.run_experiment(
        experiment_name="combined_chaos",
        duration_seconds=120,
        chaos_commands=[
            "docker compose run --rm chaos cpu on 2",
            "docker compose run --rm chaos memleak on 30",
            "docker compose run --rm chaos net latency 200",
        ]
    )


def sequential_chaos_experiment(runner: ExperimentRunner):
    """Sequential: CPU → Memory → Network"""
    logger.info("Starting sequential chaos experiment")
    
    # Phase 1: CPU (0-40s)
    runner.pipeline.collector.add_metric(
        "phase",
        "1"  # Mark phase
    )
    
    # Actually, let's use a simpler approach
    # Run CPU chaos for 40s, wait, then memory for 40s, etc.
    
    results = {}
    
    logger.info("Phase 1: CPU Saturation (40s)")
    subprocess.run("docker compose run --rm chaos cpu on 2", shell=True, check=False)
    time.sleep(40)
    subprocess.run("docker compose run --rm chaos cpu off", shell=True, check=False)
    time.sleep(5)
    
    logger.info("Phase 2: Memory Leak (40s)")
    subprocess.run("docker compose run --rm chaos memleak on 50", shell=True, check=False)
    time.sleep(40)
    subprocess.run("docker compose run --rm chaos memleak off", shell=True, check=False)
    time.sleep(5)
    
    logger.info("Phase 3: Network Latency (40s)")
    subprocess.run("docker compose run --rm chaos net latency 300", shell=True, check=False)
    time.sleep(40)
    subprocess.run("docker compose run --rm chaos net clear", shell=True, check=False)
    
    logger.info("Collecting metrics for complete experiment...")
    
    return results


# Main

if __name__ == "__main__":
    import sys
    
    runner = ExperimentRunner(output_dir="./data/experiments")
    
    print("\n" + "="*60)
    print("Metrics Collection & Experiment Runner")
    print("="*60 + "\n")
    
    print("Available experiments:")
    print("  1. CPU Saturation")
    print("  2. Memory Leak")
    print("  3. Retry Storm")
    print("  4. Combined Chaos")
    print("  5. Sequential Chaos")
    print("  0. Exit")
    print()
    
    if len(sys.argv) > 1:
        choice = sys.argv[1]
    else:
        choice = input("Choose experiment (0-5): ").strip()
    
    try:
        if choice == "1":
            print("\n→ Running CPU Saturation Experiment\n")
            results = cpu_saturation_experiment(runner)
        elif choice == "2":
            print("\n→ Running Memory Leak Experiment\n")
            results = memory_leak_experiment(runner)
        elif choice == "3":
            print("\n→ Running Retry Storm Experiment\n")
            results = retry_storm_experiment(runner)
        elif choice == "4":
            print("\n→ Running Combined Chaos Experiment\n")
            results = combined_chaos_experiment(runner)
        elif choice == "5":
            print("\n→ Running Sequential Chaos Experiment\n")
            results = sequential_chaos_experiment(runner)
        else:
            print("Exiting")
            sys.exit(0)
        
        # Print summary
        if results:
            print("\n" + "="*60)
            print("Experiment Results Summary")
            print("="*60)
            print(f"Total metric points: {results.get('total_metric_points', 'N/A')}")
            print(f"Unique metrics: {results.get('unique_metrics', 'N/A')}")
            print("\nMetric Statistics:")
            for metric_name, stats in results.get('statistics', {}).items():
                print(f"  {metric_name}:")
                print(f"    count: {stats.get('count', 0)}")
                print(f"    mean: {stats.get('mean', 0):.4f}")
                print(f"    std: {stats.get('std', 0):.4f}")
                print(f"    range: [{stats.get('min', 0):.4f}, {stats.get('max', 0):.4f}]")
        
        print("\n✓ Experiment complete!")
    
    except KeyboardInterrupt:
        print("\n\nExperiment interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Experiment failed: {e}", exc_info=True)
        sys.exit(1)
