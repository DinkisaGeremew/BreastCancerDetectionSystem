# Design Document

## Overview

This design addresses the incorrect feedback reply status messages in the reception dashboard. The current implementation hardcodes "Admin reply awaiting" for all feedback regardless of recipient. The solution involves modifying the frontend JavaScript to dynamically determine the correct reply status message based on the recipient's role.

## Architecture

The fix involves frontend-only changes to the reception dashboard template. The backend API already provides the necessary recipient information through the `recipient_name` field in the feedback data. The frontend will use this information to determine the appropriate reply status message.

## Components and Interfaces

### Frontend Components
- **Reception Dashboard Template** (`templates/dashboard_reception.html`)
  - JavaScript functions that render feedback lists
  - Dynamic reply status message generation
  - Feedback display logic

### Data Flow
1. Reception staff views sent feedback
2. Frontend fetches feedback data from existing API endpoints
3. JavaScript processes each feedback item to determine recipient type
4. System displays appropriate reply status based on recipient role

## Data Models

The existing data models are sufficient. The feedback objects already contain:
- `recipient_name`: Name of the person who should reply
- `reply`: The actual reply content (null if no reply yet)
- `message`: The original feedback message
- `date_sent`: When the feedback was sent

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

Property 1: Health Officer status message accuracy
*For any* feedback item without a reply where the recipient is identified as a Health Officer, the displayed status message should be "Health Officer reply awaiting"
**Validates: Requirements 1.1, 2.2**

Property 2: Admin status message accuracy
*For any* feedback item without a reply where the recipient is identified as an Admin, the displayed status message should be "Admin reply awaiting"
**Validates: Requirements 1.2, 2.3**

Property 3: Reply content display precedence
*For any* feedback item with a reply, the system should display the actual reply content instead of any awaiting message, regardless of recipient type
**Validates: Requirements 1.4, 1.5, 2.5**

Property 4: Fallback status message handling
*For any* feedback item without a reply where the recipient role cannot be determined, the displayed status message should be "Reply awaiting"
**Validates: Requirements 2.4**

Property 5: Feedback list consistency
*For any* list of feedback items, all items with the same recipient type and reply status should display consistent status messages
**Validates: Requirements 1.3, 2.1**

## Error Handling

### Unknown Recipient Handling
- If recipient role cannot be determined from the name, display generic "Reply awaiting" message
- Log warning for debugging purposes but don't break the display

### Missing Data Handling
- If `recipient_name` is null or empty, use fallback "Reply awaiting" message
- If `reply` field is undefined, treat as no reply received

### API Error Handling
- Existing error handling for API failures remains unchanged
- Display appropriate error messages if feedback data cannot be loaded

## Testing Strategy

### Unit Testing
- Test recipient role detection logic with various recipient names
- Test reply status message generation for different scenarios
- Test fallback behavior for edge cases

### Property-Based Testing
The testing approach will use Jest for JavaScript unit testing to verify the correctness properties:

- **Property 1 Testing**: Generate random feedback objects with different recipient names and verify correct status messages
- **Property 2 Testing**: Generate feedback objects with and without replies to verify display precedence
- **Property 3 Testing**: Generate lists of feedback with mixed recipient types to verify consistency

Each property-based test will run a minimum of 100 iterations to ensure comprehensive coverage of input variations.

### Integration Testing
- Test the complete feedback display workflow in the reception dashboard
- Verify correct display when switching between different feedback recipients
- Test real API responses with the updated display logic

## Implementation Notes

### Recipient Role Detection
The system will use pattern matching on the `recipient_name` field to determine recipient type:
- Names containing "Health Officer" or matching known health officer usernames → "Health Officer reply awaiting"
- Names containing "Admin" or "Administrator" → "Admin reply awaiting"  
- Unknown or unmatched names → "Reply awaiting"

### Backward Compatibility
The changes are purely frontend display modifications and maintain full backward compatibility with existing API endpoints and data structures.

### Performance Considerations
The recipient role detection adds minimal processing overhead as it only involves string matching operations on already-loaded data.