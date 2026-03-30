import frappe
import json
import re
from datetime import datetime


def parse_json(value, default=None):
    """Safely parse JSON - handles both string and already-parsed dict/list."""
    if value is None:
        return default if default is not None else {}
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default if default is not None else {}
    return default if default is not None else {}


class FlowEngine:
    """Execute conversation flows."""

    def __init__(self, phone_number, whatsapp_account):
        self.phone_number = phone_number
        self.account = whatsapp_account

    def check_flow_trigger(self, message_text, button_payload=None):
        """Check if message triggers any flow."""
        try:
            flows = frappe.get_all(
                "WhatsApp Chatbot Flow",
                filters={"enabled": 1},
                fields=["name", "trigger_keywords", "trigger_on_button", "whatsapp_account"]
            )

            for flow in flows:
                # Check account filter
                if flow.whatsapp_account and flow.whatsapp_account != self.account:
                    continue

                # Check button trigger
                if button_payload and flow.trigger_on_button:
                    if button_payload == flow.trigger_on_button:
                        return flow.name

                # Check keyword trigger
                if flow.trigger_keywords and message_text:
                    keywords = [k.strip().lower() for k in flow.trigger_keywords.split(",") if k.strip()]
                    if message_text.lower() in keywords:
                        return flow.name

            return None

        except Exception as e:
            frappe.log_error(f"FlowEngine check_flow_trigger error: {str(e)}")
            return None

    def start_flow(self, flow_name):
        """Start a new conversation flow."""
        try:
            flow = frappe.get_doc("WhatsApp Chatbot Flow", flow_name)

            if not flow.steps:
                frappe.log_error(f"Flow '{flow_name}' has no steps")
                return None

            # Get first step
            first_step = sorted(flow.steps, key=lambda x: x.idx)[0]

            # Create session
            session = frappe.get_doc({
                "doctype": "WhatsApp Chatbot Session",
                "phone_number": self.phone_number,
                "whatsapp_account": self.account,
                "status": "Active",
                "current_flow": flow_name,
                "current_step": first_step.step_name,
                "session_data": json.dumps({}),
                "started_at": datetime.now(),
                "last_activity": datetime.now()
            })
            session.insert(ignore_permissions=True)
            frappe.db.commit()

            # Build and return initial message
            if flow.initial_message_type == "Template" and flow.initial_template:
                return {
                    "use_template": 1,
                    "template": flow.initial_template,
                    "message_type": "Template"
                }

            # Combine initial message with first step message
            messages = []
            if flow.initial_message:
                messages.append(flow.initial_message)

            step_msg = self.build_step_message(first_step, session)
            if isinstance(step_msg, str):
                messages.append(step_msg)
                return "\n\n".join(messages) if messages else step_msg
            else:
                # Step returns a complex message (buttons, template)
                if messages:
                    # Send initial message first, then step message
                    return messages[0]  # We'll handle multi-message later
                return step_msg

        except Exception as e:
            frappe.log_error(f"FlowEngine start_flow error: {str(e)}")
            return None

    def process_input(self, session, user_input, button_payload=None):
        """Process user input in active flow."""
        try:
            flow = frappe.get_doc("WhatsApp Chatbot Flow", session.current_flow)

            # Check for cancel keywords
            if flow.cancel_keywords:
                cancel_words = [w.strip().lower() for w in flow.cancel_keywords.split(",") if w.strip()]
                if user_input.lower() in cancel_words:
                    session.status = "Cancelled"
                    session.completed_at = datetime.now()
                    session.save(ignore_permissions=True)
                    frappe.db.commit()
                    return "Your request has been cancelled."

            # Find current step
            current_step = None
            for step in flow.steps:
                if step.step_name == session.current_step:
                    current_step = step
                    break

            if not current_step:
                return self.complete_flow(session, flow)

            # Validate input
            input_value = button_payload or user_input

            if current_step.input_type and current_step.input_type != "None":
                is_valid, error = self.validate_input(current_step, user_input, button_payload)

                if not is_valid:
                    # Handle retry
                    session.step_retries = (session.step_retries or 0) + 1
                    max_retries = current_step.max_retries or 3

                    if current_step.retry_on_invalid and session.step_retries < max_retries:
                        session.save(ignore_permissions=True)
                        frappe.db.commit()
                        return error or current_step.validation_error or "Invalid input. Please try again."
                    else:
                        # Max retries reached, cancel flow
                        session.status = "Cancelled"
                        session.completed_at = datetime.now()
                        session.save(ignore_permissions=True)
                        frappe.db.commit()
                        return "Too many invalid attempts. Please start again."

                # Store input
                if current_step.store_as:
                    session_data = parse_json(session.session_data, {})
                    session_data[current_step.store_as] = input_value
                    session.session_data = json.dumps(session_data)
                    # Force a save here to ensure persistence
                    session.save(ignore_permissions=True)

            # Log message in session
            session.add_message("Incoming", user_input, current_step.step_name)

            # Determine next step
            next_step_name = self.get_next_step(current_step, flow.steps, user_input, button_payload)

            # If it's an image/file and no conditional match was found,
            # find the next sequential step so the flow doesn't die.
            if not next_step_name and current_step.input_type in ["Image", "File"]:
                sorted_steps = sorted(flow.steps, key=lambda x: x.idx)
                for i, step in enumerate(sorted_steps):
                    if step.step_name == current_step.step_name and i < len(sorted_steps) - 1:
                        next_step_name = sorted_steps[i + 1].step_name
                        break

            if not next_step_name:
                # No next step, complete flow
                session.save(ignore_permissions=True)
                frappe.db.commit()
                return self.complete_flow(session, flow)

            # Find next step
            next_step = None
            for step in flow.steps:
                if step.step_name == next_step_name:
                    next_step = step
                    break

            if not next_step:
                return self.complete_flow(session, flow)

            # Check skip condition for next step
            session_data = parse_json(session.session_data, {})
            if next_step.skip_condition:
                if self.evaluate_skip_condition(next_step.skip_condition, session_data):
                    # Skip this step, find the one after
                    next_step_name = self.get_next_step(next_step, flow.steps, None, None)
                    if not next_step_name:
                        return self.complete_flow(session, flow)

                    for step in flow.steps:
                        if step.step_name == next_step_name:
                            next_step = step
                            break

            # Update session
            session.current_step = next_step.step_name
            session.step_retries = 0
            session.last_activity = datetime.now()
            session.save(ignore_permissions=True)
            frappe.db.commit()

            # Build and return next step message
            response = self.build_step_message(next_step, session)

            # Log outgoing message
            if isinstance(response, str):
                session.add_message("Outgoing", response, next_step.step_name)
            session.save(ignore_permissions=True)
            frappe.db.commit()

            return response

        except Exception as e:
            frappe.log_error(f"FlowEngine process_input error: {str(e)}")
            return "An error occurred. Please try again later."

    def validate_input(self, step, user_input, button_payload):
        """Validate user input against step requirements."""
        input_type = step.input_type

        # Use a more flexible check for Image/File
        if input_type in ["Image", "File"]:
            val = str(user_input or "").strip()
            # Valid if it looks like a path or has content (since we know it's media)
            if val and (val.startswith("/") or "files/" in val or val.startswith("http")):
                return True, None
            return False, f"Please upload an {input_type.lower()} to continue."


        if input_type == "Button":
            # Button responses are always valid (payload or text)
            if button_payload or user_input:
                return True, None
            return False, "Please tap a button to continue."

        if input_type == "WhatsApp Flow":
            # WhatsApp Flow responses are handled via flow_response
            # The user_input will be the summary message from the flow response
            if user_input:
                return True, None
            return False, "Please complete the form."

        if input_type == "None":
            return True, None

        if not user_input:
            return False, "Please provide a response."

        if input_type == "Select":
            if step.options:
                options = [o.strip().lower() for o in step.options.split("|") if o.strip()]
                if user_input.lower() not in options:
                    return False, f"Please choose one of: {step.options.replace('|', ', ')}"

        elif input_type == "Number":
            # Allow integers and decimals
            cleaned = user_input.replace(",", "").replace(" ", "")
            if not re.match(r"^-?\d+\.?\d*$", cleaned):
                return False, "Please enter a valid number."

        elif input_type == "Email":
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", user_input.strip()):
                return False, "Please enter a valid email address."

        elif input_type == "Phone":
            cleaned = re.sub(r"[\s\-\(\)]", "", user_input)
            if not re.match(r"^\+?\d{10,15}$", cleaned):
                return False, "Please enter a valid phone number."

        elif input_type == "Date":
            # Try common date formats
            date_formats = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"]
            valid_date = False
            for fmt in date_formats:
                try:
                    datetime.strptime(user_input.strip(), fmt)
                    valid_date = True
                    break
                except ValueError:
                    continue
            if not valid_date:
                return False, "Please enter a valid date (e.g., DD-MM-YYYY)."

        # Custom regex validation
        if step.validation_regex:
            try:
                if not re.match(step.validation_regex, user_input):
                    return False, step.validation_error or "Invalid format."
            except re.error:
                pass  # Invalid regex, skip validation

        return True, None

    def get_next_step(self, current_step, all_steps, user_input, button_payload):
        """Determine the next step based on input."""
        # Check conditional next
        if current_step.conditional_next:
            conditions = parse_json(current_step.conditional_next, {})
            if conditions:
                clean_input = str(user_input or "").strip().lower()
                response_key = button_payload or clean_input

                if response_key in conditions:
                    return conditions[response_key]
                if "default" in conditions:
                    return conditions["default"]

        # Use explicit next step
        if current_step.next_step:
            return current_step.next_step

        # Find next step by order
        sorted_steps = sorted(all_steps, key=lambda x: x.idx)
        current_idx = None
        for i, step in enumerate(sorted_steps):
            if step.step_name == current_step.step_name:
                current_idx = i
                break

        if current_idx is not None and current_idx < len(sorted_steps) - 1:
            return sorted_steps[current_idx + 1].step_name

        return None

    def build_step_message(self, step, session):
        """Build message for a step with variable substitution."""
        message = step.message or ""

        # Substitute session variables
        session_data = parse_json(session.session_data, {})
        for key, value in session_data.items():
            message = message.replace(f"{{{key}}}", str(value))

        if step.message_type == "Template" and step.template:
            return {
                "use_template": 1,
                "template": step.template,
                "message_type": "Template"
            }

        if step.message_type == "Script" and step.response_script:
            script_response = self.run_response_script(step.response_script, session_data, session)
            if script_response:
                return script_response
            # Fall back to message if script returns nothing
            return message

        # Add buttons if defined
        if step.input_type == "Button" and step.buttons:
            buttons = parse_json(step.buttons, [])
            if buttons:
                return {
                    "message": message,
                    "content_type": "interactive",
                    "buttons": json.dumps(buttons) if isinstance(buttons, list) else buttons
                }

        # Handle WhatsApp Flow
        if step.input_type == "WhatsApp Flow" and step.whatsapp_flow:
            return {
                "message": message,
                "content_type": "flow",
                "flow": step.whatsapp_flow,
                "flow_cta": step.flow_cta or "Open Form",
                "flow_screen": step.flow_screen or None
            }

        # Add options hint for Select type
        if step.input_type == "Select" and step.options:
            options_list = step.options.replace("|", ", ")
            message += f"\n\nOptions: {options_list}"

        return message

    def evaluate_skip_condition(self, condition, data):
        """Evaluate skip condition."""
        try:
            eval_globals = {
                "data": data,
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
            }
            return frappe.safe_eval(condition, eval_globals=eval_globals, eval_locals={})
        except Exception:
            return False

    def complete_flow(self, session, flow):
        """Complete a conversation flow."""
        try:
            session.status = "Completed"
            session.completed_at = datetime.now()
            session.save(ignore_permissions=True)

            # Get session data
            session_data = parse_json(session.session_data, {})

            # Execute completion action
            if flow.on_complete_action == "Create Document":
                self.create_document(flow, session_data)
            elif flow.on_complete_action == "Call API":
                self.call_api(flow.api_endpoint, session_data)
            elif flow.on_complete_action == "Run Script":
                self.run_script(flow.custom_script, session_data)

            frappe.db.commit()

            # Build completion message with variable substitution
            completion_msg = flow.completion_message or "Thank you! Your request has been submitted."
            for key, value in session_data.items():
                completion_msg = completion_msg.replace(f"{{{key}}}", str(value))

            return completion_msg

        except Exception as e:
            frappe.log_error(f"FlowEngine complete_flow error: {str(e)}")
            return "Thank you! Your request has been received."

    def create_document(self, flow, data):
        """Create a document from flow data."""
        try:
            if not flow.create_doctype or not flow.field_mapping:
                frappe.log_error(
                    f"create_document: Missing doctype ({flow.create_doctype}) or field_mapping ({flow.field_mapping})",
                    "WhatsApp Chatbot"
                )
                return

            # field_mapping might already be a dict (Frappe JSON field) or a string
            mapping = parse_json(flow.field_mapping, {})

            if not mapping:
                frappe.log_error(
                    f"create_document: Empty field mapping for flow {flow.name}",
                    "WhatsApp Chatbot"
                )
                return

            doc_data = {"doctype": flow.create_doctype}

            for field, variable in mapping.items():
                if variable in data:
                    doc_data[field] = data[variable]
                else:
                    frappe.log_error(
                        f"create_document: Variable '{variable}' not found in session data. Available: {list(data.keys())}",
                        "WhatsApp Chatbot"
                    )

            # Check if we have any data besides doctype
            if len(doc_data) <= 1:
                frappe.log_error(
                    f"create_document: No data mapped. Session data: {data}, Mapping: {mapping}",
                    "WhatsApp Chatbot"
                )
                return

            doc = frappe.get_doc(doc_data)
            doc.insert(ignore_permissions=True)
            frappe.db.commit()

            frappe.log_error(
                f"create_document: Successfully created {flow.create_doctype} with data: {doc_data}",
                "WhatsApp Chatbot Success"
            )

        except Exception as e:
            frappe.log_error(
                f"FlowEngine create_document error: {str(e)}\nData: {data}\nMapping: {mapping if 'mapping' in dir() else 'N/A'}",
                "WhatsApp Chatbot Error"
            )

    def call_api(self, endpoint, data):
        """Call external API with flow data."""
        try:
            import requests
            response = requests.post(
                endpoint,
                json=data,
                timeout=30,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
        except Exception as e:
            frappe.log_error(f"FlowEngine call_api error: {str(e)}")

    def run_script(self, script, data):
        """Run custom Python script."""
        try:
            eval_globals = {
                "data": data,
                "frappe": frappe,
                "json": json
            }
            exec(script, eval_globals)
        except Exception as e:
            frappe.log_error(f"FlowEngine run_script error: {str(e)}")

    def process_flow_response(self, step, session, flow_response):
        """Process WhatsApp Flow response and map fields to session data.

        Args:
            step: The current flow step with flow_field_mapping
            session: The chatbot session document
            flow_response: Dict of field values from WhatsApp Flow

        Returns:
            Updated session_data dict
        """
        session_data = parse_json(session.session_data, {})

        if not flow_response:
            return session_data

        # Get field mapping from step
        field_mapping = parse_json(step.flow_field_mapping, {})

        if field_mapping:
            # Map flow fields to session variables based on mapping
            # Mapping format: {"session_var": "flow_field"}
            for session_var, flow_field in field_mapping.items():
                if flow_field in flow_response:
                    session_data[session_var] = flow_response[flow_field]
        else:
            # No mapping defined, store all flow fields directly
            for key, value in flow_response.items():
                session_data[key] = value

        # Also store the complete response if needed
        if step.store_as:
            session_data[step.store_as] = flow_response

        return session_data

    def run_response_script(self, script, data, session):
        """Run script to generate dynamic response message.

        The script should set 'response' variable with the message to return.
        Response can be a string or dict (for buttons/templates).

        Available in script:
            - data: dict of collected session data
            - frappe: frappe module for database queries
            - json: json module
            - session: the current session document
            - phone_number: user's phone number

        Example 1 - Simple text:
            order = frappe.get_doc('Sales Order', data.get('order_id'))
            response = f"Order status: {order.status}"

        Example 2 - Dynamic buttons (invoices):
            invoices = frappe.get_all('Sales Invoice',
                filters={'customer': data.get('customer')},
                fields=['name', 'grand_total'],
                limit=10
            )
            buttons = [{"id": inv.name, "title": inv.name, "description": f"₹{inv.grand_total}"} for inv in invoices]
            response = {"message": "Select an invoice:", "content_type": "interactive", "buttons": json.dumps(buttons)}
        """
        try:
            eval_globals = {
                "data": data,
                "frappe": frappe,
                "json": json,
                "session": session,
                "phone_number": self.phone_number,
                "response": None
            }
            exec(script, eval_globals)
            return eval_globals.get("response")
        except Exception as e:
            frappe.log_error(f"FlowEngine run_response_script error: {str(e)}")
            return None
