<div align="right">
	<a href="[https://frappecloud.com/crm/signup](https://cloud.frappe.io/marketplace/apps/frappe_whatsapp_chatbot)" target="_blank">
		<picture>
			<source media="(prefers-color-scheme: dark)" srcset="https://frappe.io/files/try-on-fc-white.png">
			<img src="https://frappe.io/files/try-on-fc-black.png" alt="Try on Frappe Cloud" height="28" />
		</picture>
	</a>
</div>
<p align="center">
  <img src="docs/assets/logo.svg" alt="Frappe WhatsApp Chatbot" width="150">
</p>




<h1 align="left">Frappe WhatsApp Chatbot</h1>

<p align="center">
A comprehensive chatbot solution for Frappe WhatsApp integration.<br>
Supports keyword-based replies, multi-step conversation flows with dynamic scripting, and optional AI-powered responses.
</p>

## Features

- **Keyword-Based Replies**: Configure automatic responses based on keywords with multiple match types
- **Conversation Flows**: Multi-step decision trees with user input collection and validation
- **WhatsApp Flow Integration**: Send native WhatsApp Flows for rich form experiences
- **Dynamic Script Responses**: Execute Python scripts to generate dynamic responses (e.g., check order status from database)
- **Document Creation**: Automatically create Frappe documents from collected flow data
- **Optional AI Integration**: OpenAI and Anthropic support for intelligent responses
- **Session Management**: Track user conversations with automatic timeout handling
- **Business Hours**: Restrict bot responses to business hours
- **Flexible Configuration**: All settings managed via Frappe Desk UI

## Installation

### Prerequisites

