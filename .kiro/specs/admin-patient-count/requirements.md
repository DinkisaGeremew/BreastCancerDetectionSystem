# Requirements Document

## Introduction

This feature adds the total number of registered patients to the Overview section of the admin dashboard. The admin dashboard currently displays counts for doctors, X-ray specialists, reception staff, and health officers, but is missing the patient count despite the data being available in the backend.

## Glossary

- **Admin Dashboard**: The administrative interface accessible only to users with admin role
- **Overview Section**: The main dashboard section displaying system statistics and information
- **Patient Count**: The total number of users registered with the "patient" role
- **Stats Container**: The grid layout displaying statistical information boxes

## Requirements

### Requirement 1

**User Story:** As an admin, I want to see the total number of registered patients in the overview section, so that I can have a complete view of all user types in the system.

#### Acceptance Criteria

1. WHEN an admin views the dashboard overview section, THE system SHALL display the total number of registered patients alongside other user role counts
2. WHEN the patient count is displayed, THE system SHALL use the same visual styling as other stat boxes (doctors, X-ray specialists, reception, health officers)
3. WHEN the patient count updates due to new registrations or deletions, THE displayed count SHALL reflect the current accurate total
4. WHEN the admin dashboard loads, THE patient count SHALL be positioned logically within the existing stats container layout
5. THE system SHALL maintain all existing functionality and visual design of the admin dashboard without disruption