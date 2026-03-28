#!/usr/bin/env python3
"""
Validation Script - Test Metrics Fetching Setup

This script validates that:
1. Prometheus is accessible
2. Metrics can be collected
3. Data can be exported in multiple formats
4. Pipeline processes data correctly
"""

import sys
import json
from pathlib import Path
from metrics_fetcher import MetricsCollector, PrometheusClient
from metrics_pipeline import MetricsDataframe, MetricsExporter
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


def print_section(title):
    """Print a section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def test_prometheus_connection():
    """Test 1: Verify Prometheus connection"""
    print_section("Test 1: Prometheus Connection")
    
    client = PrometheusClient()
    
    if client.is_healthy():
        print("✓ Prometheus is accessible at http://localhost:9090")
        return True
    else:
        print("✗ FAILED: Cannot connect to Prometheus")
        print("  Make sure: docker compose up -d")
        print("  Or run: docker compose ps")
        return False


def test_metrics_collection():
    """Test 2: Collect sample metrics"""
    print_section("Test 2: Metrics Collection")
    
    collector = MetricsCollector()
    
    print(f"Collecting metrics from {len(collector.metric_queries)} queries...")
    metrics = collector.collect_once()
    
    if not metrics:
        print("✗ FAILED: No metrics collected")
        return False
    
    total_points = sum(len(points) for points in metrics.values())
    print(f"✓ Collected {len(metrics)} metric types")
    print(f"✓ Total data points: {total_points}")
    
    # Show sample metrics
    print("\nSample metrics collected:")
    for i, (metric_name, points) in enumerate(list(metrics.items())[:5]):
        if points:
            print(f"  • {metric_name}: {points[0].value:.4f}")
        else:
            print(f"  • {metric_name}: (no data)")
    
    return total_points > 0


def test_export_formats(metrics):
    """Test 3: Export in multiple formats"""
    print_section("Test 3: Export Formats")
    
    test_dir = Path("./test_output")
    test_dir.mkdir(exist_ok=True)
    
    try:
        # JSONL
        jsonl_file = test_dir / "test.jsonl"
        MetricsExporter.export_jsonl(metrics, str(jsonl_file))
        jsonl_lines = len(jsonl_file.read_text().strip().split('\n'))
        print(f"✓ JSONL export: {jsonl_file.name} ({jsonl_lines} lines)")
        
        # CSV
        csv_file = test_dir / "test.csv"
        MetricsExporter.export_csv(metrics, str(csv_file))
        csv_lines = len(csv_file.read_text().strip().split('\n'))
        print(f"✓ CSV export: {csv_file.name} ({csv_lines} rows)")
        
        # JSON
        json_file = test_dir / "test.json"
        MetricsExporter.export_json_array(metrics, str(json_file))
        json_data = json.loads(json_file.read_text())
        print(f"✓ JSON export: {json_file.name} ({len(json_data)} objects)")
        
        return True
    
    except Exception as e:
        print(f"✗ FAILED: Export error: {e}")
        return False


def test_dataframe_processing():
    """Test 4: Pandas DataFrame processing"""
    print_section("Test 4: DataFrame Processing")
    
    collector = MetricsCollector()
    metrics = collector.collect_once()
    
    if not metrics:
        print("✗ FAILED: No metrics to process")
        return False
    
    try:
        df_handler = MetricsDataframe(metrics)
        df = df_handler.get_dataframe()
        
        if df.empty:
            print("✗ FAILED: DataFrame is empty")
            return False
        
        print(f"✓ DataFrame created: {len(df)} rows × {len(df.columns)} columns")
        
        # Test statistics
        stats = df_handler.get_statistics()
        print(f"✓ Statistics computed for {len(stats)} metrics")
        
        # Show sample stats
        for i, (metric_name, stat) in enumerate(list(stats.items())[:3]):
            if stat['count'] > 0:
                print(f"  • {metric_name}: mean={stat['mean']:.4f}, "
                      f"range=[{stat['min']:.4f}, {stat['max']:.4f}]")
        
        return True
    
    except Exception as e:
        print(f"✗ FAILED: DataFrame processing error: {e}")
        return False


def test_metrics_summary():
    """Test 5: Metrics summary generation"""
    print_section("Test 5: Metrics Summary")
    
    collector = MetricsCollector()
    metrics = collector.collect_once()
    
    if not metrics:
        print("✗ FAILED: No metrics available")
        return False
    
    try:
        summary = collector.get_metrics_summary(metrics)
        
        print(f"✓ Summary generated at {summary['timestamp']}")
        print(f"✓ Total metrics: {summary['total_metrics_collected']}")
        
        # Count metrics with data
        metrics_with_data = sum(
            1 for m in summary['metrics'].values() if m['count'] > 0
        )
        print(f"✓ Metrics with data: {metrics_with_data}/{len(summary['metrics'])}")
        
        # Show sample metrics with values
        print("\nSample metric values:")
        for i, (name, data) in enumerate(list(summary['metrics'].items())[:5]):
            if data['current'] is not None:
                print(f"  • {name}: {data['current']:.4f} "
                      f"(min={data['min']:.4f}, max={data['max']:.4f})")
        
        return True
    
    except Exception as e:
        print(f"✗ FAILED: Summary generation error: {e}")
        return False


def test_custom_metrics():
    """Test 6: Custom metrics"""
    print_section("Test 6: Custom Metrics")
    
    collector = MetricsCollector()
    
    # Add custom metrics
    try:
        collector.add_metric("custom_cpu", "rate(container_cpu_usage_seconds_total[1m])")
        collector.add_metric("custom_memory_percent", 
            "container_memory_usage_bytes / container_spec_memory_limit_bytes * 100")
        
        print(f"✓ Added 2 custom metrics")
        print(f"✓ Total queries: {len(collector.metric_queries)}")
        
        # Try to collect
        metrics = collector.collect_once()
        print(f"✓ Collection successful with custom metrics")
        
        return True
    
    except Exception as e:
        print(f"✗ FAILED: Custom metrics error: {e}")
        return False


def cleanup_test_files():
    """Clean up test output"""
    import shutil
    test_dir = Path("./test_output")
    if test_dir.exists():
        shutil.rmtree(test_dir)
        print("✓ Cleaned up test files")


def main():
    """Run all validation tests"""
    print("\n")
    print("╔" + "="*58 + "╗")
    print("║" + " "*58 + "║")
    print("║" + "  Metrics Fetching System Validation".center(58) + "║")
    print("║" + " "*58 + "║")
    print("╚" + "="*58 + "╝")
    
    results = {}
    
    # Test 1: Connection
    results['connection'] = test_prometheus_connection()
    if not results['connection']:
        print("\n⚠ Cannot continue without Prometheus")
        return False
    
    # Test 2: Collection
    results['collection'] = test_metrics_collection()
    if not results['collection']:
        print("\n⚠ Cannot continue without metrics")
        return False
    
    # Collect once for remaining tests
    collector = MetricsCollector()
    metrics = collector.collect_once()
    
    # Test 3: Export
    results['export'] = test_export_formats(metrics)
    
    # Test 4: DataFrame
    results['dataframe'] = test_dataframe_processing()
    
    # Test 5: Summary
    results['summary'] = test_metrics_summary()
    
    # Test 6: Custom
    results['custom'] = test_custom_metrics()
    
    # Cleanup
    cleanup_test_files()
    
    # Print summary
    print_section("Validation Summary")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, passed_test in results.items():
        status = "✓ PASS" if passed_test else "✗ FAIL"
        print(f"  {status}: {test_name.capitalize()}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! System is ready to use.")
        print("\nNext steps:")
        print("  1. Run experiment: python run_experiment.py")
        print("  2. Collect metrics: python metrics_fetcher.py 1")
        print("  3. Read guide: METRICS_PIPELINE_GUIDE.md")
        return True
    else:
        print("\n⚠ Some tests failed. Check the errors above.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
