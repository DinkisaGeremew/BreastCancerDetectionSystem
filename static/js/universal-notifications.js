/**
 * Universal Notification System
 * Provides consistent notification functionality across all dashboards
 */

class UniversalNotificationSystem {
    constructor(options = {}) {
        this.options = {
            pollInterval: 30000, // 30 seconds
            maxNotifications: 50,
            autoRefresh: true,
            ...options
        };
        
        this.isInitialized = false;
        this.notifications = [];
        this.unreadCount = 0;
        this.pollTimer = null;
        
        this.init();
    }
    
    init() {
        if (this.isInitialized) return;
        
        try {
            console.log('🔄 Creating notification elements...');
            this.createNotificationElements();
            
            console.log('🔄 Binding events...');
            this.bindEvents();
            
            console.log('🔄 Loading initial notifications...');
            this.loadNotifications();
            
            if (this.options.autoRefresh) {
                console.log('🔄 Starting polling...');
                this.startPolling();
            }
            
            this.isInitialized = true;
            console.log('✅ Universal Notification System initialized successfully');
        } catch (error) {
            console.error('❌ Error during notification system initialization:', error);
            this.showError('Failed to initialize notification system');
        }
    }
    
    createNotificationElements() {
        // Find existing notification bell or create one
        let notificationBell = document.getElementById('universalNotificationBell') || 
                              document.getElementById('notificationBell') ||
                              document.querySelector('.notification-bell');
        
        if (!notificationBell) {
            // Check if there are any existing notification bells before creating a new one
            const existingBells = document.querySelectorAll('.notification-bell');
            if (existingBells.length > 0) {
                console.log('⚠️ Found existing notification bells, using the first one');
                notificationBell = existingBells[0];
            } else {
                // Create notification bell if it doesn't exist
                const headerRight = document.querySelector('.header-right') || document.querySelector('.main-header');
                if (headerRight) {
                    notificationBell = this.createNotificationBell();
                    headerRight.appendChild(notificationBell);
                    console.log('✅ Created new notification bell');
                }
            }
        } else {
            console.log('✅ Using existing notification bell:', notificationBell.id || notificationBell.className);
        }
        
        // Find existing notification panel or create one
        let notificationPanel = document.getElementById('universalNotificationPanel') ||
                               document.getElementById('notificationPanel') ||
                               document.querySelector('.notification-panel');
        
        if (!notificationPanel) {
            notificationPanel = this.createNotificationPanel();
            document.body.appendChild(notificationPanel);
        } else {
            console.log('✅ Using existing notification panel:', notificationPanel.id || notificationPanel.className);
        }
        
        this.notificationBell = notificationBell;
        this.notificationPanel = notificationPanel;
        
        // Remove any duplicate notification bells
        this.removeDuplicateBells();
    }
    
    createNotificationBell() {
        const bell = document.createElement('div');
        bell.id = 'universalNotificationBell';
        bell.className = 'notification-bell';
        bell.setAttribute('aria-label', 'Notifications');
        bell.setAttribute('role', 'button');
        bell.setAttribute('tabindex', '0');
        
        bell.innerHTML = `
            <i class="fas fa-bell"></i>
            <span class="notification-badge" id="universalNotificationBadge" style="display: none;">0</span>
        `;
        
        return bell;
    }
    
    removeDuplicateBells() {
        const allBells = document.querySelectorAll('.notification-bell');
        if (allBells.length > 1) {
            console.log(`⚠️ Found ${allBells.length} notification bells, removing duplicates`);
            
            // Keep the first one (or the one we're using) and remove the rest
            for (let i = 1; i < allBells.length; i++) {
                if (allBells[i] !== this.notificationBell) {
                    console.log('🗑️ Removing duplicate notification bell:', allBells[i]);
                    allBells[i].remove();
                }
            }
        }
    }
    
