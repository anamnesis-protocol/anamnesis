"""
test_vault_monitor.py — Tests for automated vault health monitoring
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

from src.vault_monitor import (
    VaultMonitor,
    HealthMetric,
    HealthAlert,
    should_run_check,
)


def test_health_metric_creation():
    """Test creating health metric."""
    metric = HealthMetric(
        timestamp="2026-04-01T10:00:00",
        health_score=85,
        total_sections=10,
        with_metadata=8,
        stale_count=2,
        active_count=6,
        issues=["2 stale sections"],
    )
    
    assert metric.health_score == 85
    assert len(metric.issues) == 1


def test_health_alert_creation():
    """Test creating health alert."""
    alert = HealthAlert(
        severity="warning",
        category="stale_content",
        message="3 sections not reviewed",
        timestamp="2026-04-01T10:00:00",
    )
    
    assert alert.severity == "warning"
    assert not alert.resolved


def test_vault_monitor_initialization():
    """Test VaultMonitor initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        metrics_file = Path(tmpdir) / "metrics.json"
        monitor = VaultMonitor(metrics_file)
        
        assert len(monitor.metrics_history) == 0
        assert len(monitor.alerts) == 0


def test_run_health_check():
    """Test running a health check."""
    sections = {
        "section1": """---
tags: ["#status/active"]
created: "2026-04-01"
last_updated: "2026-04-01"
last_reviewed: "{}"
status: "active"
version: "1.0"
---
Content
""".format(datetime.now().date().isoformat()),
        "section2": "No metadata",
    }
    
    with tempfile.TemporaryDirectory() as tmpdir:
        metrics_file = Path(tmpdir) / "metrics.json"
        monitor = VaultMonitor(metrics_file)
        
        metric = monitor.run_health_check(sections)
        
        assert metric.total_sections == 2
        assert metric.with_metadata == 1
        assert len(monitor.metrics_history) == 1


def test_generate_alerts_critical():
    """Test critical alert generation."""
    sections = {
        "section1": "No metadata",
        "section2": "No metadata",
    }
    
    with tempfile.TemporaryDirectory() as tmpdir:
        metrics_file = Path(tmpdir) / "metrics.json"
        monitor = VaultMonitor(metrics_file)
        
        monitor.run_health_check(sections)
        
        # Should generate critical alert for low health
        critical_alerts = [a for a in monitor.alerts if a.severity == "critical"]
        assert len(critical_alerts) > 0


def test_generate_alerts_stale():
    """Test stale content alert generation."""
    sections = {
        f"section{i}": """---
tags: ["#status/active"]
created: "2025-01-01"
last_updated: "2025-01-01"
last_reviewed: "2025-01-01"
status: "active"
version: "1.0"
---
Content
"""
        for i in range(5)
    }
    
    with tempfile.TemporaryDirectory() as tmpdir:
        metrics_file = Path(tmpdir) / "metrics.json"
        monitor = VaultMonitor(metrics_file)
        
        monitor.run_health_check(sections)
        
        # Should generate alert for stale sections
        stale_alerts = [a for a in monitor.alerts if a.category == "stale_content"]
        assert len(stale_alerts) > 0


def test_metrics_history_limit():
    """Test that metrics history is limited to 100."""
    sections = {"section1": "Content"}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        metrics_file = Path(tmpdir) / "metrics.json"
        monitor = VaultMonitor(metrics_file)
        
        # Add 150 metrics
        for i in range(150):
            monitor.run_health_check(sections)
        
        # Should keep only last 100
        assert len(monitor.metrics_history) == 100


def test_alerts_limit():
    """Test that alerts are limited to 50."""
    sections = {"section1": "No metadata"}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        metrics_file = Path(tmpdir) / "metrics.json"
        monitor = VaultMonitor(metrics_file)
        
        # Generate many alerts
        for i in range(60):
            monitor.run_health_check(sections)
        
        # Should keep only last 50
        assert len(monitor.alerts) <= 50


def test_get_health_trend():
    """Test health trend analysis."""
    sections = {"section1": """---
tags: ["#status/active"]
created: "2026-04-01"
last_updated: "2026-04-01"
last_reviewed: "{}"
status: "active"
version: "1.0"
---
Content
""".format(datetime.now().date().isoformat())}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        metrics_file = Path(tmpdir) / "metrics.json"
        monitor = VaultMonitor(metrics_file)
        
        # Add some metrics
        for i in range(10):
            monitor.run_health_check(sections)
        
        trend = monitor.get_health_trend(30)
        
        assert 'trend' in trend
        assert 'average_score' in trend
        assert trend['data_points'] > 0


