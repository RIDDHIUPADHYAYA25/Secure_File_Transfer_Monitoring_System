// static/js/common.js
// SentinelTransfer - Enterprise SOC Dashboard
// Common JavaScript Functionality

// ==================================================
// GLOBAL VARIABLES
// ==================================================
let refreshIntervals = [];
let activeTooltips = [];

// ==================================================
// DOM CONTENT LOADED - INITIALIZE ALL COMPONENTS
// ==================================================
document.addEventListener('DOMContentLoaded', function() {
    'use strict';
    
    // Initialize all components
    initSidebar();
    initLiveClock();
    initGlobalSearch();
    initNotificationCenter();
    initUserProfile();
    initTooltips();
    initPopovers();
    initAOS();
    initSystemHealthCheck();
    initKeyboardShortcuts();
    initThemeFromStorage();
    initSharedEventModal();
    
    console.log('SentinelTransfer UI initialized — Enterprise SOC Mode Active');
});

// ==================================================
// SIDEBAR FUNCTIONALITY
// ==================================================
function initSidebar() {
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebarClose = document.getElementById('sidebarClose');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    const mainContent = document.getElementById('mainContent');

    if (!sidebar) return;

    const DESKTOP_BREAKPOINT = 992; // px

    function isDesktop() {
        return window.innerWidth >= DESKTOP_BREAKPOINT;
    }

    // ---- DESKTOP: collapse/expand icon rail ----
    function desktopCollapse() {
        sidebar.classList.add('sidebar-collapsed');
        if (mainContent) mainContent.classList.add('main-expanded');
        localStorage.setItem('desktopSidebarCollapsed', 'true');
    }

    function desktopExpand() {
        sidebar.classList.remove('sidebar-collapsed');
        if (mainContent) mainContent.classList.remove('main-expanded');
        localStorage.setItem('desktopSidebarCollapsed', 'false');
    }

    function toggleDesktop() {
        if (sidebar.classList.contains('sidebar-collapsed')) {
            desktopExpand();
        } else {
            desktopCollapse();
        }
    }

    // ---- MOBILE: slide-in overlay drawer ----
    function mobileOpen() {
        sidebar.classList.add('sidebar-open');
        if (sidebarOverlay) sidebarOverlay.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function mobileClose() {
        sidebar.classList.remove('sidebar-open');
        if (sidebarOverlay) sidebarOverlay.classList.remove('active');
        document.body.style.overflow = '';
    }

    function toggleMobile() {
        if (sidebar.classList.contains('sidebar-open')) {
            mobileClose();
        } else {
            mobileOpen();
        }
    }

    // ---- Unified toggle button handler ----
    window.toggleSidebar = function() {
        if (isDesktop()) {
            toggleDesktop();
        } else {
            toggleMobile();
        }
    };

    window.closeSidebar = mobileClose;
    window.openSidebar = mobileOpen;

    // Attach events
    if (sidebarToggle) sidebarToggle.addEventListener('click', window.toggleSidebar);
    if (sidebarClose) sidebarClose.addEventListener('click', mobileClose);
    if (sidebarOverlay) sidebarOverlay.addEventListener('click', mobileClose);

    // Restore desktop collapsed state from localStorage
    if (isDesktop()) {
        const collapsed = localStorage.getItem('desktopSidebarCollapsed');
        if (collapsed === 'true') {
            desktopCollapse();
        }
        // Ensure mobile classes are cleared on desktop
        sidebar.classList.remove('sidebar-open');
        if (sidebarOverlay) sidebarOverlay.classList.remove('active');
        document.body.style.overflow = '';
    }

    // Handle window resize — clean up conflicting states
    window.addEventListener('resize', function() {
        if (isDesktop()) {
            // Switch to desktop mode: remove mobile-specific states
            sidebar.classList.remove('sidebar-open');
            if (sidebarOverlay) sidebarOverlay.classList.remove('active');
            document.body.style.overflow = '';
        } else {
            // Switch to mobile mode: remove desktop-specific states
            sidebar.classList.remove('sidebar-collapsed');
            if (mainContent) mainContent.classList.remove('main-expanded');
        }
    });

    // Close mobile sidebar on Escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && sidebar.classList.contains('sidebar-open')) {
            mobileClose();
        }
    });
}

