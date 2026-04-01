"""
vault_monitor.py — Automated Vault Health Monitoring

Implements automated health checks and monitoring for vault sections.
Inspired by Symbiosis vault-health-check.py with enhanced automation.

Features:
- Automated health checks on schedule
- Health metrics tracking over time
- Alert generation for issues
- Trend analysis for vault degradation
- Integration with HCS for audit logging
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

from src.metadata import generate_health_report, get_stale_sections


@dataclass
class HealthMetric:
    """Single health metric measurement."""
    timestamp: str  # ISO datetime
    health_score: int  # 0-100
    total_sections: int
    with_metadata: int
    stale_count: int
    active_count: int
    issues: List[str]
    
    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "HealthMetric":
        """Create from dict."""
        return cls(**data)


@dataclass
class HealthAlert:
    """Health alert for issues requiring attention."""
    severity: str  # critical | warning | info
    category: str  # stale_content | missing_metadata | low_health
    message: str
    timestamp: str
    resolved: bool = False
    
    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "HealthAlert":
        """Create from dict."""
        return cls(**data)


class VaultMonitor:
    """Automated vault health monitoring system."""
    
    def __init__(self, metrics_file: Path):
        """
        Initialize vault monitor.
        
        Args:
            metrics_file: Path to metrics history JSON file
        """
        self.metrics_file = metrics_file
        self.metrics_history: List[HealthMetric] = []
        self.alerts: List[HealthAlert] = []
        self._load_history()
    
    def _load_history(self) -> None:
        """Load metrics history from file."""
        if not self.metrics_file.exists():
            return
        
        try:
            with open(self.metrics_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.metrics_history = [
                    HealthMetric.from_dict(m) for m in data.get('metrics', [])
                ]
                self.alerts = [
                    HealthAlert.from_dict(a) for a in data.get('alerts', [])
                ]
        except (json.JSONDecodeError, KeyError):
            # Corrupted file - start fresh
            self.metrics_history = []
            self.alerts = []
    
    def _save_history(self) -> None:
        """Save metrics history to file."""
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            'metrics': [m.to_dict() for m in self.metrics_history],
            'alerts': [a.to_dict() for a in self.alerts],
            'last_updated': datetime.now().isoformat(),
        }
        
        with open(self.metrics_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def run_health_check(self, sections: Dict[str, str]) -> HealthMetric:
        """
        Run health check on vault sections.
        
        Args:
            sections: Dict of {section_name: content}
            
        Returns:
            HealthMetric for this check
        """
        report = generate_health_report(sections)
        
        # Identify issues
        issues = []
        if report['missing_metadata']:
            issues.append(f"{len(report['missing_metadata'])} sections missing metadata")
        if report['stale'] > 0:
            issues.append(f"{report['stale']} stale sections (90+ days)")
        if report['health_score'] < 70:
            issues.append(f"Low health score: {report['health_score']}%")
        
        metric = HealthMetric(
            timestamp=datetime.now().isoformat(),
            health_score=report['health_score'],
            total_sections=report['total_sections'],
            with_metadata=report['with_metadata'],
            stale_count=report['stale'],
            active_count=report['active'],
            issues=issues,
        )
        
        # Add to history
        self.metrics_history.append(metric)
        
        # Keep only last 100 metrics (about 3 months if daily)
        if len(self.metrics_history) > 100:
            self.metrics_history = self.metrics_history[-100:]
        
        # Generate alerts
        self._generate_alerts(metric, report)
        
        # Save
        self._save_history()
        
        return metric
    
    def _generate_alerts(self, metric: HealthMetric, report: dict) -> None:
        """
        Generate alerts based on health metric.
        
        Args:
            metric: Current health metric
            report: Full health report
        """
        now = datetime.now().isoformat()
        
        # Critical: Health score below 50%
        if metric.health_score < 50:
            self.alerts.append(HealthAlert(
                severity="critical",
                category="low_health",
                message=f"Critical: Vault health at {metric.health_score}%",
                timestamp=now,
            ))
        
        # Warning: Health score below 70%
        elif metric.health_score < 70:
            self.alerts.append(HealthAlert(
                severity="warning",
                category="low_health",
                message=f"Warning: Vault health at {metric.health_score}%",
                timestamp=now,
            ))
        
        # Warning: Many stale sections
        if metric.stale_count >= 3:
            self.alerts.append(HealthAlert(
                severity="warning",
                category="stale_content",
                message=f"{metric.stale_count} sections not reviewed in 90+ days",
                timestamp=now,
            ))
        
        # Info: Missing metadata
        if report['missing_metadata']:
            self.alerts.append(HealthAlert(
                severity="info",
                category="missing_metadata",
                message=f"{len(report['missing_metadata'])} sections missing metadata",
                timestamp=now,
            ))
        
        # Keep only last 50 alerts
        if len(self.alerts) > 50:
            self.alerts = self.alerts[-50:]
    
    def get_health_trend(self, days: int = 30) -> dict:
        """
        Analyze health trend over time.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dict with trend analysis
        """
        if not self.metrics_history:
            return {
                'trend': 'unknown',
                'average_score': 0,
                'score_change': 0,
                'data_points': 0,
            }
        
        # Filter to last N days
        cutoff = datetime.now() - timedelta(days=days)
        recent = [
            m for m in self.metrics_history
            if datetime.fromisoformat(m.timestamp) > cutoff
        ]
        
        if not recent:
            recent = self.metrics_history[-10:]  # Fallback to last 10
        
        # Calculate trend
        scores = [m.health_score for m in recent]
        avg_score = sum(scores) / len(scores)
        
        # Compare first half vs second half
        mid = len(scores) // 2
        if mid > 0:
            first_half_avg = sum(scores[:mid]) / mid
            second_half_avg = sum(scores[mid:]) / (len(scores) - mid)
            score_change = second_half_avg - first_half_avg
            
            if score_change > 5:
                trend = "improving"
            elif score_change < -5:
                trend = "degrading"
            else:
                trend = "stable"
        else:
            score_change = 0
            trend = "stable"
        
        return {
            'trend': trend,
            'average_score': round(avg_score, 1),
            'score_change': round(score_change, 1),
            'data_points': len(recent),
            'current_score': scores[-1] if scores else 0,
        }
    
    def get_active_alerts(self, severity: Optional[str] = None) -> List[HealthAlert]:
        """
        Get active (unresolved) alerts.
        
        Args:
            severity: Filter by severity (critical, warning, info)
            
        Returns:
            List of active alerts
        """
        active = [a for a in self.alerts if not a.resolved]
        
        if severity:
            active = [a for a in active if a.severity == severity]
        
        return active
    
    def resolve_alert(self, alert: HealthAlert) -> None:
        """Mark an alert as resolved."""
        alert.resolved = True
        self._save_history()
    
    def get_summary(self) -> str:
        """
        Get human-readable monitoring summary.
        
        Returns:
            Summary string
        """
        if not self.metrics_history:
            return "No health metrics available yet."
        
        latest = self.metrics_history[-1]
        trend = self.get_health_trend(30)
        active_alerts = self.get_active_alerts()
        
        lines = [
            "Vault Health Monitoring Summary",
            "=" * 40,
            f"Latest Health Score: {latest.health_score}%",
            f"30-Day Trend: {trend['trend']} ({trend['score_change']:+.1f})",
            f"Average Score: {trend['average_score']}%",
            f"",
            f"Active Alerts: {len(active_alerts)}",
        ]
        
        if active_alerts:
            critical = [a for a in active_alerts if a.severity == "critical"]
            warnings = [a for a in active_alerts if a.severity == "warning"]
            
            if critical:
                lines.append(f"  🔴 Critical: {len(critical)}")
            if warnings:
                lines.append(f"  🟡 Warnings: {len(warnings)}")
        
        lines.extend([
            "",
            f"Total Checks: {len(self.metrics_history)}",
            f"Last Check: {latest.timestamp[:16]}",
        ])
        
        return "\n".join(lines)


def should_run_check(metrics_file: Path, interval_hours: int = 24) -> bool:
    """
    Check if enough time has passed since last health check.
    
    Args:
        metrics_file: Path to metrics file
        interval_hours: Minimum hours between checks
        
    Returns:
        True if check should run
    """
    if not metrics_file.exists():
        return True
    
    try:
        with open(metrics_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            last_updated = data.get('last_updated')
            
            if not last_updated:
                return True
            
            last_check = datetime.fromisoformat(last_updated)
            elapsed = datetime.now() - last_check
            
            return elapsed.total_seconds() / 3600 >= interval_hours
    except (json.JSONDecodeError, KeyError, ValueError):
        return True
