# -*- coding: utf-8 -*-
from django.conf import settings
try:
    from django.urls import NoReverseMatch
except ImportError:
    # Django <= 1.10
    from django.core.urlresolvers import NoReverseMatch
from django.template.loader import render_to_string

from .compatibility import is_anonymous

DISPLAY_EMAIL_NOTIFICATION = getattr(
    settings, 'ALDRYN_ACCOUNTS_DISPLAY_EMAIL_NOTIFICATION', False)
DISPLAY_PASSWORD_NOTIFICATION = getattr(
    settings, 'ALDRYN_ACCOUNTS_DISPLAY_PASSWORD_NOTIFICATION', False)


class Notification(object):
    def __init__(self, body, level=0):
        self.body = body
        self.level = level


def check_notifications(user):
    # TODO: caching/optimisation
    notifications = []
    if is_anonymous(user):
        return []
    if DISPLAY_EMAIL_NOTIFICATION:
        email_notification = check_email_verification(user)
        if email_notification:
            notifications.append(email_notification)
    if DISPLAY_PASSWORD_NOTIFICATION:
        password_notification = check_password(user)
        if password_notification:
            notifications.append(password_notification)
    return notifications


def check_password(user):
    if not user.has_usable_password():
        try:
            body = render_to_string('aldryn_accounts/notifications/no_password.html', {'user': user})
            return Notification(body)
        except NoReverseMatch:
            # the aldryn accounts profile urls are not setup correctly yet
            # (e.g the apphook was not added yet)
            pass
    return None


def check_email_verification(user):
    unverified_emails = user.email_verifications.all()
    unverified_emails_count = len(unverified_emails)
    if unverified_emails_count:
        context = {
            'unverified_emails': unverified_emails,
            'unverified_emails_count': unverified_emails_count,
            'user': user,
        }
        body = render_to_string('aldryn_accounts/notifications/email_verification_in_progress.html', context)
        return Notification(body)
    if not user.has_perm('aldryn_accounts.has_verified_email'):
        body = render_to_string('aldryn_accounts/notifications/no_verified_emails.html', {'user': user})
        return Notification(body)
    return None