// ==================================================
// LIVE CLOCK FUNCTIONALITY
// ==================================================
function initLiveClock() {
    const clockElement = document.getElementById('liveClock');
    if (!clockElement) return;
    
    function updateClock() {
        const now = new Date();
        const hours = String(now.getUTCHours()).padStart(2, '0');
        const minutes = String(now.getUTCMinutes()).padStart(2, '0');
        const seconds = String(now.getUTCSeconds()).padStart(2, '0');
        clockElement.textContent = `${hours}:${minutes}:${seconds}`;
    }
    
    updateClock();
    setInterval(updateClock, 1000);
}

// ==================================================
// GLOBAL SEARCH FUNCTIONALITY
// ==================================================
function initGlobalSearch() {
    const searchInput = document.getElementById('globalSearch');
    const searchContainer = document.getElementById('searchContainer');
    const searchToggleBtn = document.getElementById('searchToggleBtn');
    const searchCloseBtn = document.getElementById('searchCloseBtn');
    
    if (!searchInput) return;
    
    // Mobile search toggling
    if (searchToggleBtn && searchContainer) {
        searchToggleBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            searchContainer.classList.add('expanded');
            searchInput.focus();
            searchInput.select();
        });
    }
    
    if (searchCloseBtn && searchContainer) {
        searchCloseBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            searchContainer.classList.remove('expanded');
            searchInput.value = '';
        });
    }
    
    // Collapse search when clicking outside
    document.addEventListener('click', function(e) {
        if (searchContainer && searchContainer.classList.contains('expanded')) {
            if (!searchContainer.contains(e.target)) {
                searchContainer.classList.remove('expanded');
            }
        }
    });

    // Cmd+K / Ctrl+K shortcut
    document.addEventListener('keydown', function(e) {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            if (searchContainer && window.innerWidth <= 768) {
                searchContainer.classList.add('expanded');
            }
            searchInput.focus();
            searchInput.select();
        }
        
        // Escape collapses expanded search on mobile
        if (e.key === 'Escape' && searchContainer && searchContainer.classList.contains('expanded')) {
            searchContainer.classList.remove('expanded');
            searchInput.blur();
        }
    });
    
    // Search on enter
    searchInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            const query = this.value.trim();
            if (query) {
                performGlobalSearch(query);
            }
        }
    });
    
    // Debounced search for real-time filtering
    let debounceTimer;
    searchInput.addEventListener('input', function(e) {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            const query = this.value.trim();
            if (query.length > 2) {
                performGlobalSearch(query);
            }
        }, 500);
    });
}

function performGlobalSearch(query) {
    const target = `/audit-logs?search=${encodeURIComponent(query)}`;
    window.location.href = target;
}

// ==================================================
// NOTIFICATION CENTER
// ==================================================
function initNotificationCenter() {
    const notificationBtn = document.querySelector('.notification-btn');
    if (!notificationBtn) return;
    
    // Mark all as read functionality
    const markAllLink = document.querySelector('.dropdown-header a');
    if (markAllLink) {
        markAllLink.addEventListener('click', function(e) {
            e.preventDefault();
            document.querySelectorAll('.notification-item.unread').forEach(item => {
                item.classList.remove('unread');
            });
            const badge = document.querySelector('.notification-badge');
            if (badge) badge.style.display = 'none';
            showToast('All notifications marked as read', 'success');
        });
    }

    const viewAllLink = document.querySelector('.notification-dropdown .dropdown-footer a');
    if (viewAllLink) {
        viewAllLink.addEventListener('click', function(e) {
            e.preventDefault();
            window.location.href = '/audit-logs?severity=warning';
        });
    }
}

