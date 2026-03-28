# Implementation Plan

- [x] 1. Set up email validation infrastructure


  - Create email validation utility functions with regex patterns
  - Add email uniqueness checking across all user roles
  - Implement email normalization (lowercase conversion)
  - _Requirements: 1.2, 1.5, 4.1, 4.2, 4.3, 4.4_

- [ ]* 1.1 Write property test for email format validation
  - **Property 1: Email format validation**
  - **Validates: Requirements 1.2, 1.3, 4.1, 4.2**

- [ ]* 1.2 Write property test for email uniqueness validation
  - **Property 3: Email uniqueness validation**
  - **Validates: Requirements 1.5, 4.3**



- [ ] 2. Enhance registration form with email field
  - Add email input field to registration template below phone number
  - Implement client-side email format validation with JavaScript
  - Integrate email validation with existing form validation flow
  - Add email field styling consistent with existing form design
  - _Requirements: 1.1, 1.2, 1.3, 5.2, 5.3, 5.4_

- [ ]* 2.1 Write property test for email storage and normalization
  - **Property 2: Email storage and normalization**
  - **Validates: Requirements 1.4, 4.4**

- [x]* 2.2 Write property test for form validation integration


  - **Property 7: Form validation integration**
  - **Validates: Requirements 5.2, 5.3, 5.4**

- [ ] 3. Update registration backend logic
  - Modify registration route to handle email field
  - Add email validation to registration form processing
  - Update user creation functions to store email in Patient profile
  - Implement role-based email requirements (optional for non-patients)
  - _Requirements: 1.4, 1.5, 5.5_


- [ ]* 3.1 Write property test for role-based email requirements
  - **Property 8: Role-based email requirements**
  - **Validates: Requirements 5.5**

- [ ] 4. Create verification code system
  - Create VerificationCode database model
  - Implement verification code generation (6-digit random codes)
  - Add code storage with 15-minute expiration
  - Create code validation and cleanup functions


  - _Requirements: 3.1, 3.3, 4.5_

- [ ]* 4.1 Write property test for verification code lifecycle
  - **Property 4: Verification code lifecycle**
  - **Validates: Requirements 3.1, 3.3, 4.5**

- [ ] 5. Implement email notification service
  - Create email sending utility functions
  - Design email templates for account approval notifications
  - Design email templates for verification code delivery
  - Add error handling and logging for email failures
  - _Requirements: 2.1, 2.2, 2.3, 3.2_






- [ ]* 5.1 Write property test for notification sending on approval
  - **Property 5: Notification sending on approval**
  - **Validates: Requirements 2.1, 2.2**

- [x]* 5.2 Write property test for error handling resilience


  - **Property 6: Error handling resilience**
  - **Validates: Requirements 2.3**

- [ ] 6. Integrate email notifications with admin approval workflow
  - Modify admin approval functions to send email notifications
  - Add email sending to user approval process


  - Handle cases where users have no email address
  - Ensure approval process continues even if email fails
  - _Requirements: 2.1, 2.2, 2.3, 2.4_


- [ ] 7. Implement password reset with email verification
  - Create password reset request form and route
  - Add verification code sending to password reset flow
  - Create verification code validation form and route
  - Implement new password setting after successful verification
  - Add proper error handling for invalid/expired codes
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_




- [ ] 8. Add database migration for verification codes
  - Create database migration script for VerificationCode table
  - Add proper indexes for email and expiration queries
  - Ensure migration handles existing user data safely
  - _Requirements: 4.5, 5.1_

- [ ] 9. Update user interface for password reset
  - Create password reset request page
  - Create verification code entry page
  - Create new password setting page
  - Add proper error message display for all validation failures
  - Ensure UI maintains existing design consistency
  - _Requirements: 3.4, 3.5_

- [ ] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ]* 11. Create integration tests for complete email workflows
  - Write integration tests for registration with email validation
  - Write integration tests for admin approval with email notification
  - Write integration tests for password reset workflow
  - Write integration tests for error handling scenarios

- [ ]* 12. Add unit tests for email utility functions
  - Write unit tests for email format validation
  - Write unit tests for email normalization
  - Write unit tests for verification code generation
  - Write unit tests for email template rendering