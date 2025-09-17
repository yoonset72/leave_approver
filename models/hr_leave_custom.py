# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class HrLeave(models.Model):
    _inherit = 'hr.leave'

    # Extended workflow states
    state = fields.Selection([
        ('draft', 'To Submit'),
        ('cancel', 'Cancelled'),
        ('confirm', 'To Approve'),
        ('refuse', 'Refused'),
        ('validate1', 'Second Approval'),
        ('validate', 'Approved'),
    ], string='Status', readonly=True, tracking=True, copy=False, default='draft',
       help="The status is 'To Submit' when created.\n"
            "The status is 'To Approve' when confirmed.\n"
            "The status is 'Second Approval' after first approval.\n"
            "The status is 'Approved' after final approval.")

    # Approvers
    first_approver_id = fields.Many2one(
        'res.users',
        string='First Approver',
        compute='_compute_approvers',
        store=True
    )

    second_approver_ids = fields.Many2many(
        'res.users',
        'leave_second_approver_rel',
        'leave_id',
        'user_id',
        string='Second Approvers',
        compute='_compute_approvers',
        store=True
    )

    # Computed rights
    can_approve_first = fields.Boolean(
        'Can Approve (First Level)',
        compute='_compute_can_approve',
        store=True
    )

    can_approve_second = fields.Boolean(
        'Can Approve (Second Level)',
        compute='_compute_can_approve',
        store=True
    )

    # --- Approver Computations ---
    @api.depends('employee_id', 'employee_id.leave_manager_id')
    def _compute_approvers(self):
        for leave in self:
            leave.first_approver_id = leave.employee_id.leave_manager_id.user_id if leave.employee_id.leave_manager_id else False
            second_approver_users = leave.employee_id.hr_officer_ids.mapped('user_id').filtered(lambda u: u.active) if leave.employee_id.hr_officer_ids else self.env['res.users']
            leave.second_approver_ids = [(6, 0, second_approver_users.ids)]

    @api.depends('first_approver_id', 'second_approver_ids', 'state')
    def _compute_can_approve(self):
        user = self.env.user
        for leave in self:
            leave.can_approve_first = bool(
                leave.first_approver_id and
                user == leave.first_approver_id and
                leave.state == 'confirm'
            )
            leave.can_approve_second = bool(
                leave.second_approver_ids and
                user in leave.second_approver_ids and
                leave.state == 'validate1'
            )

    # --- Actions ---
    def action_confirm(self):
        """Notify first approver when confirmed"""
        res = super().action_confirm()
        for leave in self:
            if leave.first_approver_id and leave.first_approver_id.email:
                leave._send_first_approval_notification()
                _logger.info("Leave %s confirmed, email sent to %s", leave.id, leave.first_approver_id.email)
            else:
                _logger.warning("Leave %s confirmed but no email for approver", leave.id)
        return res

    def action_approve(self):
        """Two-level approval process"""
        for leave in self:
            if leave.state == 'confirm':
                if self.env.user == leave.first_approver_id:
                    leave.write({'state': 'validate1'})
                    leave._send_second_approval_notification()
                    _logger.info("First approval by %s for leave %s", self.env.user.name, leave.id)
                else:
                    raise UserError(_("You are not authorized for first-level approval."))

            elif leave.state == 'validate1':
                if self.env.user in leave.second_approver_ids:
                    leave.write({'state': 'validate'})
                    leave._send_final_approval_notification()
                    _logger.info("Final approval by %s for leave %s", self.env.user.name, leave.id)
                else:
                    raise UserError(_("You are not authorized for second-level approval."))

            else:
                if self.env.user.has_group('hr_holidays.group_hr_holidays_manager'):
                    return super().action_approve()
                else:
                    raise UserError(_("Invalid state for approval."))

        return True

    def action_refuse(self):
        """Notify employee on refusal"""
        res = super().action_refuse()
        for leave in self:
            leave._send_refusal_notification()
        return res

    # --- Email Notifications ---
    def _send_first_approval_notification(self):
        if not self.first_approver_id or not self.first_approver_id.email:
            return
        try:
            template = self.env.ref('hr_leave_custom.email_template_first_approval', raise_if_not_found=False)
            if template:
                template.with_context(email_to=self.first_approver_id.email).send_mail(self.id, force_send=True)
            else:
                self._send_fallback_email(self.first_approver_id.email, "Leave Approval Required", self.employee_id.name)
        except Exception as e:
            _logger.error("Error sending first approval email: %s", str(e))

    def _send_second_approval_notification(self):
        approvers = self.second_approver_ids.filtered('email')
        if not approvers:
            return
        try:
            template = self.env.ref('hr_leave_custom.email_template_second_approval', raise_if_not_found=False)
            if template:
                for approver in approvers:
                    template.with_context(email_to=approver.email).send_mail(self.id, force_send=True)
            else:
                for approver in approvers:
                    self._send_fallback_email(approver.email, "Second Approval Needed", self.employee_id.name)
        except Exception as e:
            _logger.error("Error sending second approval email: %s", str(e))

    def _send_final_approval_notification(self):
        employee_email = self.employee_id.work_email or self.employee_id.personal_email
        if not employee_email:
            return
        try:
            template = self.env.ref('hr_leave_custom.email_template_final_approval', raise_if_not_found=False)
            if template:
                template.send_mail(self.id, force_send=True)
            else:
                self._send_fallback_email(employee_email, "Leave Approved", self.employee_id.name)
        except Exception as e:
            _logger.error("Error sending final approval email: %s", str(e))

    def _send_refusal_notification(self):
        employee_email = self.employee_id.work_email or self.employee_id.personal_email
        if not employee_email:
            return
        try:
            template = self.env.ref('hr_leave_custom.email_template_refusal', raise_if_not_found=False)
            if template:
                template.send_mail(self.id, force_send=True)
            else:
                self._send_fallback_email(employee_email, "Leave Refused", self.employee_id.name)
        except Exception as e:
            _logger.error("Error sending refusal email: %s", str(e))

    def _send_fallback_email(self, email_to, subject, employee_name):
        try:
            mail_values = {
                'subject': subject,
                'body_html': f"<p>Leave request for {employee_name}</p>",
                'email_to': email_to,
                'email_from': self.env.user.email or 'noreply@company.com',
                'auto_delete': False,
            }
            mail = self.env['mail.mail'].create(mail_values)
            mail.send()
        except Exception as e:
            _logger.error("Fallback email failed: %s", str(e))

    # --- Responsible Approver ---
    @api.model
    def _get_responsible_for_approval(self):
        if self.state == 'confirm':
            return self.first_approver_id
        elif self.state == 'validate1':
            return self.second_approver_ids
        return self.env['res.users']
