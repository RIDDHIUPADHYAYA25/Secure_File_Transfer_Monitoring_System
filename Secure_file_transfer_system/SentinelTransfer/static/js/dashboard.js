let pieChart;
let lineChart;
let dashboardLogs = [];

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function setProgress(id, value, label, className) {
    const el = document.getElementById(id);
    if (!el) return;
    el.style.width = `${Math.max(0, Math.min(100, value))}%`;
    el.textContent = label;
    if (className) el.className = `progress-bar ${className}`;
}

function setPanelVisible(panelId, visible) {
    const panel = document.getElementById(panelId);
    if (panel) panel.classList.toggle('d-none', !visible);
}

function hasAnyValue(values) {
    return Array.isArray(values) && values.some(value => Number(value || 0) > 0);
}

function initCharts() {
    const pieCtx = document.getElementById('fileEventsPieChart');
    if (pieCtx) {
        pieChart = new Chart(pieCtx, {
            type: 'doughnut',
            data: {
                labels: ['Internal', 'External', 'Sensitive', 'USB'],
                datasets: [{
                    data: [0, 0, 0, 0],
                    backgroundColor: ['#3b82f6', '#f59e0b', '#ef4444', '#22d3ee'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '62%',
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: ctx => `${ctx.label}: ${ctx.raw}` } }
                }
            }
        });
    }

    const lineCtx = document.getElementById('transferLineChart');
    if (lineCtx) {
        lineChart = new Chart(lineCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Total Events',
                        data: [],
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59,130,246,0.12)',
                        tension: 0.35,
                        fill: true
                    },
                    {
                        label: 'Sensitive Events',
                        data: [],
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239,68,68,0.10)',
                        tension: 0.35,
                        fill: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: { legend: { labels: { color: '#cbd5e1' } } },
                scales: {
                    y: { beginAtZero: true, grid: { color: '#222837' }, ticks: { color: '#94a3b8', precision: 0 } },
                    x: { grid: { display: false }, ticks: { color: '#94a3b8', maxTicksLimit: 8 } }
                }
            }
        });
    }
}

function renderChartState(stats, chartData) {
    const categories = chartData.categories || [0, 0, 0, 0];
    const trendValues = [
        ...(chartData.total_trend || []),
        ...(chartData.sensitive_trend || [])
    ];
    const hasCategoryData = hasAnyValue(categories);
    const hasTrendData = hasAnyValue(trendValues);

    setPanelVisible('categoryChartPanel', hasCategoryData);
    setPanelVisible('trendChartPanel', hasTrendData);
    setPanelVisible('chartsRow', hasCategoryData || hasTrendData);

    if (pieChart && hasCategoryData) {
        pieChart.data.datasets[0].data = categories;
        pieChart.update();

        const total = categories.reduce((sum, value) => sum + Number(value || 0), 0);
        const labels = ['Internal', 'External', 'Sensitive', 'USB'];
        const classes = ['text-primary', 'text-warning', 'text-danger', 'text-info'];
        const legend = document.getElementById('pieLegend');
        if (legend) {
            legend.innerHTML = labels.map((label, index) => {
                const pct = total > 0 ? Math.round((categories[index] / total) * 100) : 0;
                return `<span><i class="bi bi-circle-fill ${classes[index]}"></i> ${label} (${pct}%)</span>`;
            }).join('');
        }
    }

    if (lineChart && hasTrendData) {
        lineChart.data.labels = chartData.labels || [];
        lineChart.data.datasets[0].data = chartData.total_trend || [];
        lineChart.data.datasets[1].data = chartData.sensitive_trend || [];
        lineChart.update();
    }

    if (stats.total_events === 0 && window.SentinelTransfer?.collapseEmptySections) {
        window.SentinelTransfer.collapseEmptySections();
    }
}

async function loadDashboardData() {
    try {
        const [statsRes, chartRes] = await Promise.all([
            fetch('/api/stats'),
            fetch('/api/chart-data')
        ]);

        if (!statsRes.ok || !chartRes.ok) throw new Error('Dashboard API request failed');
        const stats = await statsRes.json();
        const chartData = await chartRes.json();

        setText('totalEventsCount', (stats.total_events || 0).toLocaleString());
        setText('sensitiveTransfersCount', (stats.sensitive_access || 0).toLocaleString());
        setText('integrityViolationsCount', (stats.integrity_violations || 0).toLocaleString());
        setText('usbTransfersCount', (stats.usb_events || 0).toLocaleString());
        setText('lastScanText', stats.last_log_time || 'No events recorded');

        const health = stats.watcher_active
            ? Math.max(0, 100 - (Number(stats.critical_events || 0) * 8) - (Number(stats.warning_events || 0) * 3))
            : 0;
        setText('systemHealthText', `System Health: ${health}%`);
        setText('threatLevelText', `Threat Level: ${stats.critical_events > 0 ? 'Critical' : stats.warning_events > 0 ? 'Elevated' : 'Normal'}`);

        const healthIcon = document.getElementById('systemHealthIcon');
        if (healthIcon) healthIcon.className = `bi ${health >= 80 ? 'bi-check-circle-fill text-success' : health > 0 ? 'bi-exclamation-circle-fill text-warning' : 'bi-x-circle-fill text-danger'}`;
        const threatIcon = document.getElementById('threatLevelIcon');
        if (threatIcon) threatIcon.className = `bi bi-activity ${stats.critical_events > 0 ? 'text-danger' : stats.warning_events > 0 ? 'text-warning' : 'text-success'}`;

        setProgress('watchdogProgressBar', 100, stats.watcher_active ? 'Active' : 'Offline', stats.watcher_active ? 'bg-success' : 'bg-danger');
        setProgress('integrityFilesProgressBar', stats.registered_files > 0 ? 100 : 0, `${stats.registered_files || 0} Files`, 'bg-info');
        setProgress('dbProgressBar', 100, stats.db_size || '0 B', 'bg-success');
        setText('serviceBadge', stats.watcher_active ? 'Operational' : 'Attention Required');
        document.getElementById('serviceBadge')?.classList.toggle('bg-success', Boolean(stats.watcher_active));
        document.getElementById('serviceBadge')?.classList.toggle('bg-danger', !stats.watcher_active);

        const liveStatus = document.getElementById('monitoringLiveStatus');
        if (liveStatus) liveStatus.innerHTML = stats.watcher_active ? '<span class="pulse"></span> Active' : '<span class="status-dot danger"></span> Offline';
        setText('coreEngineText', `Last event: ${stats.last_log_time || 'No events recorded'}`);
        setText('usbPollerText', stats.watcher_active ? 'USB detection enabled' : 'USB detection paused');

        setText('encryptedFilesVal', `${stats.registered_files || 0} Registered`);
        setText('dlpHitsVal', (stats.dlp_hits || 0).toLocaleString());
        setText('violationsVal', (stats.integrity_violations || 0).toLocaleString());
        setText('watcherHealthVal', `${health}%`);
        setProgress('encryptedFilesBar', stats.registered_files > 0 ? 100 : 0, '', 'bg-success');
        setProgress('dlpHitsBar', stats.dlp_hits > 0 ? 100 : 0, '', 'bg-warning');
        setProgress('violationsBar', stats.integrity_violations > 0 ? 100 : 0, '', 'bg-danger');
        setProgress('watcherHealthBar', health, '', stats.watcher_active ? 'bg-info' : 'bg-danger');

        renderChartState(stats, chartData);
        document.querySelector('[data-empty-section]')?.classList.toggle('d-none', Number(stats.total_events || 0) > 0);
        await Promise.all([fetchLogs(true), fetchAlerts()]);
    } catch (err) {
        console.error('Error loading dashboard data:', err);
        if (window.showToast) window.showToast('Unable to load dashboard data', 'error');
    }
}

async function fetchAlerts() {
    try {
        const res = await fetch('/api/audit-logs?limit=10');
        if (!res.ok) throw new Error('Alert request failed');
        const logsData = await res.json();
        const container = document.getElementById('recentAlertsList');
        if (!container) return;

        const alertLogs = logsData.filter(log => log.status === 'warning' || log.status === 'critical');
        setPanelVisible('recentAlertsPanel', alertLogs.length > 0);
        if (alertLogs.length === 0) return;

        container.innerHTML = alertLogs.slice(0, 5).map(alert => {
            const critical = alert.status === 'critical';
            return `
                <button class="alert-item-mini ${critical ? 'critical' : 'warning'}" data-log-id="${alert.id}">
                    <i class="bi ${critical ? 'bi-exclamation-octagon-fill' : 'bi-exclamation-triangle-fill'}"></i>
                    <span>
                        <strong>${escapeHtml(alert.alert_reason || alert.severity_reason || 'Security alert')}</strong>
                        <small>${escapeHtml(alert.file_name || '-')} | ${escapeHtml(alert.timestamp || '-')}</small>
                    </span>
                    <em>${escapeHtml(alert.status || 'info')}</em>
                </button>`;
        }).join('');

        container.querySelectorAll('[data-log-id]').forEach(item => {
            item.addEventListener('click', () => {
                const log = alertLogs.find(entry => Number(entry.id) === Number(item.dataset.logId));
                if (log) window.openSharedEventDetails(log);
            });
        });
    } catch (err) {
        console.error('Error fetching alerts:', err);
    }
}

async function fetchLogs(isInitial = false) {
    try {
        const res = await fetch('/api/audit-logs?limit=5');
        if (!res.ok) throw new Error('Log request failed');
        const logs = await res.json();
        dashboardLogs = logs;

        const tableBody = document.getElementById('auditLogTable');
        const timeline = document.getElementById('dashboardTimeline');
        setPanelVisible('timelinePanel', logs.length > 0);
        setPanelVisible('auditLogsPanel', logs.length > 0);

        if (tableBody && logs.length > 0) {
            tableBody.innerHTML = logs.map(log => {
                const statusClass = log.status === 'critical' ? 'bg-danger' : log.status === 'warning' ? 'bg-warning text-dark' : 'bg-success';
                return `
                    <tr class="clickable" data-log-id="${log.id}">
                        <td class="mono">${escapeHtml(log.timestamp || '-')}</td>
                        <td>${escapeHtml(log.event_type || '-')}</td>
                        <td>${escapeHtml(log.user || 'system')} / ${escapeHtml(log.process_name || 'unknown')}</td>
                        <td><span class="badge ${statusClass}">${escapeHtml(log.status || 'info')}</span></td>
                    </tr>`;
            }).join('');

            tableBody.querySelectorAll('[data-log-id]').forEach(row => {
                row.addEventListener('click', () => {
                    const log = dashboardLogs.find(item => Number(item.id) === Number(row.dataset.logId));
                    if (log) window.openSharedEventDetails(log);
                });
            });
        }

        if (timeline && logs.length > 0) {
            timeline.innerHTML = logs.slice(0, 4).map(log => {
                const badgeClass = log.status === 'critical' ? 'danger' : log.status === 'warning' ? 'warning' : 'primary';
                return `
                    <div class="timeline-item">
                        <div class="timeline-badge ${badgeClass}"></div>
                        <div class="timeline-content">
                            <h6>${escapeHtml(log.event_type || 'File Event')}</h6>
                            <p>${escapeHtml(log.details || log.file_name || 'Audit event recorded')}</p>
                            <small>${escapeHtml(log.timestamp || '-')}</small>
                        </div>
                    </div>`;
            }).join('');
        }

        if (!isInitial && window.showToast) window.showToast('Audit logs refreshed', 'success');
    } catch (err) {
        console.error('Error fetching logs:', err);
        if (!isInitial && window.showToast) window.showToast('Unable to refresh logs', 'error');
    }
}

function refreshLogs() {
    fetchLogs(false);
}

window.refreshLogs = refreshLogs;

document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    loadDashboardData();
    window.setInterval(loadDashboardData, 30000);

    const dashboardDbMonitor = document.getElementById('dashboardDbMonitor');
    if (dashboardDbMonitor) {
        dashboardDbMonitor.addEventListener('click', () => {
            const isEncrypted = window.SentinelDashboard?.dbEncrypted;
            if (window.showToast) {
                window.showToast(isEncrypted ? 'Database is encrypted at rest' : 'Database is decrypted for this authorized session', 'info');
            }
        });
    }
});
