# Design Document

## Overview

This design implements email validation and notification functionality for the patient registration system. The solution extends the existing registration form with email input, validates email format and uniqueness, and integrates with the notification system for account approval and password reset workflows.

## Architecture

The email functionality integrates with the existing Flask-based web application architecture:

- **Frontend Layer**: Enhanced registration form with email input and client-side validation
- **Backend Layer**: Email validation service, notification service, and verification code management
- **Database Layer**: Utilizes existing Patient model email field and adds verification code storage
- **External Services**: Email sending capability through SMTP or email service provider

## Components and Interfaces

### Email Validator Component
- **Purpose**: Validates email format and checks for duplicates
- **Interface**: `validate_email(email: str) -> ValidationResult`
- **Methods**:
  - `is_valid_format(email: str) -> bool`: Validates email format using regex
  - `is_unique_email(email: str) -> bool`: Checks database for existing email
  - `normalize_email(email: str) -> str`: Converts to lowercase and trims whitespace

### Notification Service Component
- **Purpose**: Sends email notifications for account approval and verification codes
- **Interface**: `send_notification(email: str, template: str, data: dict) -> bool`
- **Methods**:
  - `send_approval_notification(user: User) -> bool`: Sends account approval email
  - `send_verification_code(email: str, code: str) -> bool`: Sends password reset code
  - `get_email_template(template_name: str) -> str`: Retrieves email templates

### Verification Service Component
- **Purpose**: Manages verification codes for password reset
- **Interface**: `generate_code(email: str) -> str`, `validate_code(email: str, code: str) -> bool`
- **Methods**:
  - `generate_verification_code() -> str`: Creates 6-digit random code
  - `store_code(email: str, code: str) -> bool`: Stores code with expiration
  - `is_code_valid(email: str, code: str) -> bool`: Validates code and expiration

### Enhanced Registration Form
- **Purpose**: Collects email input with validation feedback
- **Interface**: HTML form with JavaScript validation
- **Features**:
  - Email input field with proper HTML5 validation
  - Real-time format validation feedback
  - Integration with existing form validation flow

## Data Models

### Existing Patient Model Enhancement
The Patient model already contains an email field that will be utilized:
```python
email = db.Column(db.String(120), nullable=True, index=True)
```

### New Verification Code Model
```python
class VerificationCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    code = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*
Based on the prework analysis, I'll consolidate related properties and eliminate redundancy:

**Property Reflection:**
- Properties 1.2, 1.3, 4.1, and 4.2 all test email format validation and can be combined into a comprehensive email validation property
- Properties 1.4 and 4.4 both test email storage and can be combined into an email storage property
- Properties 3.1, 3.3, and 4.5 all test verification code behavior and can be combined
- Properties 2.1 and 2.2 test notification sending and content, which can be combined
- Properties 5.2, 5.3, and 5.4 all test form validation behavior and can be combined

Property 1: Email format validation
*For any* email string input, the Email_Validator should accept valid email formats (containing @ symbol, valid local part with letters/numbers/dots/hyphens/underscores, valid domain with dot and TLD) and reject invalid formats
**Validates: Requirements 1.2, 1.3, 4.1, 4.2**

Property 2: Email storage and normalization
*For any* valid email submitted during registration, the system should store the email in lowercase in the Patient_Profile
**Validates: Requirements 1.4, 4.4**

Property 3: Email uniqueness validation
*For any* email address, attempting to register with an email that already exists (case-insensitive) should be rejected with a duplicate error message
**Validates: Requirements 1.5, 4.3**

Property 4: Verification code lifecycle
*For any* password reset request, the system should generate a unique 6-digit code that becomes invalid after 15 minutes and can only be used once
**Validates: Requirements 3.1, 3.3, 4.5**

Property 5: Notification sending on approval
*For any* user account with an email address, when approved by an administrator, an approval email containing the username should be sent to the registered email
**Validates: Requirements 2.1, 2.2**

Property 6: Error handling resilience
*For any* email sending failure, the system should log the error but continue with the approval process without blocking
**Validates: Requirements 2.3**

Property 7: Form validation integration
*For any* registration form submission with validation errors, email validation should occur first and preserve all other form data for correction
**Validates: Requirements 5.2, 5.3, 5.4**

Property 8: Role-based email requirements
*For any* user registration, email should be optional for non-patient roles while maintaining system functionality
**Validates: Requirements 5.5**

## Error Handling

### Email Validation Errors
- Invalid format: Display user-friendly error message with format requirements
- Duplicate email: Show specific error indicating email is already registered
- Network issues: Graceful degradation with retry mechanisms

### Email Sending Errors
- SMTP failures: Log error, continue with process, notify administrators
- Invalid email addresses: Skip sending, log warning
- Rate limiting: Implement exponential backoff for retries

### Verification Code Errors
- Expired codes: Clear error message with option to request new code
- Invalid codes: Show error without revealing valid code format
- Multiple attempts: Implement rate limiting to prevent brute force

## Testing Strategy

### Unit Testing
- Email format validation with various valid/invalid inputs
- Database operations for email storage and retrieval
- Verification code generation and validation logic
- Email template rendering with different user data
- Error handling scenarios for each component

### Property-Based Testing
The testing strategy will use Hypothesis for Python to implement property-based tests. Each correctness property will be implemented as a separate test that runs a minimum of 100 iterations with randomly generated inputs.

**Property-based testing requirements:**
- Use Hypothesis library for generating test data
- Configure each test to run minimum 100 iterations
- Tag each test with corresponding design property reference
- Generate realistic email addresses, usernames, and verification codes
- Test edge cases through strategic generators

**Integration Testing:**
- End-to-end registration flow with email validation
- Email sending integration with mock SMTP server
- Password reset workflow from request to completion
- Admin approval workflow with email notifications

**Performance Considerations:**
- Email validation should complete within 100ms
- Database queries should use proper indexing on email fields
- Email sending should be asynchronous to avoid blocking registration
- Verification codes should have efficient cleanup of expired entries

## Security Considerations

### Email Privacy
- Store emails in encrypted format if required by regulations
- Implement proper access controls for email data
- Log email access for audit purposes

### Verification Code Security
- Use cryptographically secure random number generation
- Implement rate limiting for code generation requests
- Clear codes from memory after validation
- Prevent timing attacks in code validation

### Input Sanitization
- Sanitize email inputs to prevent injection attacks
- Validate email length to prevent buffer overflow
- Escape email content in templates to prevent XSS

## Implementation Notes

### Database Migration
- Add indexes to email columns for performance
- Implement migration script for existing users
- Ensure backward compatibility during deployment

### Email Templates
- Create responsive HTML email templates
- Support multiple languages for international users
- Include proper unsubscribe mechanisms where required

### Configuration
- Make email settings configurable through environment variables
- Support multiple email providers (SMTP, SendGrid, etc.)
- Allow customization of verification code expiration time

### Monitoring
- Track email delivery success rates
- Monitor verification code usage patterns
- Alert on unusual email validation failure rates