- Frappe Framework >= 15.0.0
- [frappe_whatsapp](https://github.com/shridarpatil/frappe_whatsapp) app (must be installed first)

### Install the App

```bash
# Inside your Frappe bench
bench get-app https://github.com/shridarpatil/frappe_whatsapp_chatbot
bench --site your-site install-app frappe_whatsapp_chatbot
```

### Optional Dependencies (for AI features)

```bash
pip install openai      # For OpenAI integration
pip install anthropic   # For Anthropic Claude integration
```

## Quick Start

### 1. Enable Chatbot

Navigate to **WhatsApp Chatbot** (single DocType) and:

1. Check **Enabled**
2. Select the WhatsApp Account (or enable "Process All Accounts")
3. Set a default response message for unmatched messages

### 2. Create Your First Keyword Reply

Go to **WhatsApp Keyword Reply** list and create a new rule:

```
Title: Greeting
Keywords: hello, hi, hey
Match Type: Exact
Response Type: Text
Response Text: Hello! How can I help you today?
```

### 3. Test It

Send "hello" to your WhatsApp Business number and receive the automated reply!

---

## Configuration Guide

### WhatsApp Chatbot Settings

| Setting | Description |
|---------|-------------|
| Enabled | Master switch to enable/disable the chatbot |
| WhatsApp Account | Specific account to process (or use "Process All Accounts") |
| Default Response | Message sent when no keyword/flow matches |
| Session Timeout | Minutes before an inactive flow session expires (default: 30) |
| Business Hours Only | Only respond during specified hours |
| Enable AI | Use AI for fallback responses |

### Keyword Reply Configuration

| Field | Description |
|-------|-------------|
| Keywords | Comma-separated keywords (e.g., "hello, hi, hey") |
| Match Type | **Exact** - exact match, **Contains** - keyword anywhere in message, **Starts With** - message starts with keyword, **Regex** - regular expression |
| Case Sensitive | Enable for case-sensitive matching |
| Response Type | **Text** - plain text, **Template** - WhatsApp template, **Media** - image/video/document, **Flow** - trigger a conversation flow |
| Priority | Higher priority rules are matched first (default: 10) |
| Active From/Until | Optional date range for time-limited responses |

### Conversation Flows

Flows allow multi-step conversations to collect information from users.

#### Flow Settings

| Field | Description |
|-------|-------------|
| Flow Name | Unique identifier |
| Trigger Keywords | Comma-separated keywords that start this flow |
| Initial Message | First message sent when flow starts |
| Steps | Table of flow steps (see below) |
| Completion Message | Message sent when flow completes. Use `{variable_name}` for substitution |
| On Complete Action | **None**, **Create Document**, **Call API**, or **Run Script** |
| Cancel Keywords | Words that cancel the flow (default: cancel, stop, quit, exit) |

#### Flow Step Configuration

| Field | Description |
|-------|-------------|
| Step Name | Unique identifier for this step |
| Message | Message to send. Use `{variable_name}` for substitution |
| Message Type | **Text** - plain message, **Template** - WhatsApp template, **Script** - dynamic Python script |
| Input Type | Expected input: **None**, **Text**, **Number**, **Email**, **Phone**, **Date**, **Select**, **WhatsApp Flow** |
| Store As | Variable name to store user's input (e.g., `customer_email`) |
| Options | For Select type: pipe-separated options (e.g., `Option 1|Option 2|Option 3`) |
| Validation Regex | Custom regex pattern for input validation |
| Next Step | Explicit next step name (leave empty for sequential order) |
| Conditional Next | JSON mapping input to next step (see examples below) |
| Skip Condition | Python expression to skip this step |

---

## Examples

### Example 1: Simple FAQ Bot

Create keyword replies for common questions:

**Keyword Reply: Business Hours**
```
Keywords: hours, timing, open, close
Match Type: Contains
Response Type: Text
Response Text: We're open Monday-Friday, 9 AM to 6 PM IST.
```

**Keyword Reply: Location**
```
Keywords: address, location, where
Match Type: Contains
Response Type: Text
Response Text: We're located at 123 Main Street, Mumbai, India. Google Maps: https://maps.google.com/...
```

### Example 2: Lead Collection Flow

```
Flow Name: Contact Sales
Trigger Keywords: sales, contact, demo, pricing

Initial Message: Great! I'd be happy to connect you with our sales team.

Steps:
┌─────────────────────────────────────────────────────────────────┐
│ Step 1                                                          │
│ Step Name: ask_name                                             │
│ Message: What's your name?                                      │
│ Input Type: Text                                                │
│ Store As: customer_name                                         │
├─────────────────────────────────────────────────────────────────┤
│ Step 2                                                          │
│ Step Name: ask_email                                            │
│ Message: Thanks {customer_name}! What's your email address?     │
│ Input Type: Email                                               │
│ Store As: customer_email                                        │
├─────────────────────────────────────────────────────────────────┤
│ Step 3                                                          │
│ Step Name: ask_company                                          │
│ Message: And which company are you from?                        │
│ Input Type: Text                                                │
│ Store As: company_name                                          │
└─────────────────────────────────────────────────────────────────┘

Completion Message: Thank you {customer_name}! Our sales team will contact you at {customer_email} within 24 hours.

On Complete Action: Create Document
Create DocType: Lead
Field Mapping:
{
    "lead_name": "customer_name",
    "email_id": "customer_email",
    "company_name": "company_name"
}
```

### Example 3: Order Status Check (Using Script)

This example shows how to use the **Script** message type to query the database dynamically.

```
Flow Name: Order Status
Trigger Keywords: order status, track order, my order

Steps:
┌─────────────────────────────────────────────────────────────────┐
│ Step 1                                                          │
│ Step Name: ask_order_id                                         │
│ Message: Please enter your Order ID (e.g., SAL-ORD-2024-00001)  │
│ Input Type: Text                                                │
│ Store As: order_id                                              │
├─────────────────────────────────────────────────────────────────┤
│ Step 2                                                          │
│ Step Name: show_status                                          │
│ Message: (placeholder - script will generate response)          │
│ Message Type: Script                                            │
│ Input Type: None                                                │
│ Response Script:                                                │
│                                                                 │
│   order_id = data.get('order_id')                               │
│   try:                                                          │
│       order = frappe.get_doc('Sales Order', order_id)           │
│       response = f"""Order Details:                             │
│   Order ID: {order.name}                                        │
│   Status: {order.status}                                        │
│   Total: {order.grand_total}                                    │
│   Expected Delivery: {order.delivery_date or 'TBD'}"""          │
│   except frappe.DoesNotExistError:                              │
│       response = f"Sorry, order '{order_id}' was not found."    │
│   except Exception as e:                                        │
│       response = "Sorry, unable to fetch order details."        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

Completion Message: Is there anything else I can help you with?
```

#### Script Variables Available

When using Message Type: Script, these variables are available:

| Variable | Description |
|----------|-------------|
| `data` | Dictionary of all collected session data (keyed by Store As names) |
| `frappe` | Frappe module for database queries |
| `json` | JSON module |
| `session` | Current session document |
| `phone_number` | User's WhatsApp phone number |
| `response` | **Set this variable** with the message to send |

### Example 4: Conditional Branching

Create different paths based on user input:

```
Flow Name: Support Request
Trigger Keywords: support, help, issue

Steps:
┌─────────────────────────────────────────────────────────────────┐
│ Step 1                                                          │
│ Step Name: ask_issue_type                                       │
│ Message: What type of issue are you facing?                     │
│ Input Type: Select                                              │
│ Options: Billing|Technical|General                              │
│ Store As: issue_type                                            │
│ Conditional Next:                                               │
│ {                                                               │
│   "billing": "billing_step",                                    │
│   "technical": "technical_step",                                │
│   "general": "general_step"                                     │
│ }                                                               │
├─────────────────────────────────────────────────────────────────┤
│ Step 2a                                                         │
│ Step Name: billing_step                                         │
│ Message: For billing issues, please email billing@company.com   │
│ Input Type: None                                                │
├─────────────────────────────────────────────────────────────────┤
│ Step 2b                                                         │
│ Step Name: technical_step                                       │
│ Message: Please describe your technical issue in detail.        │
│ Input Type: Text                                                │
│ Store As: issue_description                                     │
├─────────────────────────────────────────────────────────────────┤
│ Step 2c                                                         │
│ Step Name: general_step                                         │
│ Message: Please describe your question.                         │
│ Input Type: Text                                                │
│ Store As: issue_description                                     │
└─────────────────────────────────────────────────────────────────┘
```

### Example 5: Using WhatsApp Flows

Integrate native WhatsApp Flows to collect structured data with a rich form UI.

> **Note:** Requires WhatsApp Flows to be set up in the `frappe_whatsapp` app first.

```
Flow Name: Booking Request
Trigger Keywords: book, appointment, schedule

Steps:
┌─────────────────────────────────────────────────────────────────┐
│ Step 1                                                          │
│ Step Name: collect_booking_info                                 │
│ Message: Please fill out the booking form below.                │
│ Input Type: WhatsApp Flow                                       │
│ WhatsApp Flow: Booking Form                                     │
│ Flow CTA: Open Booking Form                                     │
│ Flow Screen: booking_screen                                     │
│ Flow Field Mapping:                                             │
│ {                                                               │
│   "customer_name": "name",                                      │
│   "customer_phone": "mobile",                                   │
│   "appointment_date": "date"                                    │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘

Completion Message: Thank you {customer_name}! Your appointment is confirmed for {appointment_date}.

On Complete Action: Create Document
Create DocType: Appointment
```

#### WhatsApp Flow Step Fields

| Field | Description |
|-------|-------------|
| WhatsApp Flow | Link to the WhatsApp Flow document |
| Flow CTA | Call-to-action button text (e.g., "Open Form") |
| Flow Screen | Initial screen to display (optional) |
| Flow Field Mapping | JSON mapping: `{"session_var": "flow_field"}` |

When the user completes the WhatsApp Flow, the response data is automatically mapped to session variables based on the Field Mapping configuration.

---

## AI Integration (Optional)

### Setup

1. Enable AI in **WhatsApp Chatbot** settings
2. Select provider: **OpenAI** or **Anthropic**
3. Enter your API key
4. Configure model (e.g., `gpt-4o-mini`, `claude-3-haiku-20240307`)

### AI Context

Create **WhatsApp AI Context** documents to provide knowledge to the AI:

**Static Text Context:**
```
Title: Company Info
Context Type: Static Text
Static Content:
Our company, ABC Corp, was founded in 2010. We specialize in...
Our products include: Product A, Product B, Product C...
```

**DocType Query Context:**
```
Title: Product Catalog
Context Type: DocType Query
DocType: Item
Fields to Include: item_name, description, standard_rate
Filters: {"disabled": 0, "is_sales_item": 1}
```

The AI will use this context to answer questions intelligently.

---

## Processing Priority

When a message is received, the chatbot processes it in this order:

1. **Active Flow Session** - Continue ongoing conversation
2. **Keyword Match** - Check keyword rules (highest priority first)
3. **Flow Trigger** - Check flow trigger keywords
4. **AI Fallback** - Generate AI response (if enabled)
5. **Default Response** - Send configured default message

---

## DocTypes Reference

| DocType | Type | Purpose |
|---------|------|---------|
| WhatsApp Chatbot | Single | Global settings |
| WhatsApp Keyword Reply | List | Keyword-to-response mappings |
| WhatsApp Chatbot Flow | List | Conversation flow definitions |
| WhatsApp Flow Step | Child Table | Steps within flows |
| WhatsApp Chatbot Session | List | Track active conversations |
| WhatsApp Session Message | Child Table | Message history within sessions |
| WhatsApp AI Context | List | Knowledge base for AI responses |
| WhatsApp Excluded Number | Child Table | Numbers to exclude from bot |

---

## Hooks & Scheduled Jobs

### Document Events

```python
doc_events = {
    "WhatsApp Message": {
        "after_insert": "frappe_whatsapp_chatbot.chatbot.processor.process_incoming_message"
    }
}
```

### Scheduled Jobs

| Frequency | Function | Description |
|-----------|----------|-------------|
| Hourly | `cleanup_expired_sessions` | Expire inactive sessions and send timeout messages |

---

## Troubleshooting

### Chatbot Not Responding

1. Check if **Enabled** is checked in WhatsApp Chatbot settings
2. Verify the WhatsApp Account is correct
3. Check Error Log for any exceptions
4. Ensure the phone number is not in Excluded Numbers

### Flow Not Triggering

1. Check trigger keywords match exactly (case-insensitive)
2. Verify no active session exists for that phone number
3. Check the flow is enabled

### Session Data Not Saving

1. Ensure **Store As** field is filled in flow steps
2. Check that Input Type is not "None" for steps that collect data

### Script Response Not Working

1. Set **Message Type** to "Script"
2. Ensure the script sets the `response` variable
3. Check Error Log for script execution errors

### View Logs

```
Frappe Desk > Error Log
```

Filter by "WhatsApp Chatbot" to see chatbot-specific errors.

---

## License

MIT License with Commons Clause - Free to use, modify, and distribute, but cannot be sold commercially. See [LICENSE](LICENSE) for details.

## Author

Shridhar Patil (shrip.dev@gmail.com)
