import frappe
from frappe import _
from datetime import datetime

# Flag to prevent recursive processing
_processing_messages = set()


class ChatbotProcessor:
    """Main processor for incoming WhatsApp messages."""

    def __init__(self, message_data):
        """
        Initialize with message data dict (not document).

        Args:
            message_data: dict with keys: name, from, message, content_type, whatsapp_account, type, flow_response
        """
        self.message_data = message_data
        self.message_name = message_data.get("name")
        self.phone_number = message_data.get("from") or message_data.get("from_")
        self.message_text = message_data.get("message") or ""
        self.content_type = message_data.get("content_type") or "text"
        self.account = message_data.get("whatsapp_account")
        self.button_payload = None
        self.flow_response = None

        # Extract button payload if this is a button response
        if self.content_type == "button":
            self.button_payload = self.message_text

        # Extract flow response if this is a flow response
        if self.content_type == "flow":
            flow_response_data = message_data.get("flow_response")
            if flow_response_data:
                import json
                if isinstance(flow_response_data, str):
                    try:
                        self.flow_response = json.loads(flow_response_data)
                    except json.JSONDecodeError:
                        self.flow_response = {}
                else:
                    self.flow_response = flow_response_data

        self.settings = None

    def get_chatbot_settings(self):
        """Get chatbot configuration."""
        if self.settings is not None:
            return self.settings

        try:
            if frappe.db.exists("WhatsApp Chatbot"):
                settings = frappe.get_single("WhatsApp Chatbot")
                if settings.enabled:
                    self.settings = settings
                    return settings
        except Exception as e:
            frappe.log_error(f"get_chatbot_settings error: {str(e)}")

        self.settings = False  # Mark as checked but not found/enabled
        return None

    def should_process(self):
        """Check if message should be processed by chatbot."""
        settings = self.get_chatbot_settings()

        if not settings:
            return False

        # Ensure image and document are allowed in the processing loop
        if self.content_type not in ["text", "button", "flow", "image", "document"]:
            return False

        # Check if this account is configured for chatbot
        if not settings.process_all_accounts:
            if self.account != settings.whatsapp_account:
                return False

        # Check excluded numbers
        excluded = [row.phone_number for row in settings.excluded_numbers]
        if self.phone_number in excluded:
            return False

        # Check if transferred to agent
        if self.is_transferred_to_agent():
            return False

        return True

    def is_transferred_to_agent(self):
        """Check if this conversation has been transferred to a human agent."""
        try:
            return frappe.db.exists("WhatsApp Agent Transfer", {
                "phone_number": self.phone_number,
                "status": "Active"
            })
        except Exception:
            # If doctype doesn't exist yet, don't block processing
            return False

    def process(self):
        """Process the incoming message."""
        settings = self.get_chatbot_settings()

        if not settings:
            return

        if not self.should_process():
            return

        # Check business hours (send out of hours message if needed)
        if settings.business_hours_only:
            if not self.is_business_hours():
                if settings.out_of_hours_message:
                    self.send_response(settings.out_of_hours_message)
                return

        from frappe_whatsapp_chatbot.chatbot.session_manager import SessionManager
        from frappe_whatsapp_chatbot.chatbot.keyword_matcher import KeywordMatcher
        from frappe_whatsapp_chatbot.chatbot.flow_engine import FlowEngine

        # Initialize managers
        session_mgr = SessionManager(self.phone_number, self.account)
        keyword_matcher = KeywordMatcher(self.account)
        flow_engine = FlowEngine(self.phone_number, self.account)

        response = None

        # 1. Check for active flow session
        active_session = session_mgr.get_active_session()
        if active_session:
            # If this is a flow response, process the flow data
            if self.content_type == "flow" and self.flow_response:
                response = self.process_flow_response_in_session(
                    active_session,
                    flow_engine
                )
            else:
                response = flow_engine.process_input(
                    active_session,
                    self.message_text,
                    self.button_payload
                )
            if response:
                self.send_response(response)
                return

        # 2. Check keyword matches
        keyword_match = keyword_matcher.match(self.message_text)
        if keyword_match:
            if keyword_match.response_type == "Flow":
                # Trigger a new flow
                response = flow_engine.start_flow(keyword_match.trigger_flow)
            else:
                response = self.build_keyword_response(keyword_match)

            if response:
                self.send_response(response)
                return

        # 3. Check if message triggers a flow directly
        flow_trigger = flow_engine.check_flow_trigger(self.message_text, self.button_payload)
        if flow_trigger:
            response = flow_engine.start_flow(flow_trigger)
            if response:
                self.send_response(response)
                return

        # 4. AI Fallback (if enabled)
        if settings.enable_ai:
            try:
                from frappe_whatsapp_chatbot.chatbot.ai_responder import AIResponder
                ai_responder = AIResponder(settings, phone_number=self.phone_number)
                response = ai_responder.generate_response(
                    self.message_text,
                    session_mgr.get_conversation_history()
                )
                if response:
                    self.send_response(response)
                    return
            except Exception as e:
                frappe.log_error(f"AI Fallback error: {str(e)}")
                # Rollback any failed transaction
                frappe.db.rollback()

        # 5. Default response
        if settings.default_response:
            self.send_response(settings.default_response)

    def send_response(self, response):
        """Send response message."""
        try:
            # Use flags to prevent the after_insert hook from processing our outgoing message
            flags = frappe._dict(ignore_chatbot=True)

            if isinstance(response, str):
                # Simple text response
                msg = frappe.get_doc({
                    "doctype": "WhatsApp Message",
                    "type": "Outgoing",
                    "to": self.phone_number,
                    "message": response,
                    "content_type": "text",
                    "whatsapp_account": self.account
                })
                msg.flags.ignore_chatbot = True
                msg.insert(ignore_permissions=True)
                frappe.db.commit()

            elif isinstance(response, dict):
                # Complex response (template, media, buttons, etc.)
                msg_data = {
                    "doctype": "WhatsApp Message",
                    "type": "Outgoing",
                    "to": self.phone_number,
                    "whatsapp_account": self.account
                }
                msg_data.update(response)

                msg = frappe.get_doc(msg_data)
                msg.flags.ignore_chatbot = True
                msg.insert(ignore_permissions=True)
                frappe.db.commit()

        except Exception as e:
            frappe.log_error(
                f"Chatbot send_response error: {str(e)}",
                "WhatsApp Chatbot Error"
            )

    def process_flow_response_in_session(self, session, flow_engine):
        """Process a WhatsApp Flow response within an active chatbot session.

        Args:
            session: Active WhatsApp Chatbot Session
            flow_engine: FlowEngine instance

        Returns:
            Response message to send
        """
        import json

        try:
            flow = frappe.get_doc("WhatsApp Chatbot Flow", session.current_flow)

            # Find current step
            current_step = None
            for step in flow.steps:
                if step.step_name == session.current_step:
                    current_step = step
                    break

            if not current_step:
                return flow_engine.complete_flow(session, flow)

            # Verify this step expects a WhatsApp Flow response
            if current_step.input_type != "WhatsApp Flow":
                # Unexpected flow response, treat as regular text input
                return flow_engine.process_input(
                    session,
                    self.message_text,
                    self.button_payload
                )

            # Process the flow response and map fields to session data
            session_data = flow_engine.process_flow_response(
                current_step,
                session,
                self.flow_response
            )
            session.session_data = json.dumps(session_data)

            # Log the flow response
            session.add_message("Incoming", f"Flow completed: {self.message_text}", current_step.step_name)

            # Continue to next step (same logic as process_input)
            return flow_engine.process_input(
                session,
                self.message_text,  # Use summary as input
                None
            )

        except Exception as e:
            frappe.log_error(f"process_flow_response_in_session error: {str(e)}")
            return "An error occurred processing your form. Please try again."

    def build_keyword_response(self, keyword_doc):
        """Build response from keyword match."""
        if keyword_doc.response_type == "Text":
            return keyword_doc.response_text

        elif keyword_doc.response_type == "Template":
            response = {
                "use_template": 1,
                "template": keyword_doc.response_template,
                "message_type": "Template"
            }
            if keyword_doc.template_parameters:
                response["body_param"] = keyword_doc.template_parameters
            return response

        elif keyword_doc.response_type == "Media":
            return {
                "content_type": keyword_doc.media_type.lower() if keyword_doc.media_type else "image",
                "media_image": keyword_doc.media_url if keyword_doc.media_type == "Image" else None,
                "media_video": keyword_doc.media_url if keyword_doc.media_type == "Video" else None,
                "media_audio": keyword_doc.media_url if keyword_doc.media_type == "Audio" else None,
                "media_document": keyword_doc.media_url if keyword_doc.media_type == "Document" else None,
                "message": keyword_doc.media_caption or ""
            }

        elif keyword_doc.response_type == "Script":
            return self.execute_script(keyword_doc.script)

        return None

    def execute_script(self, script):
        """Execute a Server Script or method path.

        Args:
            script: Server Script name or dotted method path

        Returns:
            Response from the script/method
        """
        if not script:
            return None

        try:
            # Get the WhatsApp Message document
            message_doc = frappe.get_doc("WhatsApp Message", self.message_name)

            # Check if it's a Server Script (API type)
            if frappe.db.exists("Server Script", {"name": script, "script_type": "API"}):
                server_script = frappe.get_doc("Server Script", script)
                # Use Frappe's safe_exec to execute the Server Script
                # Provide context variables that the script can use
                from frappe.utils.safe_exec import safe_exec
                _locals = {
                    "doc": message_doc,
                    "phone_number": self.phone_number,
                    "message": self.message_text,
                    "account": self.account,
                    "response": None  # Script can set this directly
                }
                safe_exec(
                    server_script.script,
                    _locals=_locals,
                    script_filename=server_script.name
                )
                # Check for response in multiple places:
                # 1. _locals["response"] - direct variable assignment
                # 2. frappe.response["message"] - standard Frappe API script pattern
                if _locals.get("response"):
                    return _locals.get("response")
                elif frappe.response.get("message"):
                    return frappe.response.get("message")
                return None
            else:
                # Treat as method path
                return frappe.call(script, doc=message_doc)

        except Exception as e:
            frappe.log_error(
                f"Script execution error for '{script}': {str(e)}",
                "WhatsApp Chatbot Script Error"
            )
            return None

    def is_business_hours(self):
        """Check if current time is within business hours for today."""
        try:
            settings = self.get_chatbot_settings()
            if not settings:
                return True

            if not settings.business_hours:
                return True  # No business hours configured

            now = datetime.now()
            current_time = now.time()
            day_name = now.strftime("%A")  # Monday, Tuesday, etc.

            # Find the business hours entry for today
            for row in settings.business_hours:
                if row.day == day_name:
                    # Check if this day is enabled (open)
                    if not row.enabled:
                        return False  # Closed on this day

                    # Check time range
                    start = self._parse_time(row.start_time)
                    end = self._parse_time(row.end_time)

                    if start and end:
                        return start <= current_time <= end
                    return True  # Day is enabled but no specific times set

            # No entry for this day - default to closed
            return False

        except Exception as e:
            frappe.log_error(f"is_business_hours error: {str(e)}")
        return True  # Default to open if there's an error

    def _parse_time(self, time_value):
        """Parse time value to time object."""
        if not time_value:
            return None

        if isinstance(time_value, str):
            from datetime import time
            try:
                parts = time_value.split(":")
                return time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
            except (ValueError, IndexError):
                return None

        # Already a time object
        return time_value


