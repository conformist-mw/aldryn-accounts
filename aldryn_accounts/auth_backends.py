# -*- coding: utf-8 -*-
import django
from django.contrib.auth.backends import ModelBackend

from .compatibility import is_anonymous
from .models import EmailAddress
from .utils import get_most_qualified_user_for_email_and_password


class EmailBackend(ModelBackend):
    if django.VERSION < (1, 11):
        def authenticate(self, username=None, password=None, **kwargs):
            """
            tries verified email addresses, the email field on user objects and unconfirmed email addresses.
            username is not checked, since the default model backend already does that.
            """
            username = username.strip()
            return get_most_qualified_user_for_email_and_password(username, password)
    else:
        def authenticate(self, request, username=None, password=None, **kwargs):
            """
            tries verified email addresses, the email field on user objects and unconfirmed email addresses.
            username is not checked, since the default model backend already does that.
            """
            username = username.strip()
            return get_most_qualified_user_for_email_and_password(username, password)


class PermissionBackend(object):
    def authenticate(self):
        return None

    def has_perm(self, user_obj, perm, obj=None):
        # TODO: cache
        if perm == 'aldryn_accounts.has_verified_email':
            if not user_obj or is_anonymous(user_obj):
                return False
            return EmailAddress.objects.has_verified_email(user_obj)
        return False
