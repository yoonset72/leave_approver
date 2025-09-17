{
    'name': 'HR Leave Custom Approval',
    'version': '17.0.1.0.0',
    'category': 'Human Resources/Time Off',
    'summary': 'Two-level leave approval system with email notifications',
    'description': """
        Custom leave approval workflow with:
        - Two-level approval system (First approver + HR Officers)
        - Email notifications at each stage
        - Access controls based on approver assignments
        - Enhanced leave request views and menus
    """,
    'depends': ['hr', 'hr_holidays', 'mail'],
    'data': [
        'security/hr_leave_security.xml',
        'security/ir.model.access.csv',
        'data/email_templates.xml',
        'views/hr_leave_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}