def process_incoming_message(doc, method=None):
    """
    Hook function called when WhatsApp Message is created.
    Process synchronously but safely - never raise exceptions.
    """
    global _processing_messages

    try:
        # Skip if this is an outgoing message
        if getattr(doc, "type", None) != "Incoming":
            return

        # Skip if flag is set (message created by chatbot)
        if getattr(doc.flags, "ignore_chatbot", False):
            return

        # Skip if already being processed (prevent infinite loops)
        doc_name = getattr(doc, "name", None)
        if not doc_name or doc_name in _processing_messages:
            return

        # Only process text, button, and flow content types
        content_type = getattr(doc, "content_type", None)
        if content_type not in ["text", "button", "flow", "image", "document"]:
            return

        # Quick check if chatbot is enabled (without full initialization)
        try:
            if not frappe.db.exists("WhatsApp Chatbot"):
                return
            enabled = frappe.db.get_single_value("WhatsApp Chatbot", "enabled")
            if not enabled:
                return
        except Exception:
            return

        if content_type in ["text", "button", "flow"]:
            # Extract message data
            message_data = {
                "name": doc_name,
                "from": getattr(doc, "from", None) or getattr(doc, "from_", None),
                "message": getattr(doc, "message", "") or "",
                "content_type": content_type or "text",
                "whatsapp_account": getattr(doc, "whatsapp_account", None),
                "type": "Incoming",
                "flow_response": getattr(doc, "flow_response", None)
            }

            # Mark as being processed to prevent loops
            _processing_messages.add(doc_name)

            try:
                # Process synchronously - this is fast enough and more reliable
                processor = ChatbotProcessor(message_data)
                processor.process()
            finally:
                # Clean up processing flag
                _processing_messages.discard(doc_name)

        elif content_type in ["image", "document"]:
            frappe.enqueue(
                'frappe_whatsapp_chatbot.chatbot.processor.background_media_processor',
                doc_name=doc_name,
                queue='default',
                at_front=True
            )

    except Exception as e:
        # Log error but NEVER re-raise - we must not break the incoming message save
        try:
            frappe.log_error(
                f"process_incoming_message error: {str(e)}",
                "WhatsApp Chatbot Error"
            )
        except Exception:
            pass  # Even logging failed, just continue


