# Requirements Document

## Introduction

The reception feedback system currently displays incorrect status messages when reception staff send feedback to Health Officers. When reception sends feedback to a Health Officer, the system incorrectly shows "Admin reply awaiting" instead of "Health Officer reply awaiting". This creates confusion about who is expected to respond to the feedback.

## Glossary

- **Reception Staff**: Healthcare reception personnel who can send feedback to various roles
- **Health Officer**: Healthcare professional who receives and responds to feedback from reception
- **Admin**: System administrator who receives and responds to feedback from various roles
- **Feedback System**: The communication system that allows staff to send messages and receive replies
- **Reply Status**: The displayed message indicating who is expected to respond to feedback

## Requirements

### Requirement 1

**User Story:** As a reception staff member, I want to see accurate reply status messages for my feedback, so that I know who is expected to respond to my messages.

#### Acceptance Criteria

1. WHEN reception staff sends feedback to a Health Officer THEN the system SHALL display "Health Officer reply awaiting" when no reply has been received
2. WHEN reception staff sends feedback to an Admin THEN the system SHALL display "Admin reply awaiting" when no reply has been received  
3. WHEN reception staff views their sent feedback list THEN the system SHALL show the correct recipient-specific reply status for each message
4. WHEN a Health Officer replies to reception feedback THEN the system SHALL display the reply content instead of the awaiting message
5. WHEN an Admin replies to reception feedback THEN the system SHALL display the reply content instead of the awaiting message

### Requirement 2

**User Story:** As a reception staff member, I want the feedback display to dynamically determine the correct reply status, so that the system accurately reflects the workflow regardless of recipient type.

#### Acceptance Criteria

1. WHEN the system displays feedback without replies THEN the system SHALL determine the correct awaiting message based on the recipient role
2. WHEN the recipient is a Health Officer THEN the system SHALL use "Health Officer reply awaiting" as the status message
3. WHEN the recipient is an Admin THEN the system SHALL use "Admin reply awaiting" as the status message
4. WHEN the system cannot determine the recipient role THEN the system SHALL use a generic "Reply awaiting" message
5. WHEN feedback has been replied to THEN the system SHALL display the actual reply content regardless of recipient type