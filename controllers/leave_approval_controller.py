from odoo import http, fields
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class LeaveViewController(http.Controller):
    """Controller for viewing leave requests only - approval functionality removed"""
    
    @http.route('/leave/view_requests', type='http', auth='none', methods=['GET'], csrf=False)
    def view_all_requests(self, **kw):
        """Show all leave requests assigned to the approver with enhanced filtering"""
        try:
            token = kw.get('token')
            approver_id = kw.get('approver_id')
            status_filter = kw.get('status', 'all')
            department_filter = kw.get('department', 'all')
            search_term = (kw.get('search') or '').strip()  # remove extra spaces

            if not token or not approver_id:
                return self._render_error_page("Invalid parameters")

            approver = request.env['res.users'].sudo().browse(int(approver_id))
            if not approver.exists():
                return self._render_error_page("Approver not found")

            # Base domain for approver
            domain = [
                '|',
                ('first_approver_id', '=', approver.id),
                ('second_approver_id', '=', approver.id)
            ]

            # Status filtering
            if status_filter == 'to_approve':
                domain.append(('state', '=', 'confirm'))
            elif status_filter == 'second_approval':
                domain.append(('state', '=', 'validate1'))
            elif status_filter == 'approved':
                domain.append(('state', '=', 'validate'))
            else:
                domain.append(('state', 'in', ['draft', 'confirm', 'validate1', 'validate', 'refuse']))

            # Add search domain only if search_term is not empty
            if search_term:
                search_domain = [
                    '|', '|', '|',
                    ('employee_id.name', 'ilike', search_term),
                    ('holiday_status_id.name', 'ilike', search_term),
                    ('name', 'ilike', search_term),
                    ('employee_id.department_id.name', 'ilike', search_term)
                ]
                domain = domain + search_domain

            # Fetch all leaves matching domain
            all_leaves = request.env['hr.leave'].sudo().search(domain)

            # Department filter
            if department_filter != 'all':
                all_leaves = all_leaves.filtered(
                    lambda l: l.employee_id.department_id.name == department_filter
                )

            # Sort by creation date (newest first)
            all_leaves = all_leaves.sorted(
                key=lambda r: r.create_date or fields.Datetime.now(), reverse=True
            )

            # Unique departments for sidebar
            departments = list(set([
                leave.employee_id.department_id.name
                for leave in all_leaves
                if leave.employee_id.department_id
            ]))

            # Pagination
            page = int(kw.get('page', 1))
            per_page = 10
            total_count = len(all_leaves)
            start_index = (page - 1) * per_page
            end_index = start_index + per_page
            paginated_leaves = all_leaves[start_index:end_index]

            total_pages = (total_count + per_page - 1) // per_page

            return self._render_requests_page(
                paginated_leaves, approver, status_filter, department_filter,
                search_term, departments, page, total_pages, total_count, kw
            )

        except Exception as e:
            _logger.error(f"View requests error: {e}")
        return self._render_error_page("An error occurred while loading requests")

    
    def _render_requests_page(self, leaves, approver, status_filter, department_filter, 
                            search_term, departments, current_page, total_pages, total_count, kw):
        """Render page showing all requests with Odoo-style interface"""
        
        # Build table rows
        table_rows = ""
        for leave in leaves:
            status_display = {
                'draft': 'Draft',
                'confirm': 'To Approve',
                'validate1': 'Second Approval',
                'validate': 'Approved',
                'refuse': 'Refused'
            }.get(leave.state, leave.state.title())
            
            status_color = {
                'draft': '#6c757d',
                'confirm': '#ffc107',
                'validate1': '#17a2b8',
                'validate': '#28a745',
                'refuse': '#dc3545'
            }.get(leave.state, '#6c757d')
            
            description = leave.name if leave.name else '...'
            from_date = leave.request_date_from.strftime('%m/%d/%Y') if leave.request_date_from else ''
            to_date = leave.request_date_to.strftime('%m/%d/%Y') if leave.request_date_to else ''
            created_date = leave.create_date.strftime('%m/%d/%Y %H:%M:%S') if leave.create_date else ''
            duration = f"{leave.number_of_days} days" if leave.number_of_days else ""
            
            table_rows += f"""
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #e9ecef;">
                    <div style="display: flex; align-items: center;">
                        <div style="width: 20px; height: 20px; border-radius: 50%; background: #007bff; color: white; display: flex; align-items: center; justify-content: center; font-size: 10px; margin-right: 8px;">
                            {leave.employee_id.name[:2].upper()}
                        </div>
                        {leave.employee_id.name}
                    </div>
                </td>
                <td style="padding: 12px; border-bottom: 1px solid #e9ecef;">{leave.holiday_status_id.name}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e9ecef; color: #6c757d;">{description}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e9ecef;">{from_date}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e9ecef;">{to_date}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e9ecef;">{created_date}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e9ecef;">{duration}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e9ecef;">
                    <span style="background: {status_color}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 500;">
                        {status_display}
                    </span>
                </td>
            </tr>
            """
        
        # Build pagination
        pagination_html = ""
        if total_pages > 1:
            # Previous button
            prev_disabled = "disabled" if current_page <= 1 else ""
            prev_link = f"?token={kw.get('token', '')}&approver_id={approver.id}&status={status_filter}&department={department_filter}&search={search_term}&page={current_page-1}" if current_page > 1 else "#"
            
            # Next button  
            next_disabled = "disabled" if current_page >= total_pages else ""
            next_link = f"?token={kw.get('token', '')}&approver_id={approver.id}&status={status_filter}&department={department_filter}&search={search_term}&page={current_page+1}" if current_page < total_pages else "#"
            
            pagination_html = f"""
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 15px 20px; border-top: 1px solid #e9ecef; background: #f8f9fa;">
                <span style="color: #6c757d; font-size: 14px;">
                    {((current_page-1) * 10) + 1}-{min(current_page * 10, total_count)} / {total_count}
                </span>
                <div style="display: flex; gap: 5px;">
                    <a href="{prev_link}" style="padding: 6px 12px; background: {'#e9ecef' if prev_disabled else '#007bff'}; color: {'#6c757d' if prev_disabled else 'white'}; text-decoration: none; border-radius: 4px; font-size: 14px; {'pointer-events: none;' if prev_disabled else ''}">‹</a>
                    <a href="{next_link}" style="padding: 6px 12px; background: {'#e9ecef' if next_disabled else '#007bff'}; color: {'#6c757d' if next_disabled else 'white'}; text-decoration: none; border-radius: 4px; font-size: 14px; {'pointer-events: none;' if next_disabled else ''}">›</a>
                </div>
            </div>
            """
        
        # Build status filters
        status_filters = f"""
        <div style="margin-bottom: 20px;">
            <h6 style="margin: 0 0 10px 0; color: #495057; font-size: 12px; text-transform: uppercase; font-weight: 600;">STATUS</h6>
            <div style="display: flex; flex-direction: column; gap: 5px;">
                <a href="?token={kw.get('token', '')}&approver_id={approver.id}&status=all&department={department_filter}&search={search_term}" 
                   style="padding: 8px 12px; color: {'#007bff' if status_filter == 'all' else '#6c757d'}; text-decoration: none; border-radius: 4px; background: {'#e3f2fd' if status_filter == 'all' else 'transparent'}; font-size: 14px;">
                   All
                </a>
                <a href="?token={kw.get('token', '')}&approver_id={approver.id}&status=to_approve&department={department_filter}&search={search_term}" 
                   style="padding: 8px 12px; color: {'#007bff' if status_filter == 'to_approve' else '#6c757d'}; text-decoration: none; border-radius: 4px; background: {'#e3f2fd' if status_filter == 'to_approve' else 'transparent'}; font-size: 14px;">
                   To Approve
                </a>
                <a href="?token={kw.get('token', '')}&approver_id={approver.id}&status=second_approval&department={department_filter}&search={search_term}" 
                   style="padding: 8px 12px; color: {'#007bff' if status_filter == 'second_approval' else '#6c757d'}; text-decoration: none; border-radius: 4px; background: {'#e3f2fd' if status_filter == 'second_approval' else 'transparent'}; font-size: 14px;">
                   Second Approval
                </a>
                <a href="?token={kw.get('token', '')}&approver_id={approver.id}&status=approved&department={department_filter}&search={search_term}" 
                   style="padding: 8px 12px; color: {'#007bff' if status_filter == 'approved' else '#6c757d'}; text-decoration: none; border-radius: 4px; background: {'#e3f2fd' if status_filter == 'approved' else 'transparent'}; font-size: 14px;">
                   Approved
                </a>
            </div>
        </div>
        """
        
        # Build department filters
        department_filters = ""
        if departments:
            dept_links = f"""
            <a href="?token={kw.get('token', '')}&approver_id={approver.id}&status={status_filter}&department=all&search={search_term}" 
               style="padding: 8px 12px; color: {'#007bff' if department_filter == 'all' else '#6c757d'}; text-decoration: none; border-radius: 4px; background: {'#e3f2fd' if department_filter == 'all' else 'transparent'}; font-size: 14px; display: block;">
               All
            </a>
            """
            for dept in sorted(departments):
                dept_links += f"""
                <a href="?token={kw.get('token', '')}&approver_id={approver.id}&status={status_filter}&department={dept}&search={search_term}" 
                   style="padding: 8px 12px; color: {'#007bff' if department_filter == dept else '#6c757d'}; text-decoration: none; border-radius: 4px; background: {'#e3f2fd' if department_filter == dept else 'transparent'}; font-size: 14px; display: block;">
                   {dept}
                </a>
                """
            
            department_filters = f"""
            <div>
                <h6 style="margin: 0 0 10px 0; color: #495057; font-size: 12px; text-transform: uppercase; font-weight: 600;">DEPARTMENT</h6>
                <div style="display: flex; flex-direction: column; gap: 5px;">
                    {dept_links}
                </div>
            </div>
            """
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>All Time Off</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
                    background: #f8f9fa;
                    color: #495057;
                    font-size: 14px;
                }}
                .header {{
                    background: white;
                    border-bottom: 1px solid #dee2e6;
                    padding: 15px 20px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }}
                .header h1 {{
                    font-size: 18px;
                    font-weight: 600;
                    color: #495057;
                }}
                .search-box {{
                    position: relative;
                }}
                .search-box input {{
                    padding: 8px 12px;
                    border: 1px solid #ced4da;
                    border-radius: 4px;
                    font-size: 14px;
                    width: 300px;
                }}
                .search-box button {{
                    position: absolute;
                    right: 5px;
                    top: 50%;
                    transform: translateY(-50%);
                    background: none;
                    border: none;
                    cursor: pointer;
                    padding: 5px;
                }}
                .main-content {{
                    display: flex;
                    min-height: calc(100vh - 60px);
                }}
                .sidebar {{
                    width: 200px;
                    background: white;
                    border-right: 1px solid #dee2e6;
                    padding: 20px;
                }}
                .content-area {{
                    flex: 1;
                    background: white;
                    margin: 0;
                }}
                .table-container {{
                    overflow-x: auto;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    background: white;
                }}
                th {{
                    background: #f8f9fa;
                    padding: 12px;
                    text-align: left;
                    font-weight: 600;
                    color: #495057;
                    border-bottom: 2px solid #dee2e6;
                    font-size: 12px;
                    text-transform: uppercase;
                }}
                .filter-section {{
                    margin-bottom: 30px;
                }}
                .no-results {{
                    text-align: center;
                    color: #6c757d;
                    padding: 60px 20px;
                    font-size: 16px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>All Time Off</h1>
                <form class="search-box" method="GET" action="/leave/view_requests">
                    <input type="hidden" name="token" value="{kw.get('token', '')}">
                    <input type="hidden" name="approver_id" value="{approver.id}">
                    <input type="hidden" name="status" value="{status_filter}">
                    <input type="hidden" name="department" value="{department_filter}">
                    <input type="text" name="search" value="{search_term}" placeholder="Search...">
                    <button type="submit">🔍</button>
                </form>
            </div>
            
            <div class="main-content">
                <div class="sidebar">
                    <div class="filter-section">
                        {status_filters}
                    </div>
                    {department_filters}
                </div>
                
                <div class="content-area">
                    <div class="table-container">
                        {'<table>' if table_rows else ''}
                        {'<thead><tr><th>Employee</th><th>Time Off Type</th><th>Description</th><th>From Date</th><th>To Date</th><th>Created Date</th><th>Duration</th><th>Status</th></tr></thead>' if table_rows else ''}
                        {'<tbody>' + table_rows + '</tbody>' if table_rows else ''}
                        {'</table>' if table_rows else ''}
                        
                        {('<div class="no-results">No time off requests found matching your criteria.</div>') if not table_rows else ''}
                    </div>
                    {pagination_html}
                </div>
            </div>
        </body>
        </html>
        """
        return html_content
    
    def _render_error_page(self, error_message):
        """Render error page"""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Error</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    background: #f8f9fa;
                    margin: 0;
                    padding: 20px;
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
                .container {{
                    background: white;
                    border-radius: 12px;
                    padding: 40px;
                    text-align: center;
                    max-width: 400px;
                    border: 1px solid #dc3545;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                }}
                .error-icon {{
                    font-size: 60px;
                    color: #dc3545;
                    margin-bottom: 20px;
                }}
                h1 {{
                    color: #dc3545;
                    margin-bottom: 15px;
                    font-size: 24px;
                }}
                p {{
                    margin-bottom: 10px;
                    line-height: 1.6;
                }}
                .help-text {{
                    color: #6c757d;
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error-icon">❌</div>
                <h1>Error</h1>
                <p>{error_message}</p>
                <p class="help-text">Please contact your HR administrator for assistance.</p>
            </div>
        </body>
        </html>
        """
        return html_content
    
    def _render_requests_page(self, leaves, approver, status_filter, department_filter, 
                            search_term, departments, current_page, total_pages, total_count, kw):
        """Render page showing all requests with Odoo-style interface"""
        
        # Build table rows
        table_rows = ""
        for leave in leaves:
            status_display = {
                'draft': 'Draft',
                'confirm': 'To Approve',
                'validate1': 'Second Approval',
                'validate': 'Approved',
                'refuse': 'Refused'
            }.get(leave.state, leave.state.title())
            
            status_color = {
                'draft': '#6c757d',
                'confirm': '#ffc107',
                'validate1': '#17a2b8',
                'validate': '#28a745',
                'refuse': '#dc3545'
            }.get(leave.state, '#6c757d')
            
            description = leave.name if leave.name else '...'
            from_date = leave.request_date_from.strftime('%m/%d/%Y') if leave.request_date_from else ''
            to_date = leave.request_date_to.strftime('%m/%d/%Y') if leave.request_date_to else ''
            created_date = leave.create_date.strftime('%m/%d/%Y %H:%M:%S') if leave.create_date else ''
            duration = f"{leave.number_of_days} days" if leave.number_of_days else ""
            
            table_rows += f"""
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #e9ecef;">
                    <div style="display: flex; align-items: center;">
                        <div style="width: 20px; height: 20px; border-radius: 50%; background: #007bff; color: white; display: flex; align-items: center; justify-content: center; font-size: 10px; margin-right: 8px;">
                            {leave.employee_id.name[:2].upper()}
                        </div>
                        {leave.employee_id.name}
                    </div>
                </td>
                <td style="padding: 12px; border-bottom: 1px solid #e9ecef;">{leave.holiday_status_id.name}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e9ecef; color: #6c757d;">{description}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e9ecef;">{from_date}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e9ecef;">{to_date}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e9ecef;">{created_date}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e9ecef;">{duration}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e9ecef;">
                    <span style="background: {status_color}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 500;">
                        {status_display}
                    </span>
                </td>
            </tr>
            """
        
        # Build pagination
        pagination_html = ""
        if total_pages > 1:
            # Previous button
            prev_disabled = "disabled" if current_page <= 1 else ""
            prev_link = f"?token={kw.get('token', '')}&approver_id={approver.id}&status={status_filter}&department={department_filter}&search={search_term}&page={current_page-1}" if current_page > 1 else "#"
            
            # Next button  
            next_disabled = "disabled" if current_page >= total_pages else ""
            next_link = f"?token={kw.get('token', '')}&approver_id={approver.id}&status={status_filter}&department={department_filter}&search={search_term}&page={current_page+1}" if current_page < total_pages else "#"
            
            pagination_html = f"""
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 15px 20px; border-top: 1px solid #e9ecef; background: #f8f9fa;">
                <span style="color: #6c757d; font-size: 14px;">
                    {((current_page-1) * 10) + 1}-{min(current_page * 10, total_count)} / {total_count}
                </span>
                <div style="display: flex; gap: 5px;">
                    <a href="{prev_link}" style="padding: 6px 12px; background: {'#e9ecef' if prev_disabled else '#007bff'}; color: {'#6c757d' if prev_disabled else 'white'}; text-decoration: none; border-radius: 4px; font-size: 14px; {'pointer-events: none;' if prev_disabled else ''}">‹</a>
                    <a href="{next_link}" style="padding: 6px 12px; background: {'#e9ecef' if next_disabled else '#007bff'}; color: {'#6c757d' if next_disabled else 'white'}; text-decoration: none; border-radius: 4px; font-size: 14px; {'pointer-events: none;' if next_disabled else ''}">›</a>
                </div>
            </div>
            """
        
        # Build status filters
        status_filters = f"""
        <div style="margin-bottom: 20px;">
            <h6 style="margin: 0 0 10px 0; color: #495057; font-size: 12px; text-transform: uppercase; font-weight: 600;">STATUS</h6>
            <div style="display: flex; flex-direction: column; gap: 5px;">
                <a href="?token={kw.get('token', '')}&approver_id={approver.id}&status=all&department={department_filter}&search={search_term}" 
                   style="padding: 8px 12px; color: {'#007bff' if status_filter == 'all' else '#6c757d'}; text-decoration: none; border-radius: 4px; background: {'#e3f2fd' if status_filter == 'all' else 'transparent'}; font-size: 14px;">
                   All
                </a>
                <a href="?token={kw.get('token', '')}&approver_id={approver.id}&status=to_approve&department={department_filter}&search={search_term}" 
                   style="padding: 8px 12px; color: {'#007bff' if status_filter == 'to_approve' else '#6c757d'}; text-decoration: none; border-radius: 4px; background: {'#e3f2fd' if status_filter == 'to_approve' else 'transparent'}; font-size: 14px;">
                   To Approve
                </a>
                <a href="?token={kw.get('token', '')}&approver_id={approver.id}&status=second_approval&department={department_filter}&search={search_term}" 
                   style="padding: 8px 12px; color: {'#007bff' if status_filter == 'second_approval' else '#6c757d'}; text-decoration: none; border-radius: 4px; background: {'#e3f2fd' if status_filter == 'second_approval' else 'transparent'}; font-size: 14px;">
                   Second Approval
                </a>
                <a href="?token={kw.get('token', '')}&approver_id={approver.id}&status=approved&department={department_filter}&search={search_term}" 
                   style="padding: 8px 12px; color: {'#007bff' if status_filter == 'approved' else '#6c757d'}; text-decoration: none; border-radius: 4px; background: {'#e3f2fd' if status_filter == 'approved' else 'transparent'}; font-size: 14px;">
                   Approved
                </a>
            </div>
        </div>
        """
        
        # Build department filters
        department_filters = ""
        if departments:
            dept_links = f"""
            <a href="?token={kw.get('token', '')}&approver_id={approver.id}&status={status_filter}&department=all&search={search_term}" 
               style="padding: 8px 12px; color: {'#007bff' if department_filter == 'all' else '#6c757d'}; text-decoration: none; border-radius: 4px; background: {'#e3f2fd' if department_filter == 'all' else 'transparent'}; font-size: 14px; display: block;">
               All
            </a>
            """
            for dept in sorted(departments):
                dept_links += f"""
                <a href="?token={kw.get('token', '')}&approver_id={approver.id}&status={status_filter}&department={dept}&search={search_term}" 
                   style="padding: 8px 12px; color: {'#007bff' if department_filter == dept else '#6c757d'}; text-decoration: none; border-radius: 4px; background: {'#e3f2fd' if department_filter == dept else 'transparent'}; font-size: 14px; display: block;">
                   {dept}
                </a>
                """
            
            department_filters = f"""
            <div>
                <h6 style="margin: 0 0 10px 0; color: #495057; font-size: 12px; text-transform: uppercase; font-weight: 600;">DEPARTMENT</h6>
                <div style="display: flex; flex-direction: column; gap: 5px;">
                    {dept_links}
                </div>
            </div>
            """
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>All Time Off</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
                    background: #f8f9fa;
                    color: #495057;
                    font-size: 14px;
                }}
                .header {{
                    background: white;
                    border-bottom: 1px solid #dee2e6;
                    padding: 15px 20px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }}
                .header h1 {{
                    font-size: 18px;
                    font-weight: 600;
                    color: #495057;
                }}
                .search-box {{
                    position: relative;
                }}
                .search-box input {{
                    padding: 8px 12px;
                    border: 1px solid #ced4da;
                    border-radius: 4px;
                    font-size: 14px;
                    width: 300px;
                }}
                .search-box button {{
                    position: absolute;
                    right: 5px;
                    top: 50%;
                    transform: translateY(-50%);
                    background: none;
                    border: none;
                    cursor: pointer;
                    padding: 5px;
                }}
                .main-content {{
                    display: flex;
                    min-height: calc(100vh - 60px);
                }}
                .sidebar {{
                    width: 200px;
                    background: white;
                    border-right: 1px solid #dee2e6;
                    padding: 20px;
                }}
                .content-area {{
                    flex: 1;
                    background: white;
                    margin: 0;
                }}
                .table-container {{
                    overflow-x: auto;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    background: white;
                }}
                th {{
                    background: #f8f9fa;
                    padding: 12px;
                    text-align: left;
                    font-weight: 600;
                    color: #495057;
                    border-bottom: 2px solid #dee2e6;
                    font-size: 12px;
                    text-transform: uppercase;
                }}
                .filter-section {{
                    margin-bottom: 30px;
                }}
                .no-results {{
                    text-align: center;
                    color: #6c757d;
                    padding: 60px 20px;
                    font-size: 16px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>All Time Off</h1>
                <form class="search-box" method="GET" action="/leave/view_requests">
                    <input type="hidden" name="token" value="{kw.get('token', '')}">
                    <input type="hidden" name="approver_id" value="{approver.id}">
                    <input type="hidden" name="status" value="{status_filter}">
                    <input type="hidden" name="department" value="{department_filter}">
                    <input type="text" name="search" value="{search_term}" placeholder="Search...">
                    <button type="submit">🔍</button>
                </form>
            </div>
            
            <div class="main-content">
                <div class="sidebar">
                    <div class="filter-section">
                        {status_filters}
                    </div>
                    {department_filters}
                </div>
                
                <div class="content-area">
                    <div class="table-container">
                        {'<table>' if table_rows else ''}
                        {'<thead><tr><th>Employee</th><th>Time Off Type</th><th>Description</th><th>From Date</th><th>To Date</th><th>Created Date</th><th>Duration</th><th>Status</th></tr></thead>' if table_rows else ''}
                        {'<tbody>' + table_rows + '</tbody>' if table_rows else ''}
                        {'</table>' if table_rows else ''}
                        
                        {('<div class="no-results">No time off requests found matching your criteria.</div>') if not table_rows else ''}
                    </div>
                    {pagination_html}
                </div>
            </div>
        </body>
        </html>
        """
        return html_content
    
    def _render_error_page(self, error_message):
        """Render error page"""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Error</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    background: #f8f9fa;
                    margin: 0;
                    padding: 20px;
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
                .container {{
                    background: white;
                    border-radius: 12px;
                    padding: 40px;
                    text-align: center;
                    max-width: 400px;
                    border: 1px solid #dc3545;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                }}
                .error-icon {{
                    font-size: 60px;
                    color: #dc3545;
                    margin-bottom: 20px;
                }}
                h1 {{
                    color: #dc3545;
                    margin-bottom: 15px;
                    font-size: 24px;
                }}
                p {{
                    margin-bottom: 10px;
                    line-height: 1.6;
                }}
                .help-text {{
                    color: #6c757d;
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error-icon">❌</div>
                <h1>Error</h1>
                <p>{error_message}</p>
                <p class="help-text">Please contact your HR administrator for assistance.</p>
            </div>
        </body>
        </html>
        """
        return html_content