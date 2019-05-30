# -*- coding: utf-8 -*-


import emailit.api
from django.contrib.sites.models import Site
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMultiAlternatives
try:
    from django.urls import reverse
except ImportError:
    # Django <= 1.10
    from django.core.urlresolvers import reverse
from django.template import loader
from django.utils import timezone
from django.utils.encoding import force_text
from django.utils.http import urlencode
from django.utils.module_loading import import_string
from django.utils.translation import get_language, override

from .conf import settings
from .utils import user_display


class DefaultEmailSender(object):
    @classmethod
    def get_protocol(cls):
        return getattr(settings, 'DEFAULT_HTTP_PROTOCOL', 'http')

    @classmethod
    def get_absolute_url(cls, path='', site=None):
        if not site:
            site = Site.objects.get_current()

        return '{}://{}{}'.format(
            cls.get_protocol(),
            force_text(site.domain),
            path,
        )

    @classmethod
    def send_email_verification(cls, **kwargs):
        verification = kwargs.get('verification')
        site = kwargs.get('site', None) or Site.objects.get_current()
        language = verification.user.settings.preferred_language or get_language()

        with override(language):
            activate_url = cls.get_absolute_url(
                path=reverse('aldryn_accounts:accounts_confirm_email', args=[verification.key]),
                site=site,
            )

            context = dict(
                email=verification.email,
                user=verification.user,
                name=user_display(verification.user),
                activate_url=activate_url,
                site=site,
                site_name=site.name,
                site_domain=site.domain,
                key=verification.key,
            )

            emailit.api.send_mail(
                (verification.email,),
                context,
                'aldryn_accounts/email/email_confirmation',
            )

        verification.sent_at = timezone.now()
        verification.save(update_fields=('sent_at',))

    @classmethod
    def send_signup_code(cls, **kwargs):
        signup_code = kwargs.get('signup_code')

        language = signup_code.invited_by.settings.preferred_language or get_language()
        site = kwargs.get('site', None) or get_current_site(kwargs.get('request'))

        with override(language):
            path = '{}?{}'.format(
                reverse('aldryn_accounts:accounts_signup'),
                urlencode({'code': signup_code.code}),
            )

            signup_url = cls.get_absolute_url(
                path=path,
                site=site,
            )

            context = dict(
                signup_code=signup_code,
                current_site=site,
                signup_url=signup_url,
            )

            emailit.api.send_mail(
                (signup_code.email,),
                context,
                'aldryn_accounts/email/invite_user',
            )

            signup_code.sent_at = timezone.now()
        signup_code.save(update_fields=('sent_at',))

    @classmethod
    def send_password_recovery_reset(cls, **kwargs):
        context = kwargs['context']
        # originally from django.contrib.auth.forms.PasswordResetForm#send_mail
        subject = loader.render_to_string(kwargs['subject_template_name'], context)
        # Email subject *must not* contain newlines
        subject = ''.join(subject.splitlines())
        body = loader.render_to_string(kwargs['email_template_name'], context)

        email_message = EmailMultiAlternatives(
            subject,
            body,
            kwargs['from_email'],
            [kwargs['to_email']],
        )
        html_email_template_name = kwargs.get('html_email_template_name')
        if html_email_template_name:
            html_email = loader.render_to_string(html_email_template_name, context)
            email_message.attach_alternative(html_email, 'text/html')

        email_message.send()

    @classmethod
    def send_password_changed(cls, **kwargs):
        user = kwargs.get('user')
        language = user.settings.preferred_language or get_language()
        site = get_current_site(kwargs.get('request'))

        with override(language):
            site_url = cls.get_absolute_url(site=site)

            context = dict(
                name=user_display(user),
                site_name=site.name,
                site_url=site_url,
                support_email=settings.ALDRYN_ACCOUNTS_SUPPORT_EMAIL,
            )

            emailit.api.send_mail(
                (user.email,),
                context,
                kwargs.get('template'),
            )


def get_email_sender_class():
    path = getattr(settings, 'ALDRYN_ACCOUNTS_EMAIL_SENDER', None)
    if path:
        return import_string(path)
    return DefaultEmailSender


EmailSender = get_email_sender_class()
