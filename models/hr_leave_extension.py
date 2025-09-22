from odoo import models, fields, api
import hashlib
import hmac
import time

class HrLeave(models.Model):
    _inherit = 'hr.leave'
    
    def _generate_approval_token(self):
        """Generate a secure token for email approval links"""
        # Create a unique string based on leave details and timestamp
        unique_string = f"{self.id}-{self.employee_id.id}-{self.create_date}-{time.time()}"
        
        # Use HMAC for security (you should set a secret key in your config)
        secret_key = self.env['ir.config_parameter'].sudo().get_param('leave_approval.secret_key', 'default-secret-key')
        
        # Generate token
        token = hmac.new(
            secret_key.encode('utf-8'),
            unique_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()[:32]  # Use first 32 characters
        
        return token
    
    @api.model
    def send_approval_notifications(self):
        """Enhanced method to send approval notifications with new buttons"""
        # This method can be called when leave state changes
        # to trigger the appropriate email templates
        
        if self.state == 'confirm' and self.first_approver_id:
            # Send first approval email
            template = self.env.ref('your_module.email_template_first_approval', False)
            if template:
                template.send_mail(self.id, force_send=True)
                
        elif self.state == 'validate1' and self.second_approver_id:
            # Send second approval email
            template = self.env.ref('your_module.email_template_second_approval', False)
            if template:
                template.send_mail(self.id, force_send=True)
                
        elif self.state == 'validate':
            # Send approved notification to employee
            template = self.env.ref('your_module.email_template_leave_approved', False)
            if template:
                template.send_mail(self.id, force_send=True)
    
    def action_approve(self):
        """Override to send notifications when approved"""
        result = super().action_approve()
        self.send_approval_notifications()
        return result
    
    def action_validate(self):
        """Override to send notifications when validated"""
        result = super().action_validate()
        self.send_approval_notifications()
        return result