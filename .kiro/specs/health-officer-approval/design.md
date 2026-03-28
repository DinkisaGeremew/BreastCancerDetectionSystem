# Design Document

## Overview

The Health Officer Approval System ensures that Health Officers must receive admin approval before accessing their dashboard. This design document outlines the architecture, components, and implementation details for a secure approval workflow that prevents unauthorized access while providing clear user feedback.

## Architecture

The approval system follows a role-based access control (RBAC) pattern with the following key components:

1. **Registration Layer**: Handles Health Officer account creation with pending status
2. **Authentication Layer**: Validates credentials and approval status during login
3. **Authorization Layer**: Enforces approval requirements before dashboard access
4. **Admin Interface**: Provides approval management functionality
5. **Notification System**: Communicates status changes to users and admins

## Components and Interfaces

### User Registration Component
- **Purpose**: Create Health Officer accounts with pending approval status
- **Interface**: Web form with validation and error handling
- **Dependencies**: User model, HealthOfficer model, notification system

### Authentication Service
- **Purpose**: Validate credentials and check approval status
- **Interface**: Login endpoint with multi-step validation
- **Dependencies**: User model, password hashing, session management

### Authorization Middleware
- **Purpose**: Enforce approval requirements for protected routes
- **Interface**: Decorator functions for route protection
- **Dependencies**: Flask-Login, session management

### Admin Approval Interface
- **Purpose**: Allow admins to review and approve pending accounts
- **Interface**: Admin dashboard with approval actions
- **Dependencies**: Admin model, notification system

## Data Models

### User Model Enhancement
```python
class User:
    id: Integer (Primary Key)
    username: String (Unique)
    phone: String (Unique)
    password_hash: String
    role: String
    is_approved: Boolean (Default: False for staff roles)
    is_active_user: Boolean (Default: True)
    date_created: DateTime
    last_login: DateTime
```

### HealthOfficer Profile Model
```python
class HealthOfficer:
    id: Integer (Primary Key)
    user_id: Integer (Foreign Key to User)
    employee_id: String (Unique, Optional)
    department: String
    specialization: String
    years_of_experience: Integer
    certification_level: String
    # ... other profile fields
```