    createNotificationPanel() {
        const panel = document.createElement('div');
        panel.id = 'universalNotificationPanel';
        panel.className = 'notification-panel';
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-label', 'Notifications');
        panel.setAttribute('aria-modal', 'true');
        
        panel.innerHTML = `
            <div class="notification-header">
                <h3>Notifications</h3>
                <div style="display: flex; gap: 10px;">
                    <button id="markAllReadBtn" class="notification-action-btn">Mark all as read</button>
                    <button id="clearAllBtn" class="notification-action-btn clear-all-btn">Clear All</button>
                </div>
            </div>
            <div class="notification-list" id="universalNotificationList">
                <div class="notification-loading">
                    <i class="fas fa-spinner fa-spin"></i>
                    <span>Loading notifications...</span>
                </div>
            </div>
            <div class="notification-footer">
                <button id="refreshNotificationsBtn" class="notification-refresh-btn">
                    <i class="fas fa-sync-alt"></i> Refresh
                </button>
            </div>
        `;
        
        return panel;
    }
    
    bindEvents() {
        // Notification bell click
        if (this.notificationBell) {
            this.notificationBell.addEventListener('click', () => this.toggleNotificationPanel());
            this.notificationBell.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    this.toggleNotificationPanel();
                }
            });
        }
        
        // Panel action buttons - check for existing buttons first
        const markAllReadBtn = document.getElementById('markAllReadBtn') || 
                              document.querySelector('[data-action="mark-all-read"]');
        const clearAllBtn = document.getElementById('clearAllBtn') ||
                           document.querySelector('[data-action="clear-all"]');
        const refreshBtn = document.getElementById('refreshNotificationsBtn') ||
                          document.querySelector('[data-action="refresh"]');
        
        if (markAllReadBtn) {
            markAllReadBtn.addEventListener('click', () => this.markAllAsRead());
        }
        
        if (clearAllBtn) {
            clearAllBtn.addEventListener('click', () => this.clearAllNotifications());
        }
        
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.loadNotifications());
        }
        
        // Close panel when clicking outside
        document.addEventListener('click', (e) => {
            if (this.notificationPanel && 
                !this.notificationPanel.contains(e.target) && 
                !this.notificationBell.contains(e.target)) {
                this.hideNotificationPanel();
            }
        });
        
        // ESC key to close panel
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.notificationPanel.classList.contains('active')) {
                this.hideNotificationPanel();
            }
        });
    }
    
    async loadNotifications() {
        try {
            const url = '/api/notifications?limit=' + this.options.maxNotifications;
            console.log('🔄 Loading notifications...');
            console.log('🌐 Request URL:', url);
            console.log('🌐 Base URL:', window.location.origin);
            console.log('🌐 Full URL:', window.location.origin + url);
            
            const response = await fetch(url, {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            console.log('📡 Response status:', response.status);
            console.log('📡 Response ok:', response.ok);
            console.log('📡 Response statusText:', response.statusText);
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error('❌ Response error text:', errorText);
                throw new Error(`HTTP ${response.status}: ${response.statusText} - ${errorText}`);
            }
            
            const data = await response.json();
            console.log('📋 Response data:', data);
            
            if (data.success) {
                this.notifications = data.notifications;
                this.renderNotifications();
                this.updateUnreadCount();
                console.log('✅ Notifications loaded successfully');
            } else {
                console.error('❌ Failed to load notifications:', data.message);
                this.showError('Failed to load notifications: ' + (data.message || 'Unknown error'));
            }
        } catch (error) {
            console.error('❌ Error loading notifications:', error);
            console.error('❌ Error details:', {
                name: error.name,
                message: error.message,
                stack: error.stack
            });
            this.showError('Network error loading notifications: ' + error.message);
        }
    }
    
    async updateUnreadCount() {
        try {
            const url = '/api/notifications/count';
            console.log('🔄 Updating unread count...');
            console.log('🌐 Count URL:', url);
            console.log('🌐 Full Count URL:', window.location.origin + url);
            
            const response = await fetch(url, {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            console.log('📊 Count response status:', response.status);
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error('❌ Count response error text:', errorText);
                throw new Error(`HTTP ${response.status}: ${response.statusText} - ${errorText}`);
            }
            
            const data = await response.json();
            console.log('📊 Count response data:', data);
            
            if (data.success) {
                this.unreadCount = data.count;
                this.updateBadge();
                console.log('✅ Unread count updated:', data.count);
            } else {
                console.error('❌ Failed to get unread count:', data.message);
            }
        } catch (error) {
            console.error('❌ Error updating unread count:', error);
            console.error('❌ Count error details:', {
                name: error.name,
                message: error.message,
                stack: error.stack
            });
        }
    }
    
    updateBadge() {
        const badge = document.getElementById('universalNotificationBadge') ||
                     document.getElementById('notificationBadge') ||
                     document.querySelector('.notification-badge');
        
        if (badge) {
            if (this.unreadCount > 0) {
                badge.textContent = this.unreadCount > 99 ? '99+' : this.unreadCount;
                badge.style.display = 'flex';
            } else {
                badge.style.display = 'none';
            }
            console.log('✅ Badge updated:', this.unreadCount);
        } else {
            console.warn('⚠️ Notification badge not found');
        }
    }
    
    renderNotifications() {
        const notificationList = document.getElementById('universalNotificationList') ||
                                 document.getElementById('notificationList') ||
                                 document.querySelector('.notification-list');
        
        if (!notificationList) {
            console.warn('⚠️ Notification list element not found');
            return;
        }
        
        if (this.notifications.length === 0) {
            notificationList.innerHTML = `
                <div class="notification-empty">
                    <i class="fas fa-bell-slash"></i>
                    <p>No notifications</p>
                </div>
            `;
            return;
        }
        
        const notificationHTML = this.notifications.map(notification => 
            this.createNotificationHTML(notification)
        ).join('');
        
        notificationList.innerHTML = notificationHTML;
        
        // Bind click events to notifications
        this.bindNotificationEvents();
    }
    
    createNotificationHTML(notification) {
        const isUnread = !notification.is_read;
        const clickableClass = notification.is_clickable ? 'clickable' : '';
        const unreadClass = isUnread ? 'unread' : '';
        
        return `
            <div class="notification-item ${unreadClass} ${clickableClass}" 
                 data-notification-id="${notification.id}"
                 data-action-url="${notification.action_url || ''}"
                 ${notification.is_clickable ? 'role="button" tabindex="0"' : ''}>
                <div class="notification-icon">
                    <i class="${notification.icon}"></i>
                </div>
                <div class="notification-content">
                    <div class="notification-title">${this.escapeHtml(notification.title)}</div>
                    <div class="notification-message">${this.escapeHtml(notification.message)}</div>
                    <div class="notification-time">${notification.formatted_time}</div>
                </div>
                ${isUnread ? '<div class="notification-unread-indicator"></div>' : ''}
            </div>
        `;
    }
    
    bindNotificationEvents() {
        const notificationItems = document.querySelectorAll('.notification-item.clickable');
        notificationItems.forEach(item => {
            item.addEventListener('click', () => this.handleNotificationClick(item));
            item.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    this.handleNotificationClick(item);
                }
            });
        });
    }
    
    async handleNotificationClick(notificationElement) {
        const notificationId = notificationElement.dataset.notificationId;
        const actionUrl = notificationElement.dataset.actionUrl;
        
        // Mark as read
        await this.markAsRead(notificationId);
        
        // Perform action
        if (actionUrl && actionUrl !== 'null' && actionUrl !== '') {
            // If it's a tab action (starts with #), switch tabs
            if (actionUrl.startsWith('#')) {
                const tabName = actionUrl.substring(1);
                this.switchToTab(tabName);
            } else {
                // Navigate to URL
                window.location.href = actionUrl;
            }
        }
        
        // Hide notification panel
        this.hideNotificationPanel();
    }
    
    switchToTab(tabName) {
        // Special handling for admin dashboard approve users section
        if (tabName === 'approve-users') {
            // Check if we're on admin dashboard and showApproveUsers function exists
            if (typeof showApproveUsers === 'function') {
                showApproveUsers();
                return;
            }
            // Fallback: try to click the approve user button
            const approveUserBtn = document.getElementById('approveUserBtn');
            if (approveUserBtn) {
                approveUserBtn.click();
                return;
            }
        }
        
        // Special handling for health officer clinical interview section
        if (tabName === 'clinical-interview') {
            // Check if we're on health officer dashboard
            const isHealthOfficerDashboard = document.body.dataset.userRole === 'healthofficer' ||
                                           document.querySelector('[data-user-role="healthofficer"]') ||
                                           document.querySelector('[onclick*="clinical-interview"]');
            
            if (isHealthOfficerDashboard && typeof showSection === 'function') {
                console.log('🔄 Navigating to health officer clinical interview section');
                
                // First navigate to clinical interview tab
                const clinicalInterviewTab = document.querySelector('[onclick*="clinical-interview"]');
                if (clinicalInterviewTab) {
                    clinicalInterviewTab.click();
                    
                    // Then scroll to the history table after a short delay
                    setTimeout(() => {
                        const historyTable = document.getElementById('clinicalInterviewTable');
                        if (historyTable) {
                            console.log('✅ Scrolling to clinical interview history table');
                            historyTable.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            
                            // Add a subtle highlight effect to draw attention
                            const historyCard = historyTable.closest('.card');
                            if (historyCard) {
                                historyCard.style.transition = 'box-shadow 0.3s ease';
                                historyCard.style.boxShadow = '0 0 20px rgba(0, 120, 212, 0.3)';
                                setTimeout(() => {
                                    historyCard.style.boxShadow = '';
                                }, 2000);
                            }
                        }
                    }, 300);
                }
                return;
            }
            
            // Fallback: try to click the clinical interview tab directly
            const clinicalInterviewTab = document.querySelector('[onclick*="clinical-interview"]');
            if (clinicalInterviewTab) {
                clinicalInterviewTab.click();
                return;
            }
        }
        
        // Special handling for health officer dashboard feedback sections
        if (tabName === 'reception-feedback' || tabName === 'send-to-admin' || tabName === 'xray-specialist-feedback') {
            // Check if we're on health officer dashboard
            const isHealthOfficerDashboard = document.body.dataset.userRole === 'healthofficer' ||
                                           document.querySelector('[data-user-role="healthofficer"]') ||
                                           document.querySelector('[onclick*="showFeedbackSection"]');
            
            if (isHealthOfficerDashboard && typeof showFeedbackSection === 'function') {
                console.log(`🔄 Navigating to health officer ${tabName} section`);
                
                // First navigate to feedback tab
                const feedbackTab = document.querySelector('[onclick*="feedback"]') ||
                                   document.querySelector('[onclick*="showSection(\'feedback\'"]');
                if (feedbackTab) {
                    feedbackTab.click();
                }
                
                // Then show the specific feedback section
                setTimeout(() => {
                    let sectionName = tabName;
                    // Map action URLs to actual section names
                    if (tabName === 'reception-feedback') {
                        sectionName = 'receptionist-feedback';
                    } else if (tabName === 'send-to-admin') {
                        sectionName = 'send-to-admin';
                    } else if (tabName === 'xray-specialist-feedback') {
                        sectionName = 'xray-specialist-feedback';
                    }
                    
                    console.log(`✅ Switching to ${sectionName} section`);
                    showFeedbackSection(sectionName);
                }, 200);
                return;
            }
            
            // Fallback: try to click the feedback tab
            const feedbackTab = document.querySelector('[onclick*="feedback"]');
            if (feedbackTab) {
                feedbackTab.click();
                return;
            }
        }
        
        // Special handling for health officer dashboard assigned patients section
        if (tabName === 'assigned-patients') {
            // Check if we're on health officer dashboard and showSection function exists
            if (typeof showSection === 'function') {
                // Navigate to assigned patients section
                const assignedPatientsTab = document.querySelector('[onclick*="assigned-patients"]');
                if (assignedPatientsTab) {
                    showSection('assigned-patients', assignedPatientsTab);
                    return;
                }
            }
            // Fallback: try to click the assigned patients tab directly
            const assignedPatientsTab = document.querySelector('[onclick*="assigned-patients"]');
            if (assignedPatientsTab) {
                assignedPatientsTab.click();
                return;
            }
        }
        
        // Special handling for X-ray specialist dashboard assigned patients section
        if (tabName === 'assigned-patients' && document.body.dataset.userRole === 'xrayspecialist') {
            const assignedPatientsTab = document.querySelector('[data-tab="assigned-patients"]') ||
                                       document.querySelector('[onclick*="assigned-patients"]');
            if (assignedPatientsTab) {
                assignedPatientsTab.click();
                return;
            }
        }
        
        // Special handling for doctor dashboard appointment section (for X-ray images)
        if (tabName === 'appointment' && document.body.dataset.userRole === 'doctor') {
            const appointmentTab = document.querySelector('[data-tab="appointment"]') ||
                                  document.querySelector('[onclick*="appointment"]');
            if (appointmentTab) {
                appointmentTab.click();
                return;
            }
        }
        
        // Special handling for patient dashboard results section
        if (tabName === 'results' && document.body.dataset.userRole === 'patient') {
            const resultsTab = document.querySelector('[data-tab="results"]') ||
                              document.querySelector('[onclick*="results"]') ||
                              document.querySelector('[onclick*="showSection(\'results\'"]');
            if (resultsTab) {
                resultsTab.click();
                return;
            }
        }
        
        // Special handling for notes section (X-ray specialists)
        if (tabName === 'notes') {
            const notesTab = document.querySelector('[data-tab="notes"]') ||
                            document.querySelector('[onclick*="notes"]') ||
                            document.querySelector('[onclick*="showSection(\'notes\'"]');
            if (notesTab) {
                notesTab.click();
                return;
            }
        }
        
        // Special handling for reception dashboard feedback section
        if (tabName === 'feedback') {
            // Check if we're on reception dashboard and showSection function exists
            if (typeof showSection === 'function') {
                // Check if this is reception dashboard by looking for reception-specific elements
                const isReceptionDashboard = document.body.dataset.userRole === 'reception' ||
                                           document.querySelector('[data-user-role="reception"]') ||
                                           document.querySelector('.reception-dashboard') ||
                                           document.querySelector('li[onclick*="showSection(\'feedback\'"]');
                
                if (isReceptionDashboard) {
                    console.log('🔄 Navigating to reception feedback section');
                    
                    // First navigate to feedback section
                    const feedbackSidebarItem = document.querySelector('li[onclick*="showSection(\'feedback\'"]');
                    
                    if (feedbackSidebarItem) {
                        console.log('✅ Found feedback sidebar item, clicking it');
                        feedbackSidebarItem.click();
                        
                        // Then switch to "Send to Admin" tab where admin replies are shown
                        setTimeout(() => {
                            console.log('🔄 Switching to Send to Admin tab for admin replies');
                            const sendToAdminBtn = document.querySelector('[onclick="showFeedbackSection(\'send-to-admin\')"]');
                            if (sendToAdminBtn) {
                                console.log('✅ Found Send to Admin button, clicking it');
                                sendToAdminBtn.click();
                            } else {
                                console.warn('⚠️ Send to Admin button not found');
                                // Fallback: try to call showFeedbackSection directly
                                if (typeof showFeedbackSection === 'function') {
                                    console.log('🔄 Using direct showFeedbackSection call');
                                    showFeedbackSection('send-to-admin');
                                }
                            }
                        }, 200);
                        return;
                    } else {
                        // Direct navigation using showSection function
                        console.log('🔄 Using direct showSection navigation');
                        showSection('feedback', null);
                        
                        // Then switch to admin tab
                        setTimeout(() => {
                            const sendToAdminBtn = document.querySelector('[onclick="showFeedbackSection(\'send-to-admin\')"]');
                            if (sendToAdminBtn) {
                                sendToAdminBtn.click();
                            }
                        }, 200);
                        return;
                    }
                }
            }
        }
        
        // Try to find and click the tab
        const tabButton = document.querySelector(`[data-tab="${tabName}"]`);
        if (tabButton) {
            tabButton.click();
        } else {
            // Fallback: try to show the tab content directly
            const tabContent = document.getElementById(tabName);
            if (tabContent) {
                // Hide all tab contents
                document.querySelectorAll('.tab-content').forEach(content => {
                    content.classList.remove('active');
                    content.style.display = 'none';
                });
                
                // Show target tab
                tabContent.classList.add('active');
                tabContent.style.display = 'block';
                
                // Update active tab button
                document.querySelectorAll('.nav-item').forEach(item => {
                    item.classList.remove('active');
                });
                
                const targetTabButton = document.querySelector(`[data-tab="${tabName}"]`);
                if (targetTabButton) {
                    targetTabButton.classList.add('active');
                }
            }
        }
    }
    
    async markAsRead(notificationId) {
        try {
            const response = await fetch(`/api/notifications/${notificationId}/mark-read`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            const data = await response.json();
            if (data.success) {
                // Update local notification state
                const notification = this.notifications.find(n => n.id == notificationId);
                if (notification) {
                    notification.is_read = true;
                }
                
                // Update UI
                this.updateUnreadCount();
                this.renderNotifications();
            }
        } catch (error) {
            console.error('Error marking notification as read:', error);
        }
    }
    
    async markAllAsRead() {
        try {
            const response = await fetch('/api/notifications/mark-all-read', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            const data = await response.json();
            if (data.success) {
                // Update local state
                this.notifications.forEach(notification => {
                    notification.is_read = true;
                });
                
                // Update UI
                this.unreadCount = 0;
                this.updateBadge();
                this.renderNotifications();
                
                this.showSuccess(`Marked ${data.count} notifications as read`);
            } else {
                this.showError('Failed to mark notifications as read');
            }
        } catch (error) {
            console.error('Error marking all notifications as read:', error);
            this.showError('Network error');
        }
    }
    
    async clearAllNotifications() {
        if (!confirm('Are you sure you want to clear all notifications? This action cannot be undone.')) {
            return;
        }
        
        try {
            const response = await fetch('/api/notifications/clear-all', {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            const data = await response.json();
            if (data.success) {
                // Update local state
                this.notifications = [];
                this.unreadCount = 0;
                
                // Update UI
                this.updateBadge();
                this.renderNotifications();
                
                this.showSuccess(`Cleared ${data.count} notifications`);
            } else {
                this.showError('Failed to clear notifications');
            }
        } catch (error) {
            console.error('Error clearing notifications:', error);
            this.showError('Network error');
        }
    }
    
    toggleNotificationPanel() {
        if (this.notificationPanel.classList.contains('active')) {
            this.hideNotificationPanel();
        } else {
            this.showNotificationPanel();
        }
    }
    
    showNotificationPanel() {
        if (this.notificationPanel) {
            this.notificationPanel.classList.add('active');
            this.loadNotifications(); // Refresh when opening
        }
    }
    
    hideNotificationPanel() {
        if (this.notificationPanel) {
            this.notificationPanel.classList.remove('active');
        }
    }
    
    startPolling() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
        }
        
        this.pollTimer = setInterval(() => {
            this.updateUnreadCount();
            
            // If panel is open, refresh notifications
            if (this.notificationPanel.classList.contains('active')) {
                this.loadNotifications();
            }
        }, this.options.pollInterval);
    }
    
    stopPolling() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
    }
    
    showSuccess(message) {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                toast: true,
                position: 'top-end',
                icon: 'success',
                title: message,
                showConfirmButton: false,
                timer: 3000
            });
        } else {
            console.log('Success:', message);
        }
    }
    
    showError(message) {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                toast: true,
                position: 'top-end',
                icon: 'error',
                title: message,
                showConfirmButton: true,
                confirmButtonText: 'Retry',
                timer: 5000
            }).then((result) => {
                if (result.isConfirmed) {
                    this.loadNotifications();
                }
            });
        } else {
            console.error('Error:', message);
            // Fallback: show a simple alert
            alert('Notification Error: ' + message + '\n\nClick OK to retry.');
            this.loadNotifications();
        }
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // Public methods for external use
    refresh() {
        console.log('🔄 Manual refresh requested');
        this.loadNotifications();
    }
    
    createTestNotification() {
        console.log('🔄 Creating test notification...');
        fetch('/api/notifications/test', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            console.log('📡 Test notification response status:', response.status);
            return response.json();
        })
        .then(data => {
            console.log('📋 Test notification response:', data);
            if (data.success) {
                this.showSuccess('Test notification created successfully');
                setTimeout(() => this.refresh(), 1000);
            } else {
                this.showError('Failed to create test notification: ' + (data.message || 'Unknown error'));
            }
        })
        .catch(error => {
            console.error('❌ Error creating test notification:', error);
            this.showError('Network error creating test notification: ' + error.message);
        });
    }
    
    // Debug method for troubleshooting
    debugNotificationSystem() {
        console.log('🔍 Notification System Debug Info:');
        console.log('- Initialized:', this.isInitialized);
        console.log('- Notifications count:', this.notifications.length);
        console.log('- Unread count:', this.unreadCount);
        console.log('- Bell element:', this.notificationBell);
        console.log('- Panel element:', this.notificationPanel);
        console.log('- Options:', this.options);
        
        // Test API connectivity
        this.createTestNotification();
    }
    
    destroy() {
        this.stopPolling();
        
        if (this.notificationBell) {
            this.notificationBell.remove();
        }
        
        if (this.notificationPanel) {
            this.notificationPanel.remove();
        }
        
        this.isInitialized = false;
    }
}

