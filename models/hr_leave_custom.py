from odoo import models, fields, api
from odoo.exceptions import UserError
import logging
import secrets

_logger = logging.getLogger(__name__)

class HrLeave(models.Model):
    _inherit = 'hr.leave'

    first_approver_id = fields.Many2one(
        'res.users', 
        string="First Approver",
        compute='_compute_approvers', 
        store=True, 
        readonly=True
    )
    second_approver_ids = fields.Many2many(
        'res.users',
        'hr_leave_second_approver_rel',  
        'leave_id',
        'user_id',
        string="Second Approvers",
        compute='_compute_approvers', 
        store=True
    )
    approval_token = fields.Char(string="Approval Token")

    @api.depends('employee_id', 'employee_id.leave_manager_id', 'employee_id.hr_officer_ids')
    def _compute_approvers(self):
        for leave in self:
            leave.first_approver_id = False
            leave.second_approver_ids = [(6, 0, [])]

            employee = leave.employee_id
            if not employee:
                continue

            # First approver = manager
            if employee.leave_manager_id and employee.leave_manager_id.active:
                leave.first_approver_id = employee.leave_manager_id.id

            # Second approvers = hr_officer_ids (including manager if present)
            if employee.hr_officer_ids:
                officer_ids = employee.hr_officer_ids.ids
                leave.second_approver_ids = [(6, 0, officer_ids)]
                _logger.info("Leave %s: Second approvers set to %s", leave.id, officer_ids)

    @api.model
    def create(self, vals):
        record = super().create(vals)
        record._generate_approval_token()
        record._compute_approvers()   # 🔑 force compute after create
        return record

    def action_approve(self):
        _logger.info("=== ACTION APPROVE CALLED ===")
        _logger.info("Current user: %s (ID: %s)", self.env.user.name, self.env.user.id)
        
        current_user = self.env.user
        for leave in self:
            _logger.info("Processing leave %s with state: %s", leave.id, leave.state)
            
            try:
                # First approval
                if leave.state == 'confirm':
                    _logger.info("Processing first approval for leave %s", leave.id)
                    
                    if not leave.first_approver_id:
                        _logger.error("No first approver configured for leave %s", leave.id)
                        raise UserError("No first approver configured for this employee.")
                        
                    if current_user != leave.first_approver_id:
                        _logger.error("Wrong approver for first approval. Current: %s, Expected: %s", 
                                    current_user.name, leave.first_approver_id.name)
                        raise UserError("Only the designated first approver can approve at this stage.")

                    _logger.info("Moving leave %s from 'confirm' to 'validate1'", leave.id)
                    leave.write({'state': 'validate1'})
                    leave._send_second_approval_notification()

                # Second approval
                elif leave.state == 'validate1':
                    _logger.info("Processing second approval for leave %s", leave.id)
                    
                    # Case 1: Second approvers exist
                    if leave.second_approver_ids:
                        _logger.info("Second approvers exist: %s", [a.name for a in leave.second_approver_ids])
                        
                        if current_user == leave.first_approver_id:
                            _logger.error("First approver cannot approve at second stage")
                            raise UserError("The first approver cannot approve at the second stage.")
                            
                        if current_user not in leave.second_approver_ids:
                            _logger.error("Current user %s not in second approvers: %s", 
                                        current_user.name, [a.name for a in leave.second_approver_ids])
                            raise UserError("Only designated second approvers can approve at this stage.")
                            
                    # Case 2: No second approvers configured → first approver can finalize
                    else:
                        _logger.info("No second approvers, first approver can finalize")
                        if current_user != leave.first_approver_id:
                            _logger.error("Only first approver can finalize when no second approvers")
                            raise UserError("Only the first approver can finalize this leave request.")

                    _logger.info("Moving leave %s from 'validate1' to 'validate'", leave.id)
                    leave.write({'state': 'validate'})
                    
                    _logger.info("About to call _send_leave_approved_notification for leave %s", leave.id)
                    leave._send_leave_approved_notification()
                    _logger.info("Finished calling _send_leave_approved_notification for leave %s", leave.id)
                
                # Already approved
                elif leave.state == 'validate':
                    _logger.info("Leave %s is already in 'validate' state", leave.id)
                    
                else:
                    _logger.warning("Unexpected state for leave %s: %s", leave.id, leave.state)
                    
            except Exception as e:
                _logger.error("Exception in action_approve for leave %s: %s", leave.id, str(e))
                _logger.exception("Full exception details:")
                raise

        _logger.info("=== ACTION APPROVE COMPLETED ===")
        return True

    def action_confirm(self):
        """Send email to first approver after confirmation."""
        _logger.info("=== ACTION CONFIRM CALLED ===")
        _logger.info("Current user: %s", self.env.user.name)
        
        result = super(HrLeave, self).action_confirm()
        
        for leave in self:
            _logger.info("Leave %s state after confirm: %s", leave.id, leave.state)
            if leave.state == 'confirm':
                _logger.info("Sending first approval notification for leave %s", leave.id)
                leave._send_first_approval_notification()
            else:
                _logger.warning("Leave %s not in 'confirm' state, current state: %s", leave.id, leave.state)
                
        return result

    def _send_first_approval_notification(self):
        """Send notification to first approver"""
        _logger.info("=== SENDING FIRST APPROVAL NOTIFICATION ===")
        _logger.info("Leave ID: %s", self.id)
        
        if not self.first_approver_id:
            _logger.error("No first approver for leave %s", self.id)
            return
            
        _logger.info("First approver: %s (ID: %s)", self.first_approver_id.name, self.first_approver_id.id)
            
        if not self.first_approver_id.email:
            _logger.error("First approver %s has no email for leave %s", self.first_approver_id.login, self.id)
            return
            
        _logger.info("First approver email: %s", self.first_approver_id.email)
        
        template = self.env.ref('leave_approver.email_template_first_approval', raise_if_not_found=False)
        if template:
            _logger.info("Found email template: %s (ID: %s)", template.name, template.id)
            
            try:
                # Create proper context for template rendering
                template_ctx = {
                    'lang': self.first_approver_id.lang or 'en_US',
                    'force_email': True,
                    'default_composition_mode': 'comment',
                    'mark_so_as_sent': True,
                }
                
                # Send email with proper context
                mail_id = template.with_context(**template_ctx).send_mail(
                    self.id, 
                    force_send=True,
                    email_values={
                        'email_to': self.first_approver_id.email,
                        'recipient_ids': [(4, self.first_approver_id.partner_id.id)] if self.first_approver_id.partner_id else []
                    }
                )
                
                _logger.info("First approval email sent for leave %s to %s (Mail ID: %s)", 
                           self.id, self.first_approver_id.email, mail_id)
                
                # Verify mail was created and check content
                if mail_id:
                    mail_record = self.env['mail.mail'].browse(mail_id)
                    _logger.info("Mail record - State: %s, Email to: %s, Subject: %s", 
                               mail_record.state, mail_record.email_to, mail_record.subject)
                    _logger.info("Mail body preview: %s", mail_record.body_html[:200] if mail_record.body_html else 'No body')
                else:
                    _logger.error("No mail ID returned from send_mail")
                    
            except Exception as e:
                _logger.error("Failed sending first approval email for leave %s: %s", self.id, str(e))
                _logger.exception("Full exception details:")
        else:
            _logger.error("Email template 'leave_approver.email_template_first_approval' not found")
            # List available templates for debugging
            all_templates = self.env['mail.template'].search([('model', '=', 'hr.leave')])
            _logger.info("Available hr.leave templates: %s", [t.name for t in all_templates])

    def _send_second_approval_notification(self):
        """Send notification to second approvers (HR officers)."""
        _logger.info("=== SENDING SECOND APPROVAL NOTIFICATION ===")
        _logger.info("Leave ID: %s", self.id)
        
        if not self.second_approver_ids:
            _logger.warning("No second approvers for leave %s", self.id)
            return

        _logger.info("Second approvers: %s", [a.name for a in self.second_approver_ids])

        template = self.env.ref(
            'leave_approver.email_template_second_approval',
            raise_if_not_found=False
        )
        if not template:
            _logger.error("Email template 'leave_approver.email_template_second_approval' not found")
            return

        for approver in self.second_approver_ids:
            _logger.info("Processing second approver: %s", approver.name)
            
            if not approver.email:
                _logger.warning("Second approver %s has no email, skipping", approver.login)
                continue

            try:
                template_ctx = {
                    'lang': approver.lang or 'en_US',
                    'force_email': True,
                    'recipient_user': approver
                }
                
                mail_id = template.with_context(**template_ctx).send_mail(
                    self.id,
                    force_send=True,
                    email_values={
                        'email_to': approver.email,
                        'recipient_ids': [(4, approver.partner_id.id)] if approver.partner_id else []
                    }
                )

                _logger.info("Second approval email sent for leave %s to %s (Mail ID: %s)",
                           self.id, approver.email, mail_id)
            except Exception as e:
                _logger.error("Failed sending second approval email for leave %s to %s: %s",
                           self.id, approver.email, str(e))

    def _send_leave_approved_notification(self):
        """Send notification to employee when leave is approved"""
        try:
            _logger.info("=== SENDING LEAVE APPROVED NOTIFICATION ===")
            _logger.info("Leave ID: %s", self.id)
            _logger.info("Employee: %s", self.employee_id.name if self.employee_id else 'None')
            
            if not self.employee_id:
                _logger.error("No employee for leave %s", self.id)
                return
                
            if not self.employee_id.work_email:
                _logger.error("No work email for employee %s (leave %s)", 
                            self.employee_id.name, self.id)
                return
                
            _logger.info("Employee work email: %s", self.employee_id.work_email)
                
            template = self.env.ref('leave_approver.email_template_leave_approved', raise_if_not_found=False)
            if not template:
                _logger.error("Email template 'leave_approver.email_template_leave_approved' not found")
                # List available templates for debugging
                all_templates = self.env['mail.template'].search([('model', '=', 'hr.leave')])
                _logger.info("Available hr.leave templates: %s", [t.name for t in all_templates])
                return
                
            _logger.info("Found email template: %s (ID: %s)", template.name, template.id)
            
            try:
                template_ctx = {
                    'lang': self.employee_id.user_id.lang if self.employee_id.user_id else 'en_US',
                    'force_email': True,
                }
                
                _logger.info("Sending email with context: %s", template_ctx)
                
                mail_id = template.with_context(**template_ctx).send_mail(
                    self.id, 
                    force_send=True,
                    email_values={
                        'email_to': self.employee_id.work_email,
                        'recipient_ids': [(4, self.employee_id.user_id.partner_id.id)] if self.employee_id.user_id and self.employee_id.user_id.partner_id else []
                    }
                )
                
                _logger.info("Leave approved email sent for leave %s to %s (Mail ID: %s)",
                           self.id, self.employee_id.work_email, mail_id)
                           
                # Verify mail was created and check content
                if mail_id:
                    mail_record = self.env['mail.mail'].browse(mail_id)
                    _logger.info("Mail record - State: %s, Email to: %s, Subject: %s", 
                               mail_record.state, mail_record.email_to, mail_record.subject)
                else:
                    _logger.error("No mail ID returned from send_mail")
                    
            except Exception as e:
                _logger.error("Failed sending leave approved email for leave %s: %s", self.id, str(e))
                _logger.exception("Full exception details:")
                
        except Exception as e:
            _logger.error("Exception in _send_leave_approved_notification for leave %s: %s", self.id, str(e))
            _logger.exception("Full exception details:")

    def write(self, vals):
        """Enforce approval rules also on direct write"""
        _logger.info("=== WRITE METHOD CALLED ===")
        _logger.info("Values: %s", vals)
        _logger.info("Current user: %s", self.env.user.name)
        
        if 'state' in vals:
            new_state = vals.get('state')
            current_user = self.env.user
            
            _logger.info("State change requested to: %s", new_state)

            for leave in self:
                _logger.info("Processing leave %s (current state: %s)", leave.id, leave.state)
                
                if new_state == 'validate1':
                    if current_user != leave.first_approver_id:
                        _logger.error("Unauthorized state change to validate1 by %s", current_user.name)
                        raise UserError("Only the first approver can move this request to second approval.")

                if new_state == 'validate':
                    # Case 1: Second approvers exist
                    if leave.second_approver_ids:
                        if current_user == leave.first_approver_id:
                            _logger.error("First approver cannot finalize when second approvers exist")
                            raise UserError("The first approver cannot approve at the second stage.")
                        if current_user not in leave.second_approver_ids:
                            _logger.error("Unauthorized final approval by %s", current_user.name)
                            raise UserError("Only designated second approvers can approve this request.")
                    # Case 2: No second approvers exist
                    else:
                        if current_user != leave.first_approver_id:
                            _logger.error("Only first approver can finalize when no second approvers")
                            raise UserError("Only the first approver can finalize this request.")

        result = super(HrLeave, self).write(vals)
        
        # Send approved notification after successful state change to 'validate'
        if 'state' in vals and vals.get('state') == 'validate':
            for leave in self:
                if leave.state == 'validate':  # Double-check the state was actually changed
                    _logger.info("Leave %s approved, sending notification to employee", leave.id)
                    try:
                        leave._send_leave_approved_notification()
                    except Exception as e:
                        _logger.error("Failed to send approved notification for leave %s: %s", leave.id, str(e))
                        _logger.exception("Full exception details:")
        
        _logger.info("Write method completed successfully")
        return result

    @api.model
    def debug_template_processing(self, leave_id):
        """Debug method to test template variable processing"""
        _logger.info("=== DEBUGGING TEMPLATE PROCESSING ===")
        leave = self.browse(leave_id)
        template = self.env.ref(
            'leave_approver.email_template_first_approval',
            raise_if_not_found=False
        )
        
        if not template:
            return {'error': 'Template not found'}
        
        try:
            # Get the template body
            body_html = template.body_html
            _logger.info("Raw template: %s", body_html)
            
            # Render the template with proper context
            rendered = template._render_field(
                'body_html',
                [leave.id],
                compute_lang=True
            )[leave.id]
            _logger.info("Rendered template: %s", rendered)
            
            # Also test subject rendering
            subject_rendered = template._render_field(
                'subject',
                [leave.id],
                compute_lang=True
            )[leave.id]
            
            return {
                'success': True,
                'raw_template': body_html,
                'rendered_template': rendered,
                'raw_subject': template.subject,
                'rendered_subject': subject_rendered,
                'variables': {
                    'employee_name': leave.employee_id.name,
                    'first_approver': leave.first_approver_id.name if leave.first_approver_id else 'None',
                    'leave_type': leave.holiday_status_id.name,
                    'leave_id': leave.id,
                    'date_from': leave.request_date_from,
                    'date_to': leave.request_date_to,
                    'days': leave.number_of_days
                }
            }
        except Exception as e:
            _logger.error("Template rendering failed: %s", str(e))
            _logger.exception("Full exception details:")
            return {'error': str(e)}

    @api.model
    def debug_email_config(self):
        """Debug method to check email configuration"""
        _logger.info("=== EMAIL CONFIGURATION DEBUG ===")
        
        # Check mail server configuration
        mail_servers = self.env['ir.mail_server'].search([])
        _logger.info("Mail servers found: %s", len(mail_servers))
        for server in mail_servers:
            _logger.info("Server: %s, Host: %s, Port: %s, User: %s", 
                       server.name, server.smtp_host, server.smtp_port, server.smtp_user)
        
        # Check system parameters
        system_params = self.env['ir.config_parameter'].sudo()
        mail_catchall = system_params.get_param('mail.catchall.domain')
        _logger.info("Mail catchall domain: %s", mail_catchall)
        
        # Check automated actions
        automated_actions = self.env['base.automation'].search([
            ('model_id.model', '=', 'hr.leave')
        ])
        _logger.info("Automated actions for hr.leave: %s", len(automated_actions))
        for action in automated_actions:
            _logger.info("Action: %s, Active: %s, Trigger: %s", 
                       action.name, action.active, action.trigger)

    def _generate_approval_token(self):
        self.approval_token = secrets.token_urlsafe(16)
        return self.approval_token

    def create(self, vals):
        record = super().create(vals)
        record._generate_approval_token()
        return record

    @api.model
    def debug_leave_approval_flow(self, leave_id):
        """Debug method to test the entire approval flow"""
        _logger.info("=== DEBUGGING LEAVE APPROVAL FLOW ===")
        leave = self.browse(leave_id)
        
        result = {
            'leave_id': leave.id,
            'current_state': leave.state,
            'first_approver': leave.first_approver_id.name if leave.first_approver_id else 'None',
            'second_approvers': [a.name for a in leave.second_approver_ids],
            'employee': leave.employee_id.name,
            'employee_email': leave.employee_id.work_email,
            'templates': {}
        }
        
        # Check all required templates exist
        template_names = [
            'leave_approver.email_template_first_approval',
            'leave_approver.email_template_second_approval', 
            'leave_approver.email_template_leave_approved'
        ]
        
        for template_name in template_names:
            template = self.env.ref(template_name, raise_if_not_found=False)
            result['templates'][template_name] = {
                'exists': template is not None,
                'name': template.name if template else 'Not found',
                'id': template.id if template else None
            }
        
        return result