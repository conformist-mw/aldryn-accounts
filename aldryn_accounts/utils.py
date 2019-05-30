# -*- coding: utf-8 -*-
import hashlib
import importlib
import logging
import os
import uuid

import pygeoip
from django.conf import settings
from django.contrib.auth.models import User
from django.utils.crypto import random

from .compatibility import is_anonymous

logger = logging.getLogger('aldryn_accounts')


def user_display(user, fallback_to_username=settings.ALDRYN_ACCOUNTS_USER_DISPLAY_FALLBACK_TO_USERNAME, fallback_to_pk=settings.ALDRYN_ACCOUNTS_USER_DISPLAY_FALLBACK_TO_PK):
    if is_anonymous(user):
        return 'Anonymous user'
    if user.email:
        return user.email
    elif user.first_name or user.last_name:
        return ("%s %s" % (user.first_name, user.last_name)).strip()
    elif fallback_to_username and user.username:
        return user.username
    elif fallback_to_pk and user.pk:
        return str(user.pk)
    return ''


def random_token(extra=None, hash_func=hashlib.sha256):
    if extra is None:
        extra = []
    bits = extra + [str(random.getrandbits(512))]
    return hash_func("".join(bits).encode('utf-8')).hexdigest()


def profile_image_upload_to(instance, filename):
    name, extension = os.path.splitext(filename)
    profile_data_prefix = settings.ALDRYN_ACCOUNTS_PROFILE_IMAGE_UPLOAD_TO
    return os.path.join(profile_data_prefix, '%s%s' % (uuid.uuid4(), extension) )


# TODO: make cache method configurable
if settings.ALDRYN_ACCOUNTS_USE_GEOIP:
    GEOIP_PATH = getattr(settings, 'GEOIP_PATH', '')
    GEOIP_CITY = getattr(settings, 'GEOIP_CITY', 'GeoLiteCity.dat')
    gi4 = pygeoip.GeoIP(os.path.join(GEOIP_PATH, GEOIP_CITY))


def geoip(ip):
    # TODO: validate ip
    # do nothing if geo ip is not enabled.
    if not settings.ALDRYN_ACCOUNTS_USE_GEOIP:
        return dict()
    try:
        data = gi4.record_by_addr(ip)
    except Exception:
        data = None
        # we use a catch all because there's a few exceptions that could occur here.
        logger.exception("Could not fetch geo data for ip %s" % (ip, ))
    if not data:  # empty dict
        return dict()
    if data.get('city') and data.get('country'):
        data['pretty_name'] = "%s, %s" % (data.get('city'), data.get('country_name'))
    elif data.get('country'):
        data['pretty_name'] = "%s" % data.get('country_name')
    return data


def get_most_qualified_user_for_email_and_password(email, password):
    from aldryn_accounts.models import EmailAddress, EmailConfirmation
    # try verified email addresses
    for user_email in EmailAddress.objects.filter(email__iexact=email):
        # (EmailAddress.email is unique, but using the forloop vs a .get removes the need for a try/except.
        if user_email.user.check_password(password):
            return user_email.user
        # try the email field on the user
    for user in User.objects.filter(email__iexact=email):
        if user.check_password(password):
            return user
        # try unconfirmed email addresses
    for email_confirmation in EmailConfirmation.objects.filter(email__iexact=email):
        if email_confirmation.user.check_password(password):
            return email_confirmation.user
    return None


def get_most_qualified_user_for_email(email):
    from aldryn_accounts.models import EmailAddress, EmailConfirmation
    # try verified email addresses
    for user_email in EmailAddress.objects.filter(email__iexact=email):
        # (EmailAddress.email is unique, but using the forloop vs a .get removes the need for a try/except.
        return user_email.user
    for user in User.objects.filter(email__iexact=email):
        return user
    for email_confirmation in EmailConfirmation.objects.filter(email__iexact=email):
        return email_confirmation.user
    return None


def generate_username():
    uuid_obj = uuid.uuid4()
    if hasattr(uuid_obj, 'get_hex'):  # Python 2
        uuid_str = uuid_obj.get_hex()
    else:
        uuid_str = uuid_obj.hex
    return uuid_str[:30]  # django User.username.max_length


def import_from_path(path_to_class):
    path, cls = path_to_class.rsplit('.', 1)
    module = importlib.import_module(path)
    return getattr(module, cls)


def get_signup_view():
    return import_from_path(settings.ALDRYN_ACCOUNTS_SIGNUP_VIEW)


def get_login_view():
    return import_from_path(settings.ALDRYN_ACCOUNTS_LOGIN_VIEW)