// Global instance
let universalNotifications = null;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Only initialize if user is logged in (check for current_user or similar)
    if (document.body.dataset.userRole || document.querySelector('.main-content')) {
        try {
            console.log('🔄 Initializing Universal Notification System...');
            console.log('👤 User role:', document.body.dataset.userRole);
            console.log('🌐 Current URL:', window.location.href);
            console.log('📄 Document title:', document.title);
            
            universalNotifications = new UniversalNotificationSystem();
            
            // Make it globally accessible for debugging
            window.universalNotifications = universalNotifications;
            
            console.log('✅ Universal Notification System initialized successfully');
            
            // Test API connectivity with more detailed logging
            setTimeout(() => {
                console.log('🔍 Testing basic API connectivity...');
                
                // First test a simple route without authentication
                fetch('/api/test')
                    .then(response => {
                        console.log('🔍 Basic API test status:', response.status);
                        return response.json();
                    })
                    .then(data => {
                        console.log('🔍 Basic API test response:', data);
                        
                        // If basic API works, test the notification debug endpoint
                        if (data.success) {
                            console.log('✅ Basic API works, testing notification API...');
                            
                            const debugUrl = '/api/notifications/debug';
                            console.log('🌐 Debug URL:', debugUrl);
                            console.log('🌐 Full Debug URL:', window.location.origin + debugUrl);
                            
                            return fetch(debugUrl, {
                                method: 'GET',
                                credentials: 'same-origin',
                                headers: {
                                    'Accept': 'application/json',
                                    'Content-Type': 'application/json'
                                }
                            });
                        } else {
                            throw new Error('Basic API test failed');
                        }
                    })
                    .then(response => {
                        console.log('🔍 Notification API Debug Response Status:', response.status);
                        if (!response.ok) {
                            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                        }
                        return response.json();
                    })
                    .then(data => {
                        console.log('🔍 Notification API Debug Response Data:', data);
                        if (!data.success) {
                            console.error('❌ Notification API Debug failed:', data.message);
                        } else {
                            console.log('✅ Notification API connectivity test passed');
                        }
                    })
                    .catch(error => {
                        console.error('❌ API connectivity test error:', error);
                        console.error('❌ Error details:', {
                            name: error.name,
                            message: error.message,
                            stack: error.stack
                        });
                    });
            }, 2000);
            
        } catch (error) {
            console.error('❌ Failed to initialize Universal Notification System:', error);
            console.error('❌ Initialization error details:', {
                name: error.name,
                message: error.message,
                stack: error.stack
            });
        }
    } else {
        console.log('⚠️ Universal Notification System not initialized - no user role or main content found');
        console.log('🔍 Body dataset:', document.body.dataset);
        console.log('🔍 Main content element:', document.querySelector('.main-content'));
    }
});