def background_media_processor(doc_name):
    """Wait for attachment link and process media message."""
    import time

    # 1. Fetch static data ONCE
    # We get these now so we don't have to keep asking the DB for them in the loop
    msg_data = frappe.db.get_value(
        "WhatsApp Message",
        doc_name,
        ["from", "content_type", "whatsapp_account", "flow_response"],
        as_dict=1
    )

    if not msg_data:
        return

    # 2. Optimized Polling Loop
    media_url = None
    for _ in range(4):
        time.sleep(2)  # Wait a bit for the downloader to update the record

        # Clear transaction cache to see updates from the downloader
        frappe.db.rollback()

        # Only fetch the 'attach' field - much lighter than fetching the whole row
        media_url = frappe.db.get_value("WhatsApp Message", doc_name, "attach")

        if media_url:
            break

    if media_url:
        # Extract message data
        message_data = {
            "name": doc_name,
            "from": getattr(msg_data, "from", None) or getattr(msg_data, "from_", None),
            "message": media_url,
            "content_type": getattr(msg_data, "content_type", ""),
            "whatsapp_account": getattr(msg_data, "whatsapp_account", None),
            "type": "Incoming",
            "flow_response": getattr(msg_data, "flow_response", None)
        }

        # Mark as being processed to prevent loops
        _processing_messages.add(doc_name)

        try:
            # Process synchronously - this is fast enough and more reliable
            processor = ChatbotProcessor(message_data)
            processor.process()
        finally:
            # Clean up processing flag
            _processing_messages.discard(doc_name)
    else:
        frappe.log_error(f"Chatbot Timeout: No media found for {doc_name}", "WhatsApp Chatbot Warning")


def run_processor(message_data):
    """Background job to process message (kept for compatibility)."""
    global _processing_messages

    message_name = message_data.get("name", "unknown")

    try:
        processor = ChatbotProcessor(message_data)
        processor.process()
    except Exception as e:
        frappe.log_error(
            f"run_processor error for {message_name}: {str(e)}",
            "WhatsApp Chatbot Error"
        )
    finally:
        # Clean up processing flag
        _processing_messages.discard(message_name)
