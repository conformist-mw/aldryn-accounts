# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import datetime
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth import  SESSION_KEY

from django.core import mail
from django.test import  override_settings
from django.core.urlresolvers import reverse
from django.utils import unittest
from django.utils.translation import override

from aldryn_accounts.models import SignupCode, EmailConfirmation, EmailAddress
from .base import AllAccountsApphooksTestCase


class GetViewUrlMixin(object):
    view_name = ''

    def get_view_url(self, view_name=None, **kwargs):
        if view_name is None:
            view_name = self.view_name
        with override('en'):
            view_url = reverse(view_name, kwargs=kwargs)
        return view_url


# session engine is hardcoded in djangocms-helper (atm v0.9.4), so override
# per test case
@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cached_db')
class SignupViewTestCase(GetViewUrlMixin, AllAccountsApphooksTestCase):
    view_name = "accounts_signup"

    @override_settings(ALDRYN_ACCOUNTS_OPEN_SIGNUP=True)
    def test_get_not_logged_in_no_code(self):
        view_url = self.get_view_url()
        response = self.client.get(view_url)
        self.assertContains(response, 'New? Register now')

    @override_settings(ALDRYN_ACCOUNTS_OPEN_SIGNUP=False)
    def test_get_not_logged_in_no_code(self):
        view_url = self.get_view_url()
        response = self.client.get(view_url)
        self.assertContains(response, 'Signup is currently closed')

    @override_settings(ALDRYN_ACCOUNTS_OPEN_SIGNUP=False)
    def test_get_not_logged_with_not_valid_code(self):
        data = {
            'code': 'not valid code',
        }
        view_url = self.get_view_url()
        response = self.client.get(view_url, data=data)
        self.assertContains(response, 'Signup is currently closed')

    @override_settings(ALDRYN_ACCOUNTS_OPEN_SIGNUP=False)
    def test_get_not_logged_with_valid_code(self):
        random_code = self.rand_str()
        new_code = SignupCode.create(code=random_code)
        new_code.save()
        data = {
            'code': new_code.code,
        }
        view_url = self.get_view_url()
        response = self.client.get(view_url, data=data)
        self.assertContains(response, 'New? Register now')

    @override_settings(ALDRYN_ACCOUNTS_OPEN_SIGNUP=False)
    def test_post_with_not_valid_code(self):
        data = {
            'code': 'not valid code',
            'email': 'test@example.com',
        }
        view_url = self.get_view_url()
        response = self.client.post(view_url, data=data)
        self.assertContains(response, 'Signup is currently closed')

    @override_settings(ALDRYN_ACCOUNTS_OPEN_SIGNUP=False)
    def test_get_with_valid_code(self):
        # ensure there is no users
        self.assertEqual(User.objects.count(), 0)

        random_code = self.rand_str()
        new_code = SignupCode.create(code=random_code)
        new_code.save()
        data = {
            'code': new_code.code,
            'email': 'test@example.com',
        }
        view_url = self.get_view_url()
        response = self.client.post(view_url, data=data)
        self.assertEqual(User.objects.count(), 1)

    @override_settings(ALDRYN_ACCOUNTS_OPEN_SIGNUP=False)
    def test_get_with_logged_in_user(self):
        user = self.get_standard_user()
        view_url = self.get_view_url()
        self.client.login(username='standard', password='standard')
        response = self.client.get(view_url, follow=True)
        self.assertEqual(response.status_code, 302)


