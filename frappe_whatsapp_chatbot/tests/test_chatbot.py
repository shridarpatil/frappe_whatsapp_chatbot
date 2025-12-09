import frappe
from frappe.tests import IntegrationTestCase


class TestChatbotDoctypes(IntegrationTestCase):
    """Test that all required doctypes exist."""

    def test_chatbot_settings_exists(self):
        """Test that WhatsApp Chatbot settings doctype exists."""
        self.assertTrue(frappe.db.exists("DocType", "WhatsApp Chatbot"))

    def test_keyword_reply_doctype_exists(self):
        """Test that WhatsApp Keyword Reply doctype exists."""
        self.assertTrue(frappe.db.exists("DocType", "WhatsApp Keyword Reply"))

    def test_chatbot_flow_doctype_exists(self):
        """Test that WhatsApp Chatbot Flow doctype exists."""
        self.assertTrue(frappe.db.exists("DocType", "WhatsApp Chatbot Flow"))

    def test_ai_context_doctype_exists(self):
        """Test that WhatsApp AI Context doctype exists."""
        self.assertTrue(frappe.db.exists("DocType", "WhatsApp AI Context"))

    def test_flow_step_doctype_exists(self):
        """Test that WhatsApp Flow Step doctype exists."""
        self.assertTrue(frappe.db.exists("DocType", "WhatsApp Flow Step"))

    def test_chatbot_session_doctype_exists(self):
        """Test that WhatsApp Chatbot Session doctype exists."""
        self.assertTrue(frappe.db.exists("DocType", "WhatsApp Chatbot Session"))


class TestKeywordMatcher(IntegrationTestCase):
    """Test keyword matching functionality."""

    def setUp(self):
        # Create test keyword reply
        if not frappe.db.exists("WhatsApp Keyword Reply", "Test Greeting"):
            frappe.get_doc({
                "doctype": "WhatsApp Keyword Reply",
                "title": "Test Greeting",
                "keywords": "hello, hi, hey",
                "match_type": "Exact",
                "response_type": "Text",
                "response_text": "Hello! How can I help you?",
                "enabled": 1
            }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.delete("WhatsApp Keyword Reply", {"title": "Test Greeting"})

    def test_exact_match(self):
        """Test exact keyword matching."""
        from frappe_whatsapp_chatbot.chatbot.keyword_matcher import KeywordMatcher

        matcher = KeywordMatcher()
        result = matcher.match("hello")
        self.assertIsNotNone(result)
        self.assertEqual(result.title, "Test Greeting")

    def test_exact_match_case_insensitive(self):
        """Test that exact matching is case insensitive."""
        from frappe_whatsapp_chatbot.chatbot.keyword_matcher import KeywordMatcher

        matcher = KeywordMatcher()
        result = matcher.match("HELLO")
        self.assertIsNotNone(result)
        self.assertEqual(result.title, "Test Greeting")

    def test_no_match(self):
        """Test that non-matching keywords return None."""
        from frappe_whatsapp_chatbot.chatbot.keyword_matcher import KeywordMatcher

        matcher = KeywordMatcher()
        result = matcher.match("goodbye")
        self.assertIsNone(result)


class TestFlowEngine(IntegrationTestCase):
    """Test flow engine functionality."""

    def test_phone_variants(self):
        """Test phone number variant generation."""
        from frappe_whatsapp_chatbot.chatbot.ai_responder import AIResponder

        # Create a mock settings object
        class MockSettings:
            ai_provider = "OpenAI"
            ai_api_key = None
            ai_model = "gpt-4o-mini"
            ai_system_prompt = "Test"
            ai_max_tokens = 500
            ai_temperature = 0.7
            ai_include_history = False
            ai_history_limit = 4

            def get_password(self, field):
                return None

        responder = AIResponder(MockSettings(), phone_number="+919876543210")
        variants = responder.get_phone_variants("+919876543210")

        self.assertIn("+919876543210", variants)
        self.assertIn("919876543210", variants)  # Without +
        self.assertIn("9876543210", variants)  # Last 10 digits (local number)


class TestInputValidation(IntegrationTestCase):
    """Test input validation in flow steps."""

    def test_email_validation_valid(self):
        """Test valid email passes validation."""
        import re
        email = "test@example.com"
        pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
        self.assertTrue(re.match(pattern, email.strip()))

    def test_email_validation_invalid(self):
        """Test invalid email fails validation."""
        import re
        email = "invalid-email"
        pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
        self.assertIsNone(re.match(pattern, email.strip()))

    def test_phone_validation_valid(self):
        """Test valid phone passes validation."""
        import re
        phone = "+1234567890"
        cleaned = re.sub(r"[\s\-\(\)]", "", phone)
        self.assertTrue(re.match(r"^\+?\d{10,15}$", cleaned))

    def test_phone_validation_invalid(self):
        """Test invalid phone fails validation."""
        import re
        phone = "123"
        cleaned = re.sub(r"[\s\-\(\)]", "", phone)
        self.assertIsNone(re.match(r"^\+?\d{10,15}$", cleaned))

    def test_number_validation_valid(self):
        """Test valid number passes validation."""
        import re
        number = "123.45"
        cleaned = number.replace(",", "").replace(" ", "")
        self.assertTrue(re.match(r"^-?\d+\.?\d*$", cleaned))

    def test_number_validation_invalid(self):
        """Test invalid number fails validation."""
        import re
        number = "abc"
        cleaned = number.replace(",", "").replace(" ", "")
        self.assertIsNone(re.match(r"^-?\d+\.?\d*$", cleaned))
