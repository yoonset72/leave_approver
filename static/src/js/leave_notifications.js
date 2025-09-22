odoo.define('enhanced_leave_approval.notifications', function (require) {
    'use strict';

    var core = require('web.core');
    var session = require('web.session');
    var WebClient = require('web.WebClient');

    // Enhanced notification system for leave approvals
    WebClient.include({
        show_leave_notification: function(message, type, title) {
            type = type || 'success';
            title = title || 'Leave Approval';
            
            // Create notification with custom styling
            this.do_notify(title, message, false);
            
            // Add custom popup for better visibility
            var $notification = $('<div class="leave-approval-popup">')
                .html('<strong>' + title + '</strong><br>' + message)
                .css({
                    'position': 'fixed',
                    'top': '20px',
                    'right': '20px',
                    'background': type === 'success' ? '#28a745' : '#dc3545',
                    'color': 'white',
                    'padding': '15px 20px',
                    'border-radius': '8px',
                    'box-shadow': '0 4px 12px rgba(0,0,0,0.3)',
                    'z-index': '9999',
                    'max-width': '300px',
                    'animation': 'slideInRight 0.5s ease-out'
                });
            
            $('body').append($notification);
            
            // Auto remove after 5 seconds
            setTimeout(function() {
                $notification.fadeOut(500, function() {
                    $(this).remove();
                });
            }, 5000);
        }
    });

    // CSS for animations
    $('<style>')
        .prop('type', 'text/css')
        .html(`
            @keyframes slideInRight {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            .leave-approval-popup {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
        `)
        .appendTo('head');

    return {
        show_leave_notification: function(message, type, title) {
            if (session.webclient) {
                session.webclient.show_leave_notification(message, type, title);
            }
        }
    };
});