// ==================================================
// USER PROFILE DROPDOWN
// ==================================================
function initUserProfile() {
    const profileBtn = document.querySelector('.profile-btn');
    if (!profileBtn) return;

    // Only intercept items with no real href (href="#") — real routes should navigate normally
    const profileItems = document.querySelectorAll('.user-profile .dropdown-item');
    profileItems.forEach(item => {
        const href = item.getAttribute('href') || '';
        if (href === '#' || href === '') {
            item.addEventListener('click', function(e) {
                e.preventDefault();
                showToast(`${this.textContent.trim()} — coming soon`, 'info');
            });
        }
        // Items with real hrefs (e.g., /settings, /logout) navigate normally
    });
}

// ==================================================
// TOAST NOTIFICATION SYSTEM
// ==================================================
window.showToast = function(message, type = 'info') {
    const toastColors = {
        success: 'bg-success',
        error: 'bg-danger',
        warning: 'bg-warning',
        info: 'bg-primary'
    };
    
    const icons = {
        success: 'bi-check-circle-fill',
        error: 'bi-exclamation-triangle-fill',
        warning: 'bi-exclamation-triangle-fill',
        info: 'bi-info-circle-fill'
    };
    
    const toastHtml = `
        <div class="toast align-items-center text-white ${toastColors[type]} border-0 position-fixed bottom-0 end-0 m-3" 
             role="alert" aria-live="assertive" aria-atomic="true" data-bs-autohide="true" data-bs-delay="4000">
            <div class="d-flex">
                <div class="toast-body">
                    <i class="bi ${icons[type]} me-2"></i>
                    ${escapeHtml(message)}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', toastHtml);
    const toastElement = document.querySelector('.toast:last-child');
    const toast = new bootstrap.Toast(toastElement);
    toast.show();
    
    toastElement.addEventListener('hidden.bs.toast', function() {
        this.remove();
    });
};

window.openSharedEventDetails = function(log) {
    if (!log) return;
    const timestamp = log.timestamp instanceof Date ? log.timestamp.toLocaleString() : log.timestamp || '-';
    const status = (log.status || log.severity || 'N/A').toString();
    const severity = (log.severity || log.status || 'N/A').toString();
    const alertType = log.alert_type || log.alertType || 'N/A';
    const alertReason = log.alert_reason || log.alertReason || 'N/A';
    const severityReason = log.severity_reason || log.severityReason || 'N/A';
    const sourcePath = log.source_path || log.sourcePath || 'N/A';
    const destinationPath = log.destination_path || log.destinationPath || 'N/A';
    const sha256 = log.sha256_hash || log.sha256Hash || log.sha256 || 'N/A';

    const setText = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    };

    setText('detailModalTimestamp', timestamp);
    setText('detailModalEventType', log.event_type || log.eventType || 'N/A');
    setText('detailModalUser', log.user || 'N/A');
    setText('detailModalProcessName', log.process_name || log.processName || 'N/A');
    setText('detailModalFileName', log.file_name || log.fileName || 'N/A');
    setText('detailModalSourcePath', sourcePath);
    setText('detailModalDestinationPath', destinationPath);
    setText('detailModalStatus', status);
    setText('detailModalSeverity', severity);
    setText('detailModalAlertType', alertType);
    setText('detailModalAlertReason', alertReason);
    setText('detailModalSeverityReason', severityReason);
    setText('detailModalSha256', sha256);

    const modalEl = document.getElementById('eventDetailsModal');
    if (modalEl) {
        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        modal.show();
    }
};

window.copyDetailValue = function(value) {
    if (!value) return;
    navigator.clipboard.writeText(value).then(() => {
        if (window.showToast) {
            window.showToast('Copied to clipboard', 'success');
        }
    }).catch(() => {
        if (window.showToast) {
            window.showToast('Unable to copy to clipboard', 'warning');
        }
    });
};

function initSharedEventModal() {
    const sourceBtn = document.getElementById('copyDetailSourceBtn');
    const destinationBtn = document.getElementById('copyDetailDestinationBtn');

    if (sourceBtn) {
        sourceBtn.addEventListener('click', () => {
            const value = document.getElementById('detailModalSourcePath')?.textContent || '';
            window.copyDetailValue(value);
        });
    }

    if (destinationBtn) {
        destinationBtn.addEventListener('click', () => {
            const value = document.getElementById('detailModalDestinationPath')?.textContent || '';
            window.copyDetailValue(value);
        });
    }
}

// ==================================================
// BOOTSTRAP TOOLTIPS
// ==================================================
function initTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    const tooltips = tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl, {
            delay: { show: 300, hide: 100 }
        });
    });
    activeTooltips.push(...tooltips);
}

// ==================================================
// BOOTSTRAP POPOVERS
// ==================================================
function initPopovers() {
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function(popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
}

// ==================================================
// AOS ANIMATION INITIALIZATION
// ==================================================
function initAOS() {
    if (typeof AOS !== 'undefined') {
        AOS.init({
            duration: 400,
            once: true,
            offset: 50,
            easing: 'ease-in-out'
        });
    }
}

// ==================================================
// SYSTEM HEALTH CHECK
// ==================================================
function initSystemHealthCheck() {
    setInterval(() => {
        checkSystemHealth();
    }, 30000); // Every 30 seconds
}

async function checkSystemHealth() {
    const statusDot = document.querySelector('.status-indicator');
    if (!statusDot) return;

    try {
        const response = await fetch('/api/stats');
        if (!response.ok) throw new Error('Health endpoint failed');
        const stats = await response.json();
        if (stats.watcher_active) {
            statusDot.classList.remove('warning');
            statusDot.classList.add('online');
        } else {
            statusDot.classList.remove('online');
            statusDot.classList.add('warning');
        }
    } catch (error) {
        statusDot.classList.remove('online');
        statusDot.classList.add('warning');
    }
}

// ==================================================
// KEYBOARD SHORTCUTS
// ==================================================
function initKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // Alt + D - Go to Dashboard
        if (e.altKey && e.key === 'd') {
            e.preventDefault();
            window.location.href = '/';
        }
        // Alt + M - Go to Live Monitor
        if (e.altKey && e.key === 'm') {
            e.preventDefault();
            window.location.href = '/live-monitor';
        }
        // Alt + S - Go to Settings
        if (e.altKey && e.key === 's') {
            e.preventDefault();
            window.location.href = '/settings';
        }
        // Alt + R - Refresh current page
        if (e.altKey && e.key === 'r') {
            e.preventDefault();
            window.location.reload();
        }
    });
}

// ==================================================
// THEME MANAGEMENT
// ==================================================
function initThemeFromStorage() {
    const savedTheme = localStorage.getItem('sentinelTheme');
    if (savedTheme && savedTheme !== 'dark') {
        applyTheme(savedTheme);
    }
}

function applyTheme(theme) {
    const root = document.documentElement;
    if (theme === 'light') {
        root.style.setProperty('--bg-primary', '#f8f9fa');
        root.style.setProperty('--bg-secondary', '#ffffff');
        root.style.setProperty('--bg-tertiary', '#f1f3f5');
        root.style.setProperty('--bg-card', '#ffffff');
        root.style.setProperty('--text-primary', '#212529');
        root.style.setProperty('--text-secondary', '#6c757d');
        root.style.setProperty('--border-light', '#dee2e6');
        document.body.classList.add('light-mode');
    } else {
        root.style.setProperty('--bg-primary', '#0a0c12');
        root.style.setProperty('--bg-secondary', '#0f1118');
        root.style.setProperty('--bg-tertiary', '#151722');
        root.style.setProperty('--bg-card', '#1a1d2b');
        root.style.setProperty('--text-primary', '#e9ecef');
        root.style.setProperty('--text-secondary', '#8b92a8');
        root.style.setProperty('--border-light', 'rgba(255, 255, 255, 0.05)');
        document.body.classList.remove('light-mode');
    }
    localStorage.setItem('sentinelTheme', theme);
}

// ==================================================
// TABLE REFRESH UTILITY
// ==================================================
window.refreshTable = function(tableId, apiUrl) {
    const tableBody = document.querySelector(`#${tableId} tbody`);
    if (!tableBody) return;
    
    showToast('Refreshing data...', 'info');
    
    fetch(apiUrl)
        .then(response => response.json())
        .then(data => {
            // This is a generic function - specific implementation depends on table structure
            console.log('Table refresh completed:', data);
            showToast('Data refreshed successfully', 'success');
        })
        .catch(error => {
            console.error('Refresh error:', error);
            showToast('Failed to refresh data', 'error');
        });
};

