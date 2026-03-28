# Design Document

## Overview

This design adds a patient count stat box to the admin dashboard overview section. The backend already calculates and passes `total_patients` to the template, so this is primarily a frontend template modification to display the existing data.

## Architecture

The solution involves a minimal template modification to the admin dashboard HTML file. No backend changes are required since the `total_patients` variable is already being calculated and passed to the template in the `dashboard_admin()` route.

## Components and Interfaces

### Template Modification
- **File**: `templates/admin_dashboard.html`
- **Section**: Overview stats container (`.stats-container`)
- **Change**: Add a new stat box for patient count

### Data Flow
1. Admin accesses dashboard
2. Backend `dashboard_admin()` route calculates `total_patients` (already implemented)
3. Template renders patient count in new stat box
4. User sees complete overview including patient count

## Data Models

No data model changes required. The existing User model and patient count calculation are sufficient.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

Property 1: Patient count display presence
*For any* admin dashboard page load, the patient count stat box should be present and visible in the stats container
**Validates: Requirements 1.1**

Property 2: Visual styling consistency
*For any* stat box in the admin dashboard, all stat boxes including the patient count should have identical CSS classes and visual styling
**Validates: Requirements 1.2**

Property 3: Data accuracy reflection
*For any* change in the total number of patients in the database, the displayed patient count should accurately reflect the current total
**Validates: Requirements 1.3**

Property 4: Layout positioning correctness
*For any* admin dashboard load, the patient count stat box should appear within the stats-container grid layout in a logical position
**Validates: Requirements 1.4**

Property 5: Functionality preservation
*For any* existing admin dashboard functionality, all features should continue to work unchanged after adding the patient count
**Validates: Requirements 1.5**

<function_calls>
<invoke name="prework">
<parameter name="featureName">admin-patient-count

## Error Handling

No specific error handling is required for this feature since:
- The backend already handles patient count calculation safely
- Template rendering will display "0" if no patients exist
- The existing error handling for the admin dashboard remains unchanged

## Testing Strategy

### Unit Testing
- Verify the patient count stat box renders with correct HTML structure
- Test that the `total_patients` variable is properly displayed
- Ensure CSS classes match other stat boxes

### Property-Based Testing
We will use Python's `hypothesis` library for property-based testing to verify the correctness properties. Each property will be tested with randomly generated patient data to ensure the display logic works correctly across all scenarios.

### Integration Testing
- Test complete admin dashboard rendering with various patient counts (0, 1, many)
- Verify layout remains responsive with the additional stat box
- Ensure no visual regression in existing dashboard elements

## Implementation Details

### Template Changes
The modification will add a new stat box div within the existing `.stats-container` in the admin dashboard template. The new element will:

1. Use the same HTML structure as existing stat boxes
2. Display the `{{ total_patients }}` template variable
3. Include appropriate ARIA labels for accessibility
4. Follow the existing CSS class pattern

### Positioning Strategy
The patient count will be positioned as the first stat box in the grid, as patients are typically the primary users of a healthcare system. The existing grid layout will automatically accommodate the additional box.

### Accessibility Considerations
- Include proper ARIA labels for screen readers
- Maintain semantic HTML structure
- Ensure keyboard navigation remains functional