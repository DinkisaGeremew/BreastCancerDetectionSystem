# Requirements Document

## Introduction

This feature modifies the existing registration system to restrict patient registration to reception staff only and adds a new "Health Officer" role to the public registration options. Currently, patients can self-register through the public registration page, but this needs to be changed so that only receptionists can register patients through their dashboard interface. Additionally, a new Health Officer role will be added to provide another staff category for the system.

## Glossary

- **Public Registration Page**: The main registration form accessible at `/register` that allows new users to create accounts
- **Reception Dashboard**: The authenticated interface used by reception staff to manage patient registrations
- **Patient Role**: A user role specifically for patients who receive medical services
- **Health Officer Role**: A new user role for health officers who work in the medical facility
- **Reception Staff**: Users with the 'reception' role who have permission to register patients
- **Self-Registration**: The ability for users to create their own accounts without staff assistance

## Requirements

### Requirement 1

**User Story:** As a system administrator, I want to restrict patient registration to reception staff only, so that patient account creation is controlled and managed by authorized personnel.

#### Acceptance Criteria

1. WHEN a user visits the public registration page, THE system SHALL exclude the patient role from the available role options
2. WHEN a user visits the public registration page, THE system SHALL include the health officer role in the available role options
3. WHEN a user attempts to submit a registration form with patient role, THE system SHALL reject the registration and display an error message
4. WHEN a user submits a registration form with health officer role, THE system SHALL create the health officer account successfully
5. WHEN reception staff access their dashboard, THE system SHALL provide patient registration functionality
6. WHEN reception staff register a patient, THE system SHALL create the patient account successfully
7. WHEN existing non-patient roles are selected on the public registration page, THE system SHALL continue to function normally

### Requirement 2

**User Story:** As a reception staff member, I want to register patients through my dashboard, so that I can create patient accounts as part of my workflow.

#### Acceptance Criteria

1. WHEN reception staff access the patient registration interface, THE system SHALL display all required patient information fields
2. WHEN reception staff submit valid patient information, THE system SHALL create the patient account immediately
3. WHEN reception staff submit invalid patient information, THE system SHALL display appropriate validation errors
4. WHEN a patient account is successfully created, THE system SHALL provide confirmation to the reception staff
5. WHEN reception staff attempt to register a patient with duplicate information, THE system SHALL prevent the registration and display an error message

### Requirement 3

**User Story:** As a patient, I want to understand that I need to visit reception for account creation, so that I know the proper process for getting access to the system.

#### Acceptance Criteria

1. WHEN a patient visits the public registration page, THE system SHALL display only non-patient role options
2. WHEN the registration page loads, THE system SHALL maintain all existing functionality for other roles
3. WHEN a patient needs account creation, THE system SHALL direct them to contact reception staff
4. WHEN the system processes registration requests, THE system SHALL maintain all existing validation rules for non-patient roles
5. WHEN users view the registration interface, THE system SHALL preserve the current user experience for authorized roles