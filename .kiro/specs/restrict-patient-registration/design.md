# Design Document

## Overview

This design modifies the existing registration system to remove patient self-registration capability while adding a new Health Officer role and preserving all other functionality. The solution involves updating the frontend registration form to exclude the patient role option, add the health officer role option, and adding backend validation to prevent patient role submissions while supporting health officer registration. The existing reception dashboard patient registration functionality will remain unchanged.

## Architecture

The modification follows the existing MVC architecture:

- **Model Layer**: No changes required - existing user creation functions remain intact
- **View Layer**: Update registration template to filter out patient role from dropdown
- **Controller Layer**: Add validation to reject patient role submissions in the public registration route

## Components and Interfaces

### Frontend Components

#### Registration Form (`templates/register.html`)
- **Current State**: Displays all roles including patient in dropdown
- **Modified State**: Filters out patient role from the role selection dropdown
- **Interface**: Maintains existing form structure and validation

#### Role Selection Logic
- **Input**: Available roles from translation dictionary
- **Processing**: Filter roles to exclude 'patient' 
- **Output**: Dropdown with doctor, xrayspecialist, reception, and admin (admin already excluded)

### Backend Components

#### Registration Route (`/register`)
- **Current State**: Accepts all valid roles including patient
- **Modified State**: Rejects patient role submissions with error message
- **Validation**: Add explicit check for patient role in form processing

#### Reception Dashboard
- **Current State**: Already has patient registration functionality
- **Modified State**: No changes required - existing functionality preserved

## Data Models

No changes to existing data models are required. The patient creation functions and database schema remain unchanged.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

After reviewing the acceptance criteria, several properties can be consolidated to eliminate redundancy:

Property 1: Public registration excludes patient role
*For any* request to the public registration page, the rendered HTML should not contain an option element with value="patient"
**Validates: Requirements 1.1, 3.1**

Property 2: Backend rejects patient role submissions
*For any* form submission to the public registration endpoint with role="patient", the system should reject the request and return an error response
**Validates: Requirements 1.2**

Property 3: Non-patient roles function normally
*For any* valid non-patient role (doctor, xrayspecialist, reception), submitting a registration form with that role should succeed when all other data is valid
**Validates: Requirements 1.5, 3.2, 3.4**

Property 4: Reception patient registration remains functional
*For any* valid patient data submitted through the reception dashboard interface, the system should successfully create a patient account
**Validates: Requirements 1.3, 1.4, 2.2**

Property 5: Reception interface validation works
*For any* invalid patient data submitted through the reception interface, the system should reject the submission and display appropriate error messages
**Validates: Requirements 2.3, 2.5**

Property 6: Reception interface completeness
*For any* access to the reception patient registration interface, all required patient information fields should be present and accessible
**Validates: Requirements 2.1, 2.4**

## Error Handling

### Frontend Error Handling
- **Invalid Role Selection**: Client-side validation prevents patient role selection
- **Form Validation**: Existing validation rules remain intact for all other roles
- **User Feedback**: Clear messaging when patient role is not available

### Backend Error Handling
- **Role Validation**: Server-side rejection of patient role submissions with appropriate error messages
- **Graceful Degradation**: System continues normal operation for all other roles
- **Error Logging**: Failed patient registration attempts logged for monitoring

## Testing Strategy

### Unit Testing
- Test role filtering logic in template rendering
- Test backend validation for patient role rejection
- Test existing functionality preservation for other roles
- Test reception dashboard patient registration functionality

### Property-Based Testing
The testing strategy will use Python's `hypothesis` library for property-based testing. Each correctness property will be implemented as a separate test that runs multiple iterations with generated test data.

**Property-based testing requirements:**
- Use `hypothesis` library for Python property-based testing
- Configure each test to run a minimum of 100 iterations
- Tag each test with the corresponding design document property
- Use format: `**Feature: restrict-patient-registration, Property {number}: {property_text}**`

**Test data generation:**
- Generate random user data (usernames, phones, passwords)
- Generate various role combinations for testing
- Create mock HTTP requests for endpoint testing
- Generate invalid data for validation testing

### Integration Testing
- End-to-end testing of registration flow for non-patient roles
- Reception dashboard patient registration workflow testing
- Cross-browser testing for frontend role filtering
