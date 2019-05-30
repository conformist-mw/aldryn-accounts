# -*- coding: utf-8 -*-
import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.core.files.base import ContentFile
try:
    from django.urls import reverse
except ImportError:
    # Django <= 1.10
    from django.core.urlresolvers import reverse
from django.shortcuts import redirect
from social_core.exceptions import AuthException

from .models import EmailAddress
from .signals import user_signed_up
from .utils import generate_username


def _has_verified_email(user):
    return EmailAddress.objects.filter(user=user).exists()


def _get_verified_email(email, user=None):
    kwargs = {'email': email}

    if user:
        kwargs['user'] = user

    try:
        return EmailAddress.objects.get(**kwargs).email
    except EmailAddress.DoesNotExist:
        pass


def _is_trusted_email_backend(backend):
    return (
            backend.name in
            settings.ALDRYN_ACCOUNTS_SOCIAL_BACKENDS_WITH_TRUSTED_EMAIL
    )


def get_username(*args, **kwargs):
    """Always use the UUID4 username"""
    return {'username': generate_username()}


def require_email(strategy, backend, details, response, user=None, *args, **kwargs):
    """
    Workaround for getting the email from facebook
    https://github.com/omab/python-social-auth/issues/675
    """

    if backend.name != 'facebook':
        return

    if user and user.email:
        return

    if strategy.request_data().get('email'):
        details['email'] = strategy.request_data().get('email')
        return

    if strategy.request.session.get('email', '') != '':
        details['email'] = strategy.request.session['email']
        return

    fbuid = response.get('id')
    token = response.get('access_token')
    url = (
        'https://graph.facebook.com/{}/?fields=email&access_token={}'
        .format(fbuid, token)
    )
    response = requests.get(url)
    email = response.json().get('email')
    if email:
        details['email'] = email


def create_user(username, details, backend, user=None, *args, **kwargs):
    if user:
        return

    email = details.get('email')
    verified_email = _get_verified_email(email=email)
    is_trusted_email_backend = _is_trusted_email_backend(backend)

    connect_accounts = (
            settings.ALDRYN_ACCOUNTS_SOCIAL_BACKENDS_WITH_TRUSTED_EMAIL and
            is_trusted_email_backend and
            verified_email
    )

    if connect_accounts:
        user = verified_email.user
    else:
        user = User.objects.create_user(username=username, email='')

    if email and _is_trusted_email_backend(backend):
        email_address = EmailAddress.objects.add_email(user=user, email=email)
        verified_email = email_address.email
    else:
        user.is_active = False
        user.save()

    user_signed_up.send(user=user, sender=backend)

    return {
        'user': user,
        'is_new': True,
        'verified_email': verified_email
    }


def set_profile_image(backend, user, response, is_new, *args, **kwargs):
    if is_new or not user.settings.profile_image:

        image_url = None
        if backend.name == 'facebook':
            image_url = (
                'http://graph.facebook.com/{0}/picture?type=large'
                .format(response['id'])
            )

        elif backend.name == 'twitter':
            image_url = response.get('profile_image_url')

        elif backend.name == 'google-oauth2':
            image = response.get('image')
            if image:
                image_url = image.get('url')
                if image_url:
                    image_url += '&sz=100'

        if image_url:
            try:
                image_response = requests.get(image_url)
                image_response.raise_for_status()
            except requests.HTTPError:
                return

            user_settings = user.settings
            user_settings.profile_image.save(
                '{}_{}_profile_image.jpg'.format(user.username, backend.name),
                ContentFile(image_response.content)
            )
            user_settings.save()


def link_to_existing_user_by_email_if_backend_is_trusted(backend, details, user=None, *args, **kwargs):
    """Return user entry with same email address as one returned on details."""
    if user or not _is_trusted_email_backend(backend):
        return

    email = details.get('email')

    if email:
        # try to link accounts registered with the same email address,
        # only if it's a single object. AuthException is raised if multiple
        # objects are returned
        try:
            return {'user': EmailAddress.objects.get(email=email).user}
        except MultipleObjectsReturned:
            raise AuthException(kwargs['backend'], 'Not unique email address.')
        except ObjectDoesNotExist:
            pass


def redirect_to_email_form(strategy, details, user=None, *args, **kwargs):
    if not user or _has_verified_email(user=user):
        return

    # we don't have a verified email yet
    return redirect(reverse('aldryn_accounts:accounts_email_list'))
