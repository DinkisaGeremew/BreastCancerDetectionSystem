# Design Document

## Overview

The universal notification system provides a consistent, real-time notification experience across all user dashboards. It uses a unified data model with role-specific notification targeting and clickable actions. The system includes both backend APIs for notification management and frontend components for display and interaction.

## Architecture

The system follows a layered architecture:

1. **Data Layer**: Unified notification models for all user roles
2. **Service Layer**: Notification creation, retrieval, and management services
3. **API Layer**: RESTful endpoints for notification operations
4. **Frontend Layer**: Reusable notification components for all dashboards
5. **Real-time Layer**: WebSocket or polling for live updates

## Components and Interfaces

### Backend Components

#### Unified Notification Model
```python
class UniversalNotification:
    id: Integer (Primary Key)
    user_id: Integer (Foreign Key to User)
    user_role: String (reception, healthofficer, xrayspecialist, doctor, admin, patient)
    title: String (Notification title)
    message: Text (Notification content)
    notification_type: String (feedback, appointment, validation, system)
    is_read: Boolean (Read status)
    is_clickable: Boolean (Whether notification has action)
    action_url: String (URL to navigate when clicked)
    action_data: JSON (Additional data for actions)
    created_at: DateTime
    read_at: DateTime (When marked as read)
```

#### Notification Service
```python
class NotificationService:
    create_notification(user_id, role, title, message, type, action_url=None)
    get_notifications(user_id, role, limit=50)
    mark_as_read(notification_id, user_id)
    mark_all_as_read(user_id, role)
    clear_all_notifications(user_id, role)
    get_unread_count(user_id, role)
```

### Frontend Components

#### Notification Bell Component
- Displays unread count badge
- Toggles notification panel
- Updates in real-time
- Consistent styling across dashboards

#### Notification Panel Component
- Lists notifications with timestamps
- Handles click actions
- Provides management buttons (mark all read, clear all)
- Responsive design for mobile

#### Notification Item Component
- Displays title, message, and timestamp
- Handles individual click actions
- Shows read/unread status
- Supports different notification types

## Data Models

### UniversalNotification Table
```sql
CREATE TABLE universal_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    user_role VARCHAR(20) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    notification_type VARCHAR(50) NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    is_clickable BOOLEAN DEFAULT TRUE,
    action_url VARCHAR(500),
    action_data JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    read_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES user (id)
);
```

### Indexes for Performance
```sql
CREATE INDEX idx_user_notifications ON universal_notifications(user_id, user_role, created_at DESC);
CREATE INDEX idx_unread_notifications ON universal_notifications(user_id, is_read, created_at DESC);
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

<function_calls>
<invoke name="prework">
<parameter name="featureName">universal-notification-systemAft
er reviewing the prework analysis, I need to eliminate redundancy among the properties:

**Property Reflection:**
- Properties 2.2, 2.3, 2.4 are specific examples of 2.1 (navigation behavior) - will keep as examples
- Properties 4.2, 4.3, 4.4, 4.5 are specific examples of 4.1 (role targeting) - will keep as examples
- Properties about UI behavior (1.2, 1.4, 3.3, 3.4) can be consolidated into display consistency
- Properties about bulk operations (3.1, 3.2) are distinct and should remain separate

**Property 1: Role-based notification targeting**
*For any* notification-triggering event, the system should create notifications only for users whose roles are relevant to that event type
**Validates: Requirements 1.1, 4.1**

**Property 2: Notification count accuracy**
*For any* user with notifications, the notification bell should display the correct count of unread notifications
**Validates: Requirements 1.2, 1.4**

**Property 3: Notification panel display**
*For any* user clicking the notification bell, the system should display a panel containing all their notifications in chronological order (newest first)
**Validates: Requirements 1.3, 1.5**

**Property 4: Clickable notification actions**
*For any* clickable notification, clicking it should perform the appropriate action based on notification type and mark it as read
**Validates: Requirements 2.1, 2.5**

**Property 5: Bulk notification management**
*For any* user performing bulk actions (mark all as read, clear all), the system should update all notifications and refresh the UI accordingly
**Validates: Requirements 3.1, 3.2**

**Property 6: Visual state consistency**
*For any* notification state change (read/unread), the UI should immediately reflect the updated state including badge visibility
**Validates: Requirements 3.3, 3.4**

**Property 7: Session persistence**
*For any* notification read status, it should persist across user sessions and remain consistent after logout/login
**Validates: Requirements 3.5**

**Property 8: API consistency**
*For any* notification operation (create, retrieve, update, delete), the API should behave consistently across all user roles
**Validates: Requirements 5.1, 5.3, 5.4**

**Property 9: Notification type support**
*For any* supported notification type (feedback, appointment, validation, system), the system should handle creation, display, and actions correctly
**Validates: Requirements 5.2**

**Property 10: Data structure consistency**
*For any* notification created for any user role, it should follow the same data structure and validation rules
**Validates: Requirements 5.5**

## Error Handling

### Frontend Error Handling
- Network failure recovery with retry mechanisms
- Graceful degradation when notification service is unavailable
- User-friendly error messages for failed operations
- Offline notification queuing for later synchronization

### Backend Error Handling
- Database transaction rollback on notification creation failures
- Validation of user permissions before notification operations
- Rate limiting to prevent notification spam
- Comprehensive error logging for debugging

### Error Scenarios
1. **Network Failure**: Queue operations for retry when connection restored
2. **Invalid User**: Validate user existence and permissions before operations
3. **Database Error**: Rollback transactions and log detailed error information
4. **Permission Denied**: Return appropriate HTTP status codes with clear messages
5. **Rate Limiting**: Prevent excessive notification creation from single source

## Testing Strategy

### Unit Testing
- Test notification creation for different user roles and event types
- Test notification retrieval with various filters and sorting
- Test bulk operations (mark all read, clear all)
- Test permission validation and error handling

### Property-Based Testing
The system will use **pytest** with **hypothesis** library for property-based testing. Each property will run a minimum of 100 iterations to ensure comprehensive coverage.

**Property-based testing requirements:**
- Each correctness property will be implemented as a separate property-based test
- Tests will be tagged with comments referencing the design document properties
- Format: `# Feature: universal-notification-system, Property X: [property description]`
- Tests will generate random notification data and user scenarios
- Minimum 100 iterations per property test to ensure statistical confidence

### Integration Testing
- End-to-end notification flow from creation to user interaction
- Cross-dashboard notification consistency
- Real-time update verification
- Database persistence and retrieval accuracy

### Manual Testing
- User experience across different dashboards
- Notification timing and delivery
- Mobile responsiveness
- Accessibility compliance

## Implementation Phases

### Phase 1: Backend Infrastructure
1. Create UniversalNotification model
2. Implement NotificationService class
3. Create API endpoints for CRUD operations
4. Add database migrations

### Phase 2: Frontend Components
1. Create reusable notification bell component
2. Implement notification panel component
3. Add notification item component with click handling
4. Integrate components into existing dashboards

### Phase 3: Integration and Testing
1. Connect backend APIs to frontend components
2. Implement real-time updates
3. Add comprehensive testing
4. Performance optimization

### Phase 4: Migration and Deployment
1. Migrate existing notifications to new system
2. Update existing notification creation code
3. Deploy and monitor system performance
4. User training and documentation