// Global debug functions for troubleshooting
window.debugNotifications = function() {
    if (window.universalNotifications) {
        window.universalNotifications.debugNotificationSystem();
    } else {
        console.error('❌ Universal Notification System not initialized');
        console.log('🔍 Available debug info:');
        console.log('- User role:', document.body.dataset.userRole);
        console.log('- Main content:', document.querySelector('.main-content'));
        console.log('- Current URL:', window.location.href);
    }
    
    // Check for duplicate notification bells
    const allBells = document.querySelectorAll('.notification-bell');
    console.log(`🔔 Found ${allBells.length} notification bell(s):`);
    allBells.forEach((bell, index) => {
        console.log(`  ${index + 1}. ID: ${bell.id || 'no-id'}, Classes: ${bell.className}`);
    });
    
    // Check for notification panels
    const allPanels = document.querySelectorAll('.notification-panel');
    console.log(`📋 Found ${allPanels.length} notification panel(s):`);
    allPanels.forEach((panel, index) => {
        console.log(`  ${index + 1}. ID: ${panel.id || 'no-id'}, Classes: ${panel.className}`);
    });
};

window.testNotifications = function() {
    if (window.universalNotifications) {
        window.universalNotifications.createTestNotification();
    } else {
        console.error('❌ Universal Notification System not initialized');
    }
};

