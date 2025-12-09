# Conversation Flows

Flows allow multi-step conversations to collect information from users.

![Chatbot Flow](../assets/chatbot_flow_1.png)

![Flow Steps](../assets/chatbot_flow_2.png)

## Creating a Flow

1. Go to **WhatsApp Chatbot Flow** → **+ Add**
2. Configure flow settings
3. Add steps in the Steps table
4. Set completion action
5. Click **Save**

## Flow Settings

| Field | Description |
|-------|-------------|
| **Flow Name** | Unique identifier |
| **Enabled** | Enable/disable the flow |
| **WhatsApp Account** | Leave empty for all accounts |
| **Trigger Keywords** | Comma-separated keywords that start this flow |
| **Cancel Keywords** | Words that cancel the flow (default: cancel, stop, quit, exit) |

## Initial Message

| Field | Description |
|-------|-------------|
| **Initial Message** | First message when flow starts |
| **Initial Message Type** | Text or Template |
| **Initial Template** | WhatsApp template (if type is Template) |

## Flow Steps

Each step in the flow is configured in the Steps table. **Drag and drop rows to reorder steps.**

### Step Fields

| Field | Description |
|-------|-------------|
| **Step Name** | Unique identifier (e.g., `ask_name`, `ask_email`) |
| **Message** | Message to send. Use `{variable}` for substitution |
| **Message Type** | Text, Template, or Script |
| **Input Type** | Expected input type |
| **Store As** | Variable name to store user's response |

### Input Types

| Type | Description | Validation |
|------|-------------|------------|
| **None** | No input expected | - |
| **Text** | Any text | None |
| **Number** | Numeric input | Must be a valid number |
| **Email** | Email address | Must contain @ and domain |
| **Phone** | Phone number | 10-15 digits, optional + prefix |
| **Date** | Date input | Common formats (DD-MM-YYYY, etc.) |
| **Select** | Choice from options | Must match one of the options |
| **Button** | Interactive buttons | User must tap a button |

### Buttons & Lists

Use interactive buttons for quick choices. WhatsApp automatically shows:
- **Buttons** (1-3 options) - Displayed as tappable buttons
- **List Menu** (4-10 options) - Displayed as a dropdown menu

#### Setup

1. Set **Input Type** to `Button`
2. Add buttons in the **Buttons** field (JSON format with syntax highlighting)

#### Button Format (1-3 options)

```json
[
  {"id": "yes", "title": "Yes"},
  {"id": "no", "title": "No"}
]
```

#### List Format (4-10 options)

```json
[
  {"id": "sales", "title": "Sales", "description": "Talk to sales team"},
  {"id": "support", "title": "Support", "description": "Get technical help"},
  {"id": "billing", "title": "Billing", "description": "Payment questions"},
  {"id": "other", "title": "Other", "description": "Something else"}
]
```

#### Field Reference

| Field | Description | Limit |
|-------|-------------|-------|
| `id` | Value stored when user taps (use in Conditional Next) | - |
| `title` | Text shown on button/list item | 20 chars |
| `description` | Subtitle (list only, optional) | 72 chars |

#### Example: Confirmation Step

**Buttons field:**
```json
[{"id": "confirm", "title": "Confirm"}, {"id": "cancel", "title": "Cancel"}]
```

**Conditional Next field:**
```json
{"confirm": "process_step", "cancel": "cancelled_step", "default": "retry_step"}
```

**Store As:** `user_choice` (stores "confirm" or "cancel")

#### Dynamic Buttons (Script)

Use **Message Type: Script** to generate buttons dynamically from database queries.

**Example: List user's recent invoices**

1. Set **Message Type** to `Script`
2. Set **Input Type** to `Button`
3. Add script in **Response Script**:

```python
# Get invoices for this customer (using phone number to find customer)
customer = frappe.get_value('Customer', {'mobile_no': phone_number}, 'name')

if customer:
    invoices = frappe.get_all('Sales Invoice',
        filters={'customer': customer, 'docstatus': 1},
        fields=['name', 'grand_total', 'posting_date'],
        order_by='posting_date desc',
        limit=10
    )

    if invoices:
        buttons = [
            {
                "id": inv.name,
                "title": inv.name[:20],
                "description": f"₹{inv.grand_total} - {inv.posting_date}"
            }
            for inv in invoices
        ]
        response = {
            "message": "Select an invoice to view details:",
            "content_type": "interactive",
            "buttons": json.dumps(buttons)
        }
    else:
        response = "No invoices found for your account."
else:
    response = "Customer not found. Please contact support."
```

4. Set **Store As** to `selected_invoice`
5. In the next step, use `{selected_invoice}` to fetch and display details

### Message Type: Script

Execute Python code to generate dynamic responses. See [Script Responses](../features/scripts.md).

### Validation

| Field | Description |
|-------|-------------|
| **Validation Regex** | Custom regex pattern |
| **Validation Error Message** | Error shown on invalid input |
| **Retry on Invalid Input** | Re-prompt on invalid input |
| **Max Retries** | Maximum retry attempts (default: 3) |

### Navigation

| Field | Description |
|-------|-------------|
| **Next Step** | Explicit next step name (leave empty for sequential) |
| **Conditional Next** | JSON mapping input to next step |
| **Skip Condition** | Python expression to skip this step |

#### Conditional Next Example

```json
{
  "billing": "billing_step",
  "technical": "technical_step",
  "default": "general_step"
}
```

## Completion Settings

| Field | Description |
|-------|-------------|
| **Completion Message** | Message sent when flow completes. Use `{variable}` for substitution |
| **On Complete Action** | None, Create Document, Call API, or Run Script |

### Create Document

| Field | Description |
|-------|-------------|
| **Create DocType** | DocType to create (e.g., Lead, Issue) |
| **Field Mapping** | JSON mapping flow variables to DocType fields |

Example field mapping:
```json
{
  "lead_name": "customer_name",
  "email_id": "customer_email",
  "company_name": "company"
}
```

### Call API

| Field | Description |
|-------|-------------|
| **API Endpoint** | URL to POST collected data to |

### Run Script

| Field | Description |
|-------|-------------|
| **Custom Script** | Python script to execute. Use `data` dict for collected values |

## Variable Substitution

Use `{variable_name}` in messages to substitute collected values.

Example:
```
Message: Thanks {customer_name}! We'll contact you at {customer_email}.
```

## Flow Processing Priority

When a message is received:

1. **Active Session** - If user has an active flow session, continue that flow
2. **Keyword Match** - Check keyword replies (if response type is Flow, start that flow)
3. **Flow Trigger** - Check flow trigger keywords
4. **AI/Default** - Fallback to AI or default response
