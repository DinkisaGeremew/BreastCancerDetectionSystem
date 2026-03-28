# Implementation Plan

- [ ] 1. Create recipient role detection function
  - Implement JavaScript function to determine recipient type from recipient_name
  - Add pattern matching for "Health Officer", "Admin", and fallback cases
  - _Requirements: 1.1, 1.2, 2.2, 2.3, 2.4_

- [ ]* 1.1 Write property test for recipient role detection
  - **Property 1: Health Officer status message accuracy**
  - **Validates: Requirements 1.1, 2.2**

- [ ]* 1.2 Write property test for Admin role detection
  - **Property 2: Admin status message accuracy**
  - **Validates: Requirements 1.2, 2.3**

- [ ]* 1.3 Write property test for fallback role detection
  - **Property 4: Fallback status message handling**
  - **Validates: Requirements 2.4**

- [ ] 2. Update feedback display logic in reception dashboard
  - Modify the JavaScript code in templates/dashboard_reception.html
  - Replace hardcoded "Admin reply awaiting" with dynamic status messages
  - Implement logic to show correct awaiting message based on recipient type
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3_

- [ ]* 2.1 Write property test for reply content precedence
  - **Property 3: Reply content display precedence**
  - **Validates: Requirements 1.4, 1.5, 2.5**

- [ ]* 2.2 Write property test for feedback list consistency
  - **Property 5: Feedback list consistency**
  - **Validates: Requirements 1.3, 2.1**

- [ ] 3. Update all feedback display locations
  - Find and update all instances where feedback status is displayed
  - Ensure consistent behavior across different feedback sections
  - Update both the feedback list display and new feedback creation display
  - _Requirements: 1.3, 1.4, 1.5, 2.1, 2.5_

- [x] 4. Test the feedback display functionality



  - Test sending feedback to Health Officers shows "Health Officer reply awaiting"
  - Test sending feedback to Admins shows "Admin reply awaiting"
  - Test that replies display correctly instead of awaiting messages
  - Verify fallback behavior for unknown recipients
  - _Requirements: 1.1, 1.2, 1.4, 1.5, 2.4_

- [ ] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.