window.refreshNotifications = function() {
    if (window.universalNotifications) {
        window.universalNotifications.refresh();
    } else {
        console.error('❌ Universal Notification System not initialized');
    }
};

window.testReceptionFeedbackNavigation = function() {
    console.log('🧪 Testing reception feedback navigation...');
    console.log('- Body dataset userRole:', document.body.dataset.userRole);
    console.log('- Reception element check:', document.querySelector('[data-user-role="reception"]'));
    console.log('- Feedback sidebar item:', document.querySelector('li[onclick*="showSection(\'feedback\'"]'));
    console.log('- Send to Admin button:', document.querySelector('[onclick="showFeedbackSection(\'send-to-admin\')"]'));
    console.log('- showSection function available:', typeof showSection);
    console.log('- showFeedbackSection function available:', typeof showFeedbackSection);
    
    if (window.universalNotifications) {
        console.log('🔄 Testing navigation to feedback section...');
        window.universalNotifications.switchToTab('feedback');
    } else {
        console.error('❌ Universal Notification System not available');
    }
};

window.testHealthOfficerFeedbackNavigation = function() {
    console.log('🧪 Testing health officer feedback navigation...');
    console.log('- Body dataset userRole:', document.body.dataset.userRole);
    console.log('- Health officer element check:', document.querySelector('[data-user-role="healthofficer"]'));
    console.log('- Feedback sidebar item:', document.querySelector('[onclick*="feedback"]'));
    console.log('- showFeedbackSection function available:', typeof showFeedbackSection);
    
    // Test all three feedback sections
    const sections = ['reception-feedback', 'send-to-admin', 'xray-specialist-feedback'];
    sections.forEach(section => {
        console.log(`- ${section} button:`, document.querySelector(`[onclick="showFeedbackSection('${section.replace('-', '-')}')"]`));
    });
    
    if (window.universalNotifications) {
        console.log('🔄 Testing navigation to reception feedback...');
        window.universalNotifications.switchToTab('reception-feedback');
        
        setTimeout(() => {
            console.log('🔄 Testing navigation to admin feedback...');
            window.universalNotifications.switchToTab('send-to-admin');
        }, 1000);
        
        setTimeout(() => {
            console.log('🔄 Testing navigation to X-ray specialist feedback...');
            window.universalNotifications.switchToTab('xray-specialist-feedback');
        }, 2000);
    } else {
        console.error('❌ Universal Notification System not available');
    }
};

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = UniversalNotificationSystem;
}