def test_get_active_alerts():
    """Test getting active alerts."""
    sections = {"section1": "No metadata"}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        metrics_file = Path(tmpdir) / "metrics.json"
        monitor = VaultMonitor(metrics_file)
        
        monitor.run_health_check(sections)
        
        active = monitor.get_active_alerts()
        assert len(active) > 0
        
        # All should be unresolved
        for alert in active:
            assert not alert.resolved


def test_get_active_alerts_by_severity():
    """Test filtering alerts by severity."""
    sections = {"section1": "No metadata", "section2": "No metadata"}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        metrics_file = Path(tmpdir) / "metrics.json"
        monitor = VaultMonitor(metrics_file)
        
        monitor.run_health_check(sections)
        
        critical = monitor.get_active_alerts(severity="critical")
        warnings = monitor.get_active_alerts(severity="warning")
        
        # Should have some alerts
        assert len(critical) + len(warnings) > 0


def test_resolve_alert():
    """Test resolving an alert."""
    sections = {"section1": "No metadata"}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        metrics_file = Path(tmpdir) / "metrics.json"
        monitor = VaultMonitor(metrics_file)
        
        monitor.run_health_check(sections)
        
        alert = monitor.alerts[0]
        monitor.resolve_alert(alert)
        
        assert alert.resolved
        
        # Should not appear in active alerts
        active = monitor.get_active_alerts()
        assert alert not in active


def test_save_and_load_history():
    """Test saving and loading metrics history."""
    sections = {"section1": """---
tags: ["#status/active"]
created: "2026-04-01"
last_updated: "2026-04-01"
last_reviewed: "{}"
status: "active"
version: "1.0"
---
Content
""".format(datetime.now().date().isoformat())}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        metrics_file = Path(tmpdir) / "metrics.json"
        
        # Create and run check
        monitor1 = VaultMonitor(metrics_file)
        monitor1.run_health_check(sections)
        
        # Load in new instance
        monitor2 = VaultMonitor(metrics_file)
        
        assert len(monitor2.metrics_history) == 1
        assert monitor2.metrics_history[0].total_sections == 1


def test_get_summary():
    """Test getting monitoring summary."""
    sections = {"section1": """---
tags: ["#status/active"]
created: "2026-04-01"
last_updated: "2026-04-01"
last_reviewed: "{}"
status: "active"
version: "1.0"
---
Content
""".format(datetime.now().date().isoformat())}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        metrics_file = Path(tmpdir) / "metrics.json"
        monitor = VaultMonitor(metrics_file)
        
        monitor.run_health_check(sections)
        summary = monitor.get_summary()
        
        assert "Vault Health Monitoring Summary" in summary
        assert "Latest Health Score" in summary


def test_should_run_check_no_file():
    """Test should_run_check with no existing file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        metrics_file = Path(tmpdir) / "metrics.json"
        
        assert should_run_check(metrics_file, interval_hours=24)


def test_should_run_check_recent():
    """Test should_run_check with recent check."""
    with tempfile.TemporaryDirectory() as tmpdir:
        metrics_file = Path(tmpdir) / "metrics.json"
        
        # Create recent metrics file
        data = {
            'metrics': [],
            'alerts': [],
            'last_updated': datetime.now().isoformat(),
        }
        
        with open(metrics_file, 'w') as f:
            json.dump(data, f)
        
        # Should not run (too recent)
        assert not should_run_check(metrics_file, interval_hours=24)


def test_should_run_check_old():
    """Test should_run_check with old check."""
    with tempfile.TemporaryDirectory() as tmpdir:
        metrics_file = Path(tmpdir) / "metrics.json"
        
        # Create old metrics file
        old_time = datetime.now() - timedelta(hours=48)
        data = {
            'metrics': [],
            'alerts': [],
            'last_updated': old_time.isoformat(),
        }
        
        with open(metrics_file, 'w') as f:
            json.dump(data, f)
        
        # Should run (old enough)
        assert should_run_check(metrics_file, interval_hours=24)