class SignupEmailResendConfirmationViewTestCase(GetViewUrlMixin,
                                                AllAccountsApphooksTestCase):
    view_name = "accounts_signup_email_resend_confirmation"

    def test_get(self):
        view_url = self.get_view_url()
        response = self.client.get(view_url)
        # test that there is the text from template
        self.assertContains(response, 'Send again the confirmation email')
        # and submit button
        self.assertContains(
            response, 'Yes, send me the confirmation email again')

    def test_post_with_invalid_email(self):
        data = {
            'email': 'wrong@example.com',
        }
        mail.outbox = []
        view_url = self.get_view_url()
        response = self.client.post(view_url, data=data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_post_with_valid_email(self):
        user = self.get_standard_user()
        test_email = 'test@example.com'
        new_confirmation = EmailConfirmation.objects.request(
            user=user,
            email=test_email,
        )
        mail.outbox = []
        data = {
            'email': new_confirmation.email,
        }
        view_url = self.get_view_url()
        response = self.client.post(view_url, data=data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(response.status_code, 302)


class SignupEmailConfirmationSentViewTestCase(GetViewUrlMixin,
                                              AllAccountsApphooksTestCase):
    view_name = 'accounts_signup_email_confirmation_sent'

    def test_get_no_email(self):
        view_url = self.get_view_url()
        response = self.client.get(view_url)
        self.assertContains(response, 'We have sent you an email to')

    def test_getwith_email(self):
        test_email = 'test@examole.com'
        data = {
            'email': test_email,
        }
        lookup_string = 'We have sent you an email to <b>{0}</b>'
        view_url = self.get_view_url()
        response = self.client.get(view_url, data=data)
        self.assertContains(response, lookup_string.format(test_email))


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cached_db')
class LoginLogoutViewsTestCase(AllAccountsApphooksTestCase):

    def login(self, username='standard', password='standard'):
        with override('en'):
            login_url = reverse('login')
        response = self.client.post(login_url, {
            'username': username,
            'password': password,
        })
        self.assertIn(SESSION_KEY, self.client.session)
        return response

    def test_login_view_get(self):
        with override('en'):
            login_url = reverse('login')
        response = self.client.get(login_url)
        self.assertEqual(response.status_code, 200)

    def test_login_view_logins(self):
        self.get_standard_user()
        self.login()

    def test_logout_get_not_logged_in_user(self):
        self.get_standard_user()
        with override('en'):
            logout_url = reverse('logout')
        response = self.client.get(logout_url)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_logout_get_logged_in_user(self):
        self.get_standard_user()
        self.login()
        # test logout
        with override('en'):
            logout_url = reverse('logout')
        response = self.client.get(logout_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(SESSION_KEY, self.client.session)

    def test_logout_post(self):
        self.get_standard_user()
        self.login()
        # test logout
        with override('en'):
            logout_url = reverse('logout')
        response = self.client.post(logout_url)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(SESSION_KEY, self.client.session)


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cached_db')
class PasswordResetViewsTestCase(GetViewUrlMixin, AllAccountsApphooksTestCase):
    view_name = 'accounts_password_reset_recover'

    def test_get(self):
        view_url = self.get_view_url()
        response = self.client.get(view_url)
        self.assertContains(response, 'Recover my password')

    def test_post_with_not_valid_username(self):
        view_url = self.get_view_url()
        data = {
            'username_or_email': 'not_existing'
        }
        mail.outbox = []
        response = self.client.post(view_url, data=data)
        # check that no email were sent
        self.assertEqual(len(mail.outbox), 0)
        # check that there is a validation error message
        self.assertContains(response, "Sorry, this user doesn't exist.")

    def test_post_with_valid_username(self):
        user = self.get_standard_user()
        view_url = self.get_view_url()
        data = {
            'username_or_email': user.username,
        }
        mail.outbox = []
        response = self.client.post(view_url, data=data, follow=True)
        # check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        # ensure there was a redirect
        self.assertEqual(response.status_code, 302)
        # TODO: add check for content of redirected PasswordResetRecoverSentView

    def test_post_with_valid_email(self):
        user = self.get_standard_user()
        view_url = self.get_view_url()
        data = {
            'username_or_email': user.email,
        }
        mail.outbox = []
        response = self.client.post(view_url, data=data, follow=True)
        # check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        # ensure there was a redirect
        self.assertEqual(response.status_code, 302)
        # TODO: add check for content of redirected PasswordResetRecoverSentView


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cached_db')
class ConfirmEmailViewTestCase(GetViewUrlMixin, AllAccountsApphooksTestCase):
    view_name = 'accounts_confirm_email'

    def setUp(self):
        super(ConfirmEmailViewTestCase, self).setUp()
        # create user but don't make him active
        self.user = self.get_standard_user()
        self.user.is_active = False
        self.user.save()
        self.confirmation_object = EmailConfirmation.objects.request(
            user=self.user, email='test@example.com', send=True)
        # reset the outbox
        mail.outbox = []

    def test_get_not_existing_key(self):
        view_url = self.get_view_url(key='notExistingKey')
        response = self.client.get(view_url)
        self.assertEqual(response.status_code, 404)

    def test_get_valid_key(self):
        view_url = self.get_view_url(key=self.confirmation_object.key)
        response = self.client.get(view_url)
        self.assertContains(response, 'confirm and login')

    def test_post_with_not_valid_key(self):
        view_url = self.get_view_url(key='notExistingKey')
        response = self.client.post(view_url)
        self.assertEqual(response.status_code, 404)
        # check that login and user are not affected
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.user = User.objects.get(pk=self.user.pk)
        self.assertFalse(self.user.is_active)

    def test_post_with_valid_key(self):
        view_url = self.get_view_url(key=self.confirmation_object.key)
        # ensure user was not logged in
        self.assertNotIn(SESSION_KEY, self.client.session)
        response = self.client.post(view_url, follow=True)
        # TODO: test messages
        self.assertEqual(response.status_code, 302)
        # ensure user has been logged in after success
        self.assertIn(SESSION_KEY, self.client.session)
        # refresh user from db
        self.user = User.objects.get(pk=self.user.pk)
        self.assertTrue(self.user.is_active)

    def test_post_with_verified_email(self):
        view_url = self.get_view_url(key=self.confirmation_object.key)
        # ensure user was not logged in
        self.assertNotIn(SESSION_KEY, self.client.session)
        # confirm email
        self.confirmation_object.confirm()
        mail.outbox = []
        response = self.client.post(view_url, follow=True)
        # TODO: test messages
        self.assertContains(
            response, 'This email has already been verified')
        # ensure user was not logged in and not affected
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.user = User.objects.get(pk=self.user.pk)
        self.assertFalse(self.user.is_active)

    def test_post_with_expired_key(self):
        view_url = self.get_view_url(key=self.confirmation_object.key)
        # ensure user was not logged in
        self.assertNotIn(SESSION_KEY, self.client.session)
        # expire the key
        expire_days = getattr(
            settings,
            'ALDRYN_ACCOUNTS_EMAIL_CONFIRMATION_EXPIRE_DAYS', 5)
        expire_days_delta = datetime.timedelta(days=expire_days + 1)
        self.confirmation_object.sent_at -= expire_days_delta
        self.confirmation_object.save()
        mail.outbox = []
        response = self.client.post(view_url, follow=True)
        # TODO: test messages
        self.assertContains(
            response, 'The activation key has expired')
        # ensure user was not logged in and not affected
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.user = User.objects.get(pk=self.user.pk)
        self.assertFalse(self.user.is_active)


class CreateChangePasswordCommonTestCasesMixin(object):

    def setUp(self):
        super(CreateChangePasswordCommonTestCasesMixin, self).setUp()
        self.user = self.get_standard_user()

    def test_get_not_authenticated(self):
        view_url = self.get_view_url()
        response = self.client.get(view_url)
        self.assertEqual(response.status_code, 302)

    def _view_get_with_valid_user_no_assert(self):
        view_url = self.get_view_url()
        self.client.login(username=self.user.username, password='standard')
        response = self.client.get(view_url)
        return response

    def _view_get_with_not_usable_user_password(self):
        view_url = self.get_view_url()
        self.client.login(username=self.user.username, password='standard')
        self.user.set_unusable_password()
        self.user.save()
        # todo: test with follow=true
        response = self.client.get(view_url)
        return response

    def test_post_with_not_authenticated_user(self):
        view_url = self.get_view_url()
        response = self.client.post(view_url)
        self.assertEqual(response.status_code, 403)

    def _test_post_with_valid_data(self):
        view_url = self.get_view_url()
        self.client.login(username=self.user.username, password='standard')
        # todo: test with follow=true and check messages
        response = self.client.post(view_url, data=self.valid_data)
        self.assertEqual(response.status_code, 302)
        self.client.logout()
        # check that we can login with new password
        login_result = self.client.login(
            username=self.user.username, password=self.new_password)
        self.assertTrue(login_result)

    def test_post_with_valid_data_no_extra_settings(self):
        self._test_post_with_valid_data()

    @override_settings(ALDRYN_ACCOUNTS_NOTIFY_PASSWORD_CHANGE=False)
    def test_post_with_valid_data_dont_send_email(self):
        mail.outbox = []
        self._test_post_with_valid_data()
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(ALDRYN_ACCOUNTS_NOTIFY_PASSWORD_CHANGE=True)
    def test_post_with_valid_data_and_send_email(self):
        mail.outbox = []
        self._test_post_with_valid_data()
        self.assertEqual(len(mail.outbox), 1)

    def test_post_with_not_valid_data(self):
        view_url = self.get_view_url()
        self.client.login(username=self.user.username, password='standard')
        # todo: test with follow=true and check messages
        response = self.client.post(view_url, data=self.invalid_data)
        self.assertEqual(response.status_code, 200)
        self.client.logout()
        # check that we can't login with new password
        login_result = self.client.login(
            username=self.user.username, password=self.new_password)
        self.assertFalse(login_result)


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cached_db')
class ChangePasswordViewTestCase(GetViewUrlMixin,
                                 AllAccountsApphooksTestCase,
                                 CreateChangePasswordCommonTestCasesMixin):
    view_name = 'accounts_change_password'
    new_password = 'new_password'
    valid_data = {
        'password_current': 'standard',
        'password_new': new_password,
    }
    invalid_data = {
        'password_current': 'wrong_password',
        'password_new': new_password,
    }

    def test_get_with_valid_user(self):
        response = self._view_get_with_valid_user_no_assert()
        self.assertContains(response, 'set new password')

    def test_get_with_not_usable_user_password(self):
        response = self._view_get_with_not_usable_user_password()
        self.assertEqual(response.status_code, 302)


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cached_db')
class CreatePasswordViewTestCase(GetViewUrlMixin,
                                 CreateChangePasswordCommonTestCasesMixin,
                                 AllAccountsApphooksTestCase):
    view_name = 'accounts_create_password'
    new_password = 'new_password'
    valid_data = {
        'password_new': new_password,
    }
    invalid_data = {
        'password_new': '',
    }

    def test_get_with_valid_user(self):
        response = self._view_get_with_valid_user_no_assert()
        self.assertEqual(response.status_code, 302)

    def test_get_with_not_usable_user_password(self):
        response = self._view_get_with_not_usable_user_password()
        self.assertContains(response, 'set new password')


class ProfileViewsCommonMixin(object):

    def setUp(self):
        super(ProfileViewsCommonMixin, self).setUp()
        self.user = self.get_standard_user()

    def _view_get_logged_in(self):
        view_url = self.get_view_url()
        self.client.login(username=self.user.username, password='standard')
        response = self.client.get(view_url)
        return response
    def _view_get_not_logged_in(self):
        view_url = self.get_view_url()
        response = self.client.get(view_url)
        return response


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cached_db')
class ProfileViewTestCase(GetViewUrlMixin,
                          ProfileViewsCommonMixin,
                          AllAccountsApphooksTestCase):
    view_name = 'accounts_profile'

    def test_get_not_logged_in(self):
        response = self._view_get_not_logged_in()
        self.assertEqual(response.status_code, 302)

    def test_get_logged_in(self):
        response = self._view_get_logged_in()
        self.assertContains(response, 'Edit settings')


@unittest.skip("Since social aut is not working - don't run this test cases.")
@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cached_db')
class ProfileAssociationsViewTestCase(GetViewUrlMixin,
                                      ProfileViewsCommonMixin,
                                      AllAccountsApphooksTestCase):
    view_name = 'accounts_profile_associations'

    def test_get_not_logged_in(self):
        response = self._view_get_not_logged_in()
        self.assertEqual(response.status_code, 302)

    def test_get_logged_in(self):
        response = self._view_get_logged_in()
        self.assertContains(response, 'Connected accounts')

@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cached_db')
class ProfileEmailListViewTestCase(GetViewUrlMixin,
                                   ProfileViewsCommonMixin,
                                   AllAccountsApphooksTestCase):
    view_name = 'accounts_email_list'

    def test_get_not_logged_in(self):
        response = self._view_get_not_logged_in()
        self.assertEqual(response.status_code, 302)

    def test_get_logged_in(self):
        response = self._view_get_logged_in()
        self.assertContains(response, 'Email addresses')
        self.assertContains(response, 'add')

    def test_get_contains_only_user_owned_itmes(self):
        # standard user email addresses and confirmation objects
        user_email_address = EmailAddress(
            user=self.user,
            email=self.user_email1,
            is_primary=True,
        )
        user_email_address.save()
        user_email_confirmtaion = EmailConfirmation.objects.request(
            user=self.user, email='test@example.com', send=True)

        # staff user email addresses and confirmations
        staff_user = self.get_staff_user_with_std_permissions()
        staff_email_address = EmailAddress(
            user=self.user,
            email=self.user_email1,
            is_primary=True,
        )
        user_email_address.save()
        staff_email_confirmtaion = EmailConfirmation.objects.request(
            user=self.user, email='test@example.com', send=True)
        # get response for standard user
        response = self._view_get_logged_in()
        self.assertContains(response, user_email_address.email)
        self.assertContains(response, user_email_confirmtaion.email)
        # ensure that other user emails are not present
        self.assertNotContains(response, staff_email_address.email)
        self.assertNotContains(response, staff_email_confirmtaion.email)

    def test_post_with_valid_new_email(self):
        view_url = self.get_view_url()
        self.client.login(username=self.user.username, password='standard')
        data = {
            'email': 'new@example.com'
        }
        self.assertEqual(EmailConfirmation.objects.count(), 0)
        response = self.client.post(view_url, data=data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(EmailConfirmation.objects.count(), 1)

    def test_post_with_same_email_two_times(self):
        view_url = self.get_view_url()
        self.client.login(username=self.user.username, password='standard')
        data = {
            'email': 'new@example.com'
        }
        self.assertEqual(EmailConfirmation.objects.count(), 0)
        response = self.client.post(view_url, data=data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(EmailConfirmation.objects.count(), 1)
        # test second time
        response = self.client.post(view_url, data=data)
        self.assertEqual(response.status_code, 200)
        # ensure that another email confirmation object was not created.
        self.assertEqual(EmailConfirmation.objects.count(), 1)

    def test_post_if_email_object_exists(self):
        view_url = self.get_view_url()
        self.client.login(username=self.user.username, password='standard')
        new_email = EmailAddress(
            user=self.user,
            email='new@example.com',
            is_primary=True,
        )
        new_email.save()
        data = {
            'email': 'new@example.com'
        }
        response = self.client.post(view_url, data=data)
        self.assertContains(response, 'This email address is already in use')


class ProfileEmailConfirmationResendViewTestCase(GetViewUrlMixin,
                                                 AllAccountsApphooksTestCase):
    view_name = 'accounts_email_confirmation_resend'

    def setUp(self):
        super(ProfileViewsCommonMixin, self).setUp()
        self.user = self.get_standard_user()
        self.confirmation = EmailConfirmation.objects.request(
            user=self.user, email='test_confirm@example.com', send=True)
        mail.outbox = []
        self.client.login(username=self.user.username, password='standard')

    def test_get_not_logged_in(self):
        self.client.logout()
        view_url = self.get_view_url()
        response = self.client.get(view_url)
        self.assertEqual(response.status_code, 302)

    def test_get_logged_in(self):
        view_url = self.get_view_url(pk=self.confirmation.pk)
        response = self.client.get(view_url)
        self.assertContains(
            response, 'Do you want to re-send the confirmation request')

    def test_get_logged_in_confirmation_for_another_user(self):
        staff_user = self.get_staff_user_with_std_permissions()
        staff_user_confirmation = EmailConfirmation.objects.request(
            user=staff_user, email='staff_confirm@example.com', send=True)
        mail.outbox = []
        view_url = self.get_view_url(pk=staff_user_confirmation.pk)
        response = self.client.get(view_url)
        self.assertEqual(response.status_code, 404)

    def test_post_with_valid_pk(self):
        view_url = self.get_view_url(pk=self.confirmation.pk)
        self.assertEqual(len(mail.outbox), 0)
        response = self.client.post(view_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

    def test_post_with_not_valid_pk(self):
        view_url = self.get_view_url(pk=42)
        self.assertEqual(len(mail.outbox), 0)
        response = self.client.post(view_url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(mail.outbox), 0)

    def test_post_confirmation_for_another_user(self):
        staff_user = self.get_staff_user_with_std_permissions()
        staff_user_confirmation = EmailConfirmation.objects.request(
            user=staff_user, email='staff_confirm@example.com', send=True)
        mail.outbox = []
        view_url = self.get_view_url(pk=staff_user_confirmation.pk)
        response = self.client.post(view_url)
        self.assertEqual(response.status_code, 404)
