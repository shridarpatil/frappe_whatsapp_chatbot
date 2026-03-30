import frappe
from datetime import datetime, timedelta


class SessionManager:
    """Manage chatbot conversation sessions."""

    def __init__(self, phone_number, whatsapp_account):
        self.phone_number = phone_number
        self.account = whatsapp_account
        self.timeout_minutes = self.get_timeout()

    def get_timeout(self):
        """Get session timeout from settings."""
        try:
            if frappe.db.exists("WhatsApp Chatbot"):
                settings = frappe.get_single("WhatsApp Chatbot")
                return settings.session_timeout_minutes or 30
        except Exception:
            pass
        return 30

    def get_active_session(self):
        """Get active session for this phone number."""
        try:
            # Check for expired sessions first
            self.expire_old_sessions()

            session = frappe.db.get_value(
                "WhatsApp Chatbot Session",
                {
                    "phone_number": self.phone_number,
                    "whatsapp_account": self.account,
                    "status": "Active"
                },
                "name"
            )

            if session:
                return frappe.get_doc("WhatsApp Chatbot Session", session)

            return None

        except Exception as e:
            frappe.log_error(f"SessionManager get_active_session error: {str(e)}")
            return None

    def expire_old_sessions(self):
        """Mark old sessions as timed out."""
        try:
            timeout_threshold = datetime.now() - timedelta(minutes=self.timeout_minutes)

            expired = frappe.get_all(
                "WhatsApp Chatbot Session",
                filters={
                    "status": "Active",
                    "last_activity": ["<", timeout_threshold]
                },
                pluck="name"
            )

            for session_name in expired:
                session = frappe.get_doc("WhatsApp Chatbot Session", session_name)
                session.status = "Timeout"
                session.completed_at = datetime.now()
                session.save(ignore_permissions=True)

                # Send timeout message
                if session.current_flow:
                    flow = frappe.get_doc("WhatsApp Chatbot Flow", session.current_flow)
                    if flow.timeout_message:
                        self.send_timeout_message(session, flow.timeout_message)

            if expired:
                frappe.db.commit()

        except Exception as e:
            frappe.log_error(f"SessionManager expire_old_sessions error: {str(e)}")

    def send_timeout_message(self, session, message):
        """Send session timeout message."""
        try:
            frappe.get_doc({
                "doctype": "WhatsApp Message",
                "type": "Outgoing",
                "to": session.phone_number,
                "message": message,
                "content_type": "text",
                "whatsapp_account": session.whatsapp_account
            }).insert(ignore_permissions=True)
        except Exception as e:
            frappe.log_error(f"SessionManager send_timeout_message error: {str(e)}")

    def get_conversation_history(self, limit=20):
        """Get recent conversation history for AI context."""
        try:
            messages = frappe.get_all(
                "WhatsApp Message",
                filters={
                    "whatsapp_account": self.account,
                    "content_type": ["in", ["text", "image", "document"]]
                },
                or_filters=[
                    ["from", "=", self.phone_number],
                    ["to", "=", self.phone_number]
                ],
                fields=["type", "message", "content_type", "attach", "creation"],
                order_by="creation desc",
                limit=limit
            )

            # Convert to standardized format
            history = []
            for msg in reversed(messages):
                history.append({
                    "direction": "Incoming" if msg.type == "Incoming" else "Outgoing",
                    # If it's a media message, use the attach as the message text
                    "message": msg.attach if msg.content_type in ["image", "document"] else msg.message,
                    "timestamp": msg.creation
                })

            return history

        except Exception as e:
            frappe.log_error(f"SessionManager get_conversation_history error: {str(e)}")
            return []


def cleanup_expired_sessions():
    """Scheduled job to clean up expired sessions."""
    try:
        # Get settings
        if not frappe.db.exists("WhatsApp Chatbot"):
            return

        settings = frappe.get_single("WhatsApp Chatbot")
        if not settings.enabled:
            return

        timeout_minutes = settings.session_timeout_minutes or 30
        timeout_threshold = datetime.now() - timedelta(minutes=timeout_minutes)

        # Find all expired active sessions
        expired_sessions = frappe.get_all(
            "WhatsApp Chatbot Session",
            filters={
                "status": "Active",
                "last_activity": ["<", timeout_threshold]
            },
            fields=["name", "phone_number", "whatsapp_account", "current_flow"]
        )

        for session_data in expired_sessions:
            try:
                session = frappe.get_doc("WhatsApp Chatbot Session", session_data.name)
                session.status = "Timeout"
                session.completed_at = datetime.now()
                session.save(ignore_permissions=True)

                # Send timeout message
                if session_data.current_flow:
                    flow = frappe.get_doc("WhatsApp Chatbot Flow", session_data.current_flow)
                    if flow.timeout_message:
                        frappe.get_doc({
                            "doctype": "WhatsApp Message",
                            "type": "Outgoing",
                            "to": session_data.phone_number,
                            "message": flow.timeout_message,
                            "content_type": "text",
                            "whatsapp_account": session_data.whatsapp_account
                        }).insert(ignore_permissions=True)

            except Exception as e:
                frappe.log_error(
                    f"cleanup_expired_sessions error for {session_data.name}: {str(e)}"
                )

        if expired_sessions:
            frappe.db.commit()

    except Exception as e:
        frappe.log_error(f"cleanup_expired_sessions error: {str(e)}")