### Notification Model
```python
class Notification:
    id: Integer (Primary Key)
    admin_id: Integer (Foreign Key)
    title: String
    message: Text
    notification_type: String
    is_read: Boolean (Default: False)
    created_at: DateTime
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

Property 1: Health Officer registration creates unapproved accounts
*For any* valid Health Officer registration data, creating the account should result in an account with is_approved set to false
**Validates: Requirements 1.1**

Property 2: Successful registration redirects to login
*For any* successful Health Officer registration, the system should redirect to the login page with appropriate messaging
**Validates: Requirements 1.2**

Property 3: Registration creates admin notifications
*For any* Health Officer account creation, the system should create a notification for administrators about the pending approval
**Validates: Requirements 1.3**

Property 4: Valid registration data is stored
*For any* valid Health Officer registration information, the system should store all provided profile data in the database
**Validates: Requirements 1.4**

Property 5: Invalid registration is rejected
*For any* invalid Health Officer registration data, the system should prevent account creation and display appropriate error messages
**Validates: Requirements 1.5**

Property 6: Pending accounts show approval message
*For any* Health Officer with pending approval status and correct credentials, login attempts should display "Your account is pending admin approval" message
**Validates: Requirements 2.1**

Property 7: Pending accounts cannot access dashboard
*For any* Health Officer with pending approval status, the system should prevent access to the dashboard regardless of correct credentials
**Validates: Requirements 2.2**

Property 8: Authentication errors are handled
*For any* Health Officer login attempt with incorrect credentials, the system should display appropriate error messages
**Validates: Requirements 2.4**

Property 9: Admin approval interface shows all pending
*For any* admin viewing the approval interface, the system should display all Health Officers with pending approval status
**Validates: Requirements 3.1**

Property 10: Admin approval updates status
*For any* admin approval action on a Health Officer account, the system should set the is_approved status to true
**Validates: Requirements 3.2**

Property 11: Approval creates notifications
*For any* Health Officer account approval by admin, the system should create a notification for the Health Officer
**Validates: Requirements 3.3**

Property 12: Approved accounts can login
*For any* Health Officer with approved status and correct credentials, the system should allow successful authentication
**Validates: Requirements 3.4, 4.1**

Property 13: Approved login redirects to dashboard
*For any* successful Health Officer login with approved status, the system should redirect to the Health Officer dashboard
**Validates: Requirements 4.2**

Property 14: Session expiration requires re-authentication
*For any* Health Officer with an expired session, accessing protected resources should require re-authentication
**Validates: Requirements 4.4**

Property 15: Logout clears session
*For any* Health Officer logout action, the system should clear the session and redirect to the login page
**Validates: Requirements 4.5**

Property 16: Approval checks apply to all staff roles
*For any* staff role user (doctor, xray specialist, reception, health officer), the system should verify approval status before allowing dashboard access
**Validates: Requirements 5.1**

Property 17: Bypass attempts are prevented
*For any* attempt to bypass approval checks, the system should prevent unauthorized access to protected resources
**Validates: Requirements 5.2**

Property 18: Status changes update database immediately
*For any* approval status change, the system should update the database record immediately
**Validates: Requirements 5.3**

Property 19: Login validates both authentication and approval
*For any* login attempt, the system should check both password correctness and approval status before granting access
**Validates: Requirements 5.4**

Property 20: Approval activities are logged
*For any* approval-related activity, the system should record the action in security logs
**Validates: Requirements 5.5**

## Error Handling

### Registration Errors
- **Invalid Input**: Display field-specific validation messages
- **Duplicate Accounts**: Prevent registration with existing username/phone
- **Database Errors**: Rollback transactions and display generic error message
- **Network Issues**: Provide retry mechanisms and offline indicators

### Authentication Errors
- **Invalid Credentials**: Display "Invalid username or password" message
- **Pending Approval**: Display "Your account is pending admin approval" message
- **Account Not Found**: Display "No account found for that username" message
- **Session Errors**: Clear invalid sessions and redirect to login

### Authorization Errors
- **Insufficient Permissions**: Redirect to appropriate dashboard or login
- **Expired Sessions**: Clear session and require re-authentication
- **Role Mismatches**: Log security events and deny access

### Admin Interface Errors
- **Approval Failures**: Display error messages and maintain current state
- **Notification Failures**: Log errors but continue with approval process
- **Database Conflicts**: Handle concurrent approval attempts gracefully

## Testing Strategy

### Unit Testing Approach
Unit tests will verify specific components and edge cases:
- User model validation and password hashing
- Registration form validation logic
- Authentication service credential checking
- Authorization middleware permission enforcement
- Admin approval action handlers
- Notification creation and delivery
- Database transaction handling
- Session management functionality

### Property-Based Testing Approach
Property-based tests will verify universal properties across all inputs using **Hypothesis** for Python:
- Each property-based test will run a minimum of 100 iterations
- Tests will generate random but valid input data
- Each test will be tagged with comments referencing the design document properties
- Property tests will use the format: **Feature: health-officer-approval, Property {number}: {property_text}**

**Property-Based Testing Requirements:**
- Use Hypothesis library for generating test data
- Configure tests to run 100+ iterations each
- Generate realistic user data (usernames, phones, passwords)
- Test approval state transitions comprehensively
- Verify security properties across all user roles
- Test concurrent access scenarios
- Validate error handling across input ranges

### Integration Testing
- End-to-end registration and approval workflows
- Cross-role permission verification
- Database consistency during concurrent operations
- Session management across multiple users
- Notification delivery and processing

### Security Testing
- Approval bypass attempt detection
- Session hijacking prevention
- Role escalation prevention
- Input sanitization verification
- Authentication timing attack resistance