// ==================================================
// EXPORT DATA UTILITY
// ==================================================
window.exportToCSV = function(data, filename) {
    if (!data || !data.length) {
        showToast('No data to export', 'warning');
        return;
    }
    
    const headers = Object.keys(data[0]);
    const csvRows = [headers];
    
    data.forEach(row => {
        const values = headers.map(header => {
            const value = row[header] || '';
            return `"${String(value).replace(/"/g, '""')}"`;
        });
        csvRows.push(values.join(','));
    });
    
    const csvContent = csvRows.join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    
    showToast(`Exported ${data.length} records to CSV`, 'success');
};

// ==================================================
// FORMATTING UTILITIES
// ==================================================
window.formatBytes = function(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
};

window.formatDate = function(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`;
    if (diffHours < 24) return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
    if (diffDays < 7) return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
    return date.toLocaleDateString();
};

window.truncateText = function(text, maxLength = 50) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength - 3) + '...';
};

window.escapeHtml = function(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
};

window.collapseEmptySections = function(root = document) {
    root.querySelectorAll('[data-collapse-empty]').forEach(section => {
        const hasCanvas = section.querySelector('canvas:not(.d-none)');
        const hasRows = section.querySelector('tbody tr');
        const hasItems = section.querySelector('[data-content-item], .alert-item-mini, .timeline-item');
        const hasExplicitText = section.textContent.trim().length > 0;
        section.classList.toggle('d-none', !(hasCanvas || hasRows || hasItems || hasExplicitText));
    });
};

// ==================================================
// CHART COLOR UTILITIES (Dark Theme)
// ==================================================
window.getChartColors = function() {
    return {
        primary: '#0d6efd',
        secondary: '#6c757d',
        success: '#198754',
        danger: '#dc3545',
        warning: '#ffc107',
        info: '#0dcaf0',
        dark: '#1a1d2b',
        grid: '#23252e',
        text: '#adb5bd'
    };
};

window.getChartOptions = function() {
    const colors = getChartColors();
    return {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
            legend: {
                labels: { color: colors.text }
            },
            tooltip: {
                mode: 'index',
                intersect: false,
                backgroundColor: '#1a1d2b',
                titleColor: '#e9ecef',
                bodyColor: '#adb5bd',
                borderColor: '#0d6efd',
                borderWidth: 1
            }
        },
        scales: {
            y: {
                grid: { color: colors.grid },
                ticks: { color: colors.text }
            },
            x: {
                grid: { color: colors.grid },
                ticks: { color: colors.text }
            }
        }
    };
};

// ==================================================
// PAGINATION UTILITY
// ==================================================
class Pagination {
    constructor(items, itemsPerPage, renderCallback) {
        this.items = items;
        this.itemsPerPage = itemsPerPage;
        this.renderCallback = renderCallback;
        this.currentPage = 1;
        this.totalPages = Math.ceil(items.length / itemsPerPage);
    }
    
    getCurrentItems() {
        const start = (this.currentPage - 1) * this.itemsPerPage;
        const end = start + this.itemsPerPage;
        return this.items.slice(start, end);
    }
    
    goToPage(page) {
        if (page < 1 || page > this.totalPages) return;
        this.currentPage = page;
        this.renderCallback(this.getCurrentItems(), this);
    }
    
    next() {
        this.goToPage(this.currentPage + 1);
    }
    
    previous() {
        this.goToPage(this.currentPage - 1);
    }
    
    renderPaginationControls(containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;
        
        let html = '<div class="pagination-controls">';
        html += `<button class="page-btn" ${this.currentPage === 1 ? 'disabled' : ''} onclick="paginationInstance.previous()">Previous</button>`;
        html += `<span class="mx-2">Page ${this.currentPage} of ${this.totalPages}</span>`;
        html += `<button class="page-btn" ${this.currentPage === this.totalPages ? 'disabled' : ''} onclick="paginationInstance.next()">Next</button>`;
        html += '</div>';
        container.innerHTML = html;
    }
}

window.Pagination = Pagination;

// ==================================================
// CLEANUP ON PAGE UNLOAD
// ==================================================
window.addEventListener('beforeunload', function() {
    // Clear all refresh intervals
    refreshIntervals.forEach(interval => clearInterval(interval));
    refreshIntervals = [];
    
    // Destroy tooltips
    activeTooltips.forEach(tooltip => {
        if (tooltip && tooltip.dispose) tooltip.dispose();
    });
    activeTooltips = [];
});

// ==================================================
// MODAL HANDLERS
// ==================================================
document.addEventListener('show.bs.modal', function(event) {
    const modal = event.target;
    // Add animation class
    modal.classList.add('fade-in');
});

document.addEventListener('hidden.bs.modal', function(event) {
    const modal = event.target;
    // Remove animation class
    modal.classList.remove('fade-in');
});

// ==================================================
// FORM VALIDATION HELPERS
// ==================================================
window.validateForm = function(formId) {
    const form = document.getElementById(formId);
    if (!form) return true;
    
    const inputs = form.querySelectorAll('input[required], select[required], textarea[required]');
    let isValid = true;
    
    inputs.forEach(input => {
        if (!input.value.trim()) {
            input.classList.add('is-invalid');
            isValid = false;
        } else {
            input.classList.remove('is-invalid');
        }
    });
    
    return isValid;
};

// ==================================================
// LOADING STATE HANDLER
// ==================================================
window.showLoading = function(message = 'Loading...') {
    const overlay = document.getElementById('loadingOverlay') || createLoadingOverlay();
    const messageSpan = overlay.querySelector('.loading-message') || overlay.querySelector('span');
    if (messageSpan) messageSpan.textContent = message;
    overlay.style.display = 'flex';
};

window.hideLoading = function() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) overlay.style.display = 'none';
};

function createLoadingOverlay() {
    const overlay = document.createElement('div');
    overlay.id = 'loadingOverlay';
    overlay.className = 'loading-overlay';
    overlay.innerHTML = `
        <div class="spinner-border text-primary" role="status">
            <span class="visually-hidden">Loading...</span>
        </div>
        <span class="loading-message">Loading...</span>
    `;
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(10, 12, 18, 0.95);
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 1rem;
        z-index: 1100;
        backdrop-filter: blur(4px);
        display: none;
    `;
    document.body.appendChild(overlay);
    return overlay;
}

