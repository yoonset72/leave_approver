from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class HrLeaveEmailDebug(models.Model):
    _inherit = 'hr.leave'

    def debug_email_settings(self):
        """Debug method to check email configuration"""
        _logger.info("=== EMAIL DEBUG INFO ===")
        
        # Check mail server configuration
        mail_servers = self.env['ir.mail_server'].search([])
        if mail_servers:
            for server in mail_servers:
                _logger.info(f"Mail Server: {server.name} - {server.smtp_host}:{server.smtp_port}")
        else:
            _logger.warning("No mail servers configured!")
        
        # Check outgoing mail queue
        pending_mails = self.env['mail.mail'].search([('state', '=', 'outgoing')])
        _logger.info(f"Pending emails in queue: {len(pending_mails)}")
        
        # Check failed mails
        failed_mails = self.env['mail.mail'].search([('state', '=', 'exception')])
        if failed_mails:
            _logger.warning(f"Failed emails: {len(failed_mails)}")
            for mail in failed_mails[:5]:  # Show first 5 failed emails
                _logger.warning(f"Failed email to {mail.email_to}: {mail.failure_reason}")
        
        # Check system parameters
        catchall = self.env['ir.config_parameter'].sudo().get_param('mail.catchall.domain')
        bounce_alias = self.env['ir.config_parameter'].sudo().get_param('mail.bounce.alias')
        _logger.info(f"Catchall domain: {catchall}")
        _logger.info(f"Bounce alias: {bounce_alias}")
        
        return True

    def test_send_email(self):
        """Test method to send a simple email"""
        if not self.first_approver_id or not self.first_approver_id.email:
            _logger.error("No first approver or email found")
            return False
            
        try:
            mail_values = {
                'subject': 'Test Email from Odoo Leave System',
                'body_html': '''
                    <p>This is a test email to verify email functionality.</p>
                    <p>If you receive this, the email system is working correctly.</p>
                ''',
                'email_to': self.first_approver_id.email,
                'email_from': self.env.user.email or 'noreply@company.com',
                'auto_delete': False,
            }
            mail = self.env['mail.mail'].create(mail_values)
            mail.send()
            _logger.info(f"Test email sent to {self.first_approver_id.email}")
            return True
        except Exception as e:
            _logger.error(f"Test email failed: {str(e)}")
            return False