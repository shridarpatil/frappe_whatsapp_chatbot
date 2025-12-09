import frappe
from frappe.model.document import Document


class WhatsAppChatbotFlow(Document):
    def validate(self):
        self.validate_steps()
        self.validate_completion_action()

    def validate_steps(self):
        if not self.steps:
            frappe.throw("Please add at least one step to the flow")

        step_names = []
        for step in self.steps:
            if step.step_name in step_names:
                frappe.throw(f"Duplicate step name: {step.step_name}")
            step_names.append(step.step_name)

            # Validate next_step references
            if step.next_step and step.next_step not in step_names:
                # It might reference a later step, so we'll check after collecting all names
                pass

            # Validate conditional_next references
            if step.conditional_next:
                import json
                try:
                    conditions = json.loads(step.conditional_next)
                    for target in conditions.values():
                        if target and target not in step_names:
                            # Will validate after all steps are collected
                            pass
                except json.JSONDecodeError:
                    frappe.throw(f"Invalid JSON in conditional_next for step {step.step_name}")

            # Validate buttons JSON only for Button input type (skip if using Script for dynamic buttons)
            if step.input_type == "Button" and step.message_type != "Script":
                import json
                # Skip empty or default values
                if not step.buttons or step.buttons in ("{}", "[]", ""):
                    frappe.throw(f"Buttons are required for step {step.step_name}")
                try:
                    buttons = json.loads(step.buttons) if isinstance(step.buttons, str) else step.buttons
                    if not isinstance(buttons, list) or not buttons:
                        frappe.throw(f"Buttons must be a non-empty JSON array for step {step.step_name}")
                except json.JSONDecodeError:
                    frappe.throw(f"Invalid JSON in buttons for step {step.step_name}")

        # Second pass: validate all step references
        for step in self.steps:
            if step.next_step and step.next_step not in step_names:
                frappe.throw(f"Step '{step.step_name}' references non-existent step '{step.next_step}'")

            if step.conditional_next:
                import json
                conditions = json.loads(step.conditional_next)
                for key, target in conditions.items():
                    if target and target not in step_names:
                        frappe.throw(f"Step '{step.step_name}' conditional_next references non-existent step '{target}'")

    def validate_completion_action(self):
        if self.on_complete_action == "Create Document":
            if not self.create_doctype:
                frappe.throw("Please select a DocType for 'Create Document' action")
            if not self.field_mapping:
                frappe.throw("Please provide field mapping for 'Create Document' action")

            import json
            try:
                json.loads(self.field_mapping)
            except json.JSONDecodeError:
                frappe.throw("Field mapping must be valid JSON")

        elif self.on_complete_action == "Call API":
            if not self.api_endpoint:
                frappe.throw("Please provide API endpoint for 'Call API' action")

        elif self.on_complete_action == "Run Script":
            if not self.custom_script:
                frappe.throw("Please provide custom script for 'Run Script' action")