// ==================================================
// LOCAL STORAGE HELPERS
// ==================================================
window.saveToStorage = function(key, value) {
    try {
        localStorage.setItem(`sentinel_${key}`, JSON.stringify(value));
        return true;
    } catch (e) {
        console.error('Storage save error:', e);
        return false;
    }
};

window.loadFromStorage = function(key, defaultValue = null) {
    try {
        const value = localStorage.getItem(`sentinel_${key}`);
        return value ? JSON.parse(value) : defaultValue;
    } catch (e) {
        console.error('Storage load error:', e);
        return defaultValue;
    }
};

// ==================================================
// NETWORK CONNECTION CHECK
// ==================================================
window.isOnline = function() {
    return navigator.onLine;
};

window.addEventListener('online', function() {
    showToast('Network connection restored', 'success');
});

window.addEventListener('offline', function() {
    showToast('Network connection lost. Some features may be unavailable.', 'warning');
});

// ==================================================
// EXPOSE GLOBALLY ACCESSIBLE FUNCTIONS
// ==================================================
window.SentinelTransfer = {
    showToast: window.showToast,
    formatBytes: window.formatBytes,
    formatDate: window.formatDate,
    truncateText: window.truncateText,
    escapeHtml: window.escapeHtml,
    exportToCSV: window.exportToCSV,
    refreshTable: window.refreshTable,
    showLoading: window.showLoading,
    hideLoading: window.hideLoading,
    saveToStorage: window.saveToStorage,
    loadFromStorage: window.loadFromStorage,
    isOnline: window.isOnline,
    Pagination: window.Pagination,
    getChartColors: window.getChartColors,
    getChartOptions: window.getChartOptions,
    collapseEmptySections: window.collapseEmptySections
};
