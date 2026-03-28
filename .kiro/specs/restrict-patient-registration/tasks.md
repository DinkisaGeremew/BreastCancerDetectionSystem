# Implementation Plan

- [x] 1. Update frontend registration template to exclude patient role


  - Modify the role selection dropdown in `templates/register.html` to filter out patient role
  - Ensure the template logic excludes 'patient' from the available options
  - Preserve all existing styling and functionality for other roles
  - _Requirements: 1.1, 3.1_

- [ ]* 1.1 Write property test for frontend role filtering
  - **Property 1: Public registration excludes patient role**
  - **Validates: Requirements 1.1, 3.1**



- [ ] 2. Add backend validation to reject patient role submissions
  - Update the `/register` route in `app.py` to explicitly reject patient role
  - Add validation check before processing the registration
  - Return appropriate error message when patient role is submitted
  - _Requirements: 1.2_

- [x]* 2.1 Write property test for backend patient role rejection


  - **Property 2: Backend rejects patient role submissions**
  - **Validates: Requirements 1.2**

- [ ] 3. Verify existing non-patient role functionality
  - Test that doctor, xrayspecialist, and reception roles still work normally
  - Ensure all existing validation rules remain intact
  - Verify user creation functions work for non-patient roles
  - _Requirements: 1.5, 3.2, 3.4_


- [ ]* 3.1 Write property test for non-patient role functionality
  - **Property 3: Non-patient roles function normally**
  - **Validates: Requirements 1.5, 3.2, 3.4**

- [ ] 4. Verify reception dashboard patient registration functionality
  - Confirm existing reception patient registration interface works
  - Test patient account creation through reception dashboard
  - Ensure all patient registration fields are accessible
  - _Requirements: 1.3, 1.4, 2.1, 2.2, 2.4_

- [ ]* 4.1 Write property test for reception patient registration
  - **Property 4: Reception patient registration remains functional**

  - **Validates: Requirements 1.3, 1.4, 2.2**

- [ ]* 4.2 Write property test for reception interface completeness
  - **Property 6: Reception interface completeness**
  - **Validates: Requirements 2.1, 2.4**

- [ ] 5. Test reception interface validation
  - Verify validation works for invalid patient data in reception interface
  - Test duplicate prevention for patient registration


  - Ensure appropriate error messages are displayed
  - _Requirements: 2.3, 2.5_

- [ ]* 5.1 Write property test for reception validation
  - **Property 5: Reception interface validation works**
  - **Validates: Requirements 2.3, 2.5**

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.