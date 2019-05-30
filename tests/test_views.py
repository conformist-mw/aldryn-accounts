# -*- coding: utf-8 -*-


import datetime

from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core import mail
try:
    from django.urls import reverse
except ImportError:
    # Django <= 1.10
    from django.core.urlresolvers import reverse
from django.test import override_settings
from django.utils import unittest
from django.utils.translation import override

# use aldryn account patched settings
from aldryn_accounts.conf import settings
from aldryn_accounts.models import EmailAddress, EmailConfirmation, SignupCode
from .base import AllAccountsApphooksTestCase


class GetViewUrlMixin(object):
    view_name = ''

    def get_view_url(self, view_name=None, **kwargs):
        if view_name is None:
            view_name = self.view_name
        with override('en'):
            view_url = reverse(view_name, kwargs=kwargs)
        return view_url


class ViewsAssertionsMixin(object):

    def assertMessagesContains(self, response, text):
        """
        Test if provided text is in response messages.
        """
        storage = get_messages(response.wsgi_request)
        messages = [msg.message for msg in storage]
        self.assertIn(text, messages)


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
        self.assertRedirects()

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
        # ensure we had a redirect, redirect_chain will look like
        # [('http://testserver/', 302), ('http://testserver/en/', 302)]
        root_url = self.root_page.get_absolute_url()
        self.assertRedirects(response, root_url)


class SignupEmailResendConfirmationViewTestCase(GetViewUrlMixin,
                                                AllAccountsApphooksTestCase):
    view_name = "aldryn_accounts:accounts_signup_email_resend_confirmation"

    def test_get_with_not_existing_email_in_get_params(self):
        """
        Tests get content with email present in get params, but email doesn't
        exists
        """
        # TODO: Check the desired behavior, adjust accordingly
        # should we redirect or 404 if email does not exists or display the
        # form anyway and validate only on post requests?
        view_url = self.get_view_url()
        data = {
            'email': 'not_existing_confirmation@example.com'
        }
        response = self.client.get(view_url, data=data)
        # check the text from template
        expected_string = 'confirmation email to {email} again'.format(**data)
        self.assertContains(
            response, expected_string)
        # and button
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
    view_name = 'aldryn_accounts:accounts_signup_email_confirmation_sent'

    def test_get_no_email(self):
        # TODO: Check the desired behavior, adjust accordingly
        # should we redirect or 404 if the email is not present?
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
        # original message "Sorry, this user doesn't exist.", but ' is escaped
        self.assertContains(response, "Sorry, this user doesn&#39;t exist.")

    def test_post_with_valid_username_no_primary_email(self):
        # Since we cant blindly trust not confirmed emails, we need to ensure
        # that emails with recovery are not sent to not confirmed emails.
        user = self.get_standard_user()
        view_url = self.get_view_url()
        data = {
            'username_or_email': user.username,
        }
        mail.outbox = []
        response = self.client.post(view_url, data=data, follow=True)
        # check that email was not sent
        self.assertEqual(len(mail.outbox), 0)
        expected_msg = "Sorry, this user doesn&#39;t have any verified email."
        self.assertContains(response, expected_msg)

    @override_settings(
        ALDRYN_ACCOUNTS_RESTORE_PASSWORD_RAISE_VALIDATION_ERROR=False)
    def test_post_with_valid_email_no_primary_email(self):
        # Since we cant blindly trust not confirmed emails, we need to ensure
        # that emails with recovery are not sent to not confirmed emails.
        user = self.get_standard_user()
        view_url = self.get_view_url()
        data = {
            'username_or_email': user.email,
        }
        mail.outbox = []
        response = self.client.post(view_url, data=data, follow=True)
        # check that email was not sent
        self.assertEqual(len(mail.outbox), 0)
        # ensure there was a redirect
        self.assertGreater(len(response.redirect_chain), 0)
        expected_message = 'An email was sent'.format(
            user.email)
        self.assertContains(response, expected_message)

    @override_settings(
        ALDRYN_ACCOUNTS_RESTORE_PASSWORD_RAISE_VALIDATION_ERROR=True)
    def test_post_with_valid_email_no_primary_email_check_validation(self):
        # Since we cant blindly trust not confirmed emails, we need to ensure
        # that emails with recovery are not sent to not confirmed emails.
        user = self.get_standard_user()
        view_url = self.get_view_url()
        data = {
            'username_or_email': user.email,
        }
        mail.outbox = []
        response = self.client.post(view_url, data=data, follow=True)
        # check that email was not sent
        self.assertEqual(len(mail.outbox), 0)
        expected_msg = "Sorry, this user doesn&#39;t have any verified email."
        self.assertContains(response, expected_msg)

    @override_settings(
        ALDRYN_ACCOUNTS_RESTORE_PASSWORD_RAISE_VALIDATION_ERROR=True)
    def test_post_with_old_user_email_and_existing_primary(self):
        # Since we cant blindly trust not confirmed emails, we need to ensure
        # that emails with recovery are to confirmed emails.
        user = self.get_standard_user()
        primary_email = 'user_primary@example.com'
        old_email = user.email
        EmailAddress.objects.add_email(
            user=user,
            email=primary_email,
            make_primary=True
        )
        view_url = self.get_view_url()
        data = {
            'username_or_email': old_email,
        }
        mail.outbox = []
        response = self.client.post(view_url, data=data, follow=True)

        # check that email was not sent
        self.assertEqual(len(mail.outbox), 0)
        # ensure there were no redirect
        self.assertEqual(len(response.redirect_chain), 0)
        expected_message = "Sorry, this user doesn&#39;t exist."
        self.assertContains(response, expected_message)

    @override_settings(
        ALDRYN_ACCOUNTS_RESTORE_PASSWORD_RAISE_VALIDATION_ERROR=True)
    def test_post_with_valid_email_and_primary_email_for_primary_email(self):
        # Since we cant blindly trust not confirmed emails, we need to ensure
        # that emails with recovery are to confirmed emails.
        user = self.get_standard_user()
        primary_email = 'user_primary@example.com'
        email = EmailAddress.objects.add_email(
            user=user,
            email=primary_email,
            make_primary=True
        )
        view_url = self.get_view_url()
        data = {
            'username_or_email': primary_email,
        }
        mail.outbox = []
        response = self.client.post(view_url, data=data, follow=True)
        # check that email was not sent
        self.assertEqual(len(mail.outbox), 1)
        # ensure there was a redirect
        self.assertGreater(len(response.redirect_chain), 0)
        # expect that email was sent to primary address
        self.assertContains(response, primary_email)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, [primary_email])
        # ensure template text
        expected_message = "An email was sent"
        self.assertContains(response, expected_message)


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cached_db')
class ConfirmEmailViewTestCase(GetViewUrlMixin,
                               ViewsAssertionsMixin,
                               AllAccountsApphooksTestCase):
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
        # test that success messages is present in response
        self.assertMessagesContains(response,
                                    'You have confirmed test@example.com.')
        self.assertGreater(len(response.redirect_chain), 0)
        expected_url = self.page_profile_email_settings.get_absolute_url('en')
        self.assertRedirects(response, expected_url)
        # ensure user has been logged in after success
        self.assertIn(SESSION_KEY, self.client.session)
        # refresh user from db
        self.user = User.objects.get(pk=self.user.pk)
        self.assertTrue(self.user.is_active)

    def test_post_with_verified_email_no_delete(self):
        view_url = self.get_view_url(key=self.confirmation_object.key)
        # ensure user was not logged in
        self.assertNotIn(SESSION_KEY, self.client.session)
        # confirm email, but leave the item
        self.confirmation_object.confirm(delete=False)
        mail.outbox = []
        response = self.client.post(view_url, follow=True)
        self.assertMessagesContains(
            response,
            'This email has already been verified with an other account.')
        # ensure user was not logged in and not affected
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.user = User.objects.get(pk=self.user.pk)
        self.assertFalse(self.user.is_active)

    def test_post_with_verified_email_returns404(self):
        view_url = self.get_view_url(key=self.confirmation_object.key)
        self.confirmation_object.confirm()
        response = self.client.post(view_url)
        self.assertEqual(response.status_code, 404)

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
        self.assertMessagesContains(response, 'The activation key has expired.')
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
        response = self.client.get(view_url, follow=True)
        return response

    def test_post_with_not_authenticated_user(self):
        view_url = self.get_view_url()
        response = self.client.post(view_url)
        self.assertEqual(response.status_code, 302)

    def _test_post_with_valid_data(self, set_unusable_password=False):
        view_url = self.get_view_url()
        self.client.login(username=self.user.username, password='standard')
        if set_unusable_password:
            self.user.set_unusable_password()
            self.user.save()
        response = self.client.post(view_url, data=self.valid_data, follow=True)
        self.client.logout()
        # check that we can login with new password
        login_result = self.client.login(
            username=self.user.username, password=self.new_password)
        self.assertTrue(login_result)
        return response

    def test_post_with_valid_data_no_extra_settings(
            self, set_unusable_password=False):
        self._test_post_with_valid_data(
            set_unusable_password=set_unusable_password)

    @override_settings(ALDRYN_ACCOUNTS_NOTIFY_PASSWORD_CHANGE=False)
    def test_post_with_valid_data_dont_send_email(self,
                                                  set_unusable_password=False):
        mail.outbox = []
        response = self._test_post_with_valid_data(
            set_unusable_password=set_unusable_password)
        expected_url = self.page_profile_index.get_absolute_url('en')
        self.assertRedirects(response, expected_url)
        self.assertMessagesContains(response, 'Password successfully changed.')
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(ALDRYN_ACCOUNTS_NOTIFY_PASSWORD_CHANGE=True)
    def test_post_with_valid_data_and_send_email(self,
                                                 set_unusable_password=False):
        mail.outbox = []
        response = self._test_post_with_valid_data(
            set_unusable_password=set_unusable_password)
        expected_url = self.page_profile_index.get_absolute_url('en')
        self.assertRedirects(response, expected_url)
        self.assertMessagesContains(response, 'Password successfully changed.')
        self.assertEqual(len(mail.outbox), 1)

    def test_post_with_not_valid_data(self, set_unusable_password=False):
        view_url = self.get_view_url()
        self.client.login(username=self.user.username, password='standard')
        if set_unusable_password:
            self.user.set_unusable_password()
            self.user.save()
        response = self.client.post(view_url, data=self.invalid_data,
                                    follow=True)
        self.client.logout()
        # check that we can't login with new password
        login_result = self.client.login(
            username=self.user.username, password=self.new_password)
        self.assertFalse(login_result)


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cached_db')
class ChangePasswordViewTestCase(GetViewUrlMixin,
                                 ViewsAssertionsMixin,
                                 CreateChangePasswordCommonTestCasesMixin,
                                 AllAccountsApphooksTestCase):
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
        expected_url = self.get_view_url(view_name='accounts_create_password')
        self.assertRedirects(response, expected_url)


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cached_db')
class CreatePasswordViewTestCase(GetViewUrlMixin,
                                 ViewsAssertionsMixin,
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

    def test_post_with_valid_data_no_extra_settings(self,
                                                    set_unusable_password=True):
        super(CreatePasswordViewTestCase,
              self).test_post_with_valid_data_no_extra_settings(
            set_unusable_password=set_unusable_password)

    def test_post_with_valid_data_dont_send_email(self,
                                                  set_unusable_password=True):
        super(CreatePasswordViewTestCase,
              self).test_post_with_valid_data_dont_send_email(
            set_unusable_password=set_unusable_password)

    def test_post_with_not_valid_data(self, set_unusable_password=True):
        super(CreatePasswordViewTestCase, self).test_post_with_not_valid_data(
            set_unusable_password=set_unusable_password)

    def test_post_with_valid_data_and_send_email(self,
                                                 set_unusable_password=True):
        super(CreatePasswordViewTestCase,
              self).test_post_with_valid_data_and_send_email(
            set_unusable_password=set_unusable_password)


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
        expected_username = 'username: {0}'.format(self.user.username)
        expected_user_email = 'email: {0}'.format(self.user.email)
        self.assertContains(response, expected_username)
        self.assertContains(response, expected_user_email)


@unittest.skip("Since social auth is not working - don't run this test cases.")
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
            email='user_email@example.com',
            is_primary=True,
        )
        user_email_address.save()
        user_email_confirmtaion = EmailConfirmation.objects.request(
            user=self.user, email='test@example.com', send=True)

        # staff user email addresses and confirmations
        staff_user = self.get_staff_user_with_std_permissions()
        staff_email_address = EmailAddress(
            user=staff_user,
            email='staff_email@example.com',
            is_primary=True,
        )
        user_email_address.save()
        staff_email_confirmtaion = EmailConfirmation.objects.request(
            user=staff_user, email='staff_test@example.com', send=True)
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
        response = self.client.post(view_url, data=data, follow=True)
        self.assertRedirects(response, view_url)
        self.assertEqual(EmailConfirmation.objects.count(), 1)
        # test second time
        response = self.client.post(view_url, data=data, follow=True)
        self.assertRedirects(response, view_url)
        # ensure that another email confirmation object was created.
        # the actual owner of email can only confirm the email
        # redundant emails can be deleted on cleanup or other way.
        self.assertEqual(EmailConfirmation.objects.count(), 2)

    def test_post_if_email_objeselfct_exists(self):
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


class ProfileEmailConfirmationCommonMixin(object):
    confirmation_email_addr = 'test_confirm@example.com'

    def setUp(self):
        self.user = self.get_standard_user()
        self.staff_user = self.get_staff_user_with_std_permissions()
        super(ProfileEmailConfirmationCommonMixin, self).setUp()
        self.client.login(username=self.user.username, password='standard')

    def _get_not_logged_in(self, **kwargs):
        self.client.logout()
        view_url = self.get_view_url(**kwargs)
        response = self.client.get(view_url)
        return response

    def _get_logged_in(self, **kwargs):
        view_url = self.get_view_url(**kwargs)
        response = self.client.get(view_url)
        return response

    def _get_logged_in_confirmation_for_another_user(self):
        staff_user_confirmation = EmailConfirmation.objects.request(
            user=self.staff_user, email='staff_confirm@example.com', send=True)
        mail.outbox = []
        view_url = self.get_view_url(pk=staff_user_confirmation.pk)
        response = self.client.get(view_url)
        return response

    def _post_with_valid_pk(self, **kwargs):
        view_url = self.get_view_url(**kwargs)
        self.assertEqual(len(mail.outbox), 0)
        response = self.client.post(view_url)
        return response

    def _post_with_not_valid_pk(self, pk=42):
        view_url = self.get_view_url(pk=pk)
        self.assertEqual(len(mail.outbox), 0)
        response = self.client.post(view_url)
        return response

    def _post(self, **kwargs):
        view_url = self.get_view_url(**kwargs)
        response = self.client.post(view_url)
        return response


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cached_db')
class ProfileEmailConfirmationResendViewTestCase(
    GetViewUrlMixin,
    ProfileEmailConfirmationCommonMixin,
    AllAccountsApphooksTestCase):
    view_name = 'accounts_email_confirmation_resend'

    def setUp(self):
        super(ProfileEmailConfirmationResendViewTestCase, self).setUp()
        self.confirmation = EmailConfirmation.objects.request(
            user=self.user, email=self.confirmation_email_addr, send=True)
        self.staff_user_confirmation = EmailConfirmation.objects.request(
            user=self.staff_user, email='staff_confirm@example.com', send=True)
        mail.outbox = []

    def test_get_not_logged_in(self):
        response = self._get_not_logged_in(pk=self.confirmation.pk)
        self.assertEqual(response.status_code, 302)

    def test_get_logged_in(self):
        response = self._get_logged_in(pk=self.confirmation.pk)
        self.assertContains(
            response, 'Do you want to re-send the confirmation request')

    def test_get_logged_in_confirmation_for_another_user(self):
        response = self._get_logged_in_confirmation_for_another_user()
        self.assertEqual(response.status_code, 404)

    def test_post_with_valid_pk(self):
        response = self._post_with_valid_pk(pk=self.confirmation.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

    def test_post_with_not_valid_pk(self):
        response = self._post_with_not_valid_pk()
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(mail.outbox), 0)

    def test_post_confirmation_for_another_user(self):
        response = self._post(pk=self.staff_user_confirmation.pk)
        self.assertEqual(response.status_code, 404)


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cached_db')
class ProfileEmailConfirmationCancelViewTestCase(
      GetViewUrlMixin,
      ProfileEmailConfirmationCommonMixin,
      AllAccountsApphooksTestCase):
    view_name = 'accounts_email_confirmation_cancel'

    def setUp(self):
        super(ProfileEmailConfirmationCancelViewTestCase, self).setUp()
        self.confirmation = EmailConfirmation.objects.request(
            user=self.user, email=self.confirmation_email_addr, send=True)
        self.staff_user_confirmation = EmailConfirmation.objects.request(
            user=self.staff_user, email='staff_confirm@example.com', send=True)
        mail.outbox = []

    def test_get_not_logged_in(self):
        response = self._get_not_logged_in(pk=self.confirmation.pk)
        self.assertEqual(response.status_code, 302)

    def test_get_logged_in(self):
        response = self._get_logged_in(pk=self.confirmation.pk)
        self.assertContains(
            response,
            'cancel the confirmation request for {0}'.format(
                self.confirmation_email_addr))

    def test_post_with_valid_pk(self):
        confirmation_pk = self.confirmation.pk
        response = self._post_with_valid_pk(pk=self.confirmation.pk)
        self.assertFalse(
            EmailConfirmation.objects.filter(pk=confirmation_pk).exists())
        self.assertEqual(response.status_code, 302)

    def test_post_with_not_valid_pk(self):
        confirmation_pk = self.confirmation.pk
        response = self._post_with_not_valid_pk()
        self.assertTrue(
            EmailConfirmation.objects.filter(pk=confirmation_pk).exists())
        self.assertEqual(response.status_code, 404)

    def test_post_confirmation_for_another_user(self):
        staf_user_confirmation_pk = self.staff_user_confirmation.pk
        response = self._post(pk=self.staff_user_confirmation.pk)
        self.assertTrue(EmailConfirmation.objects.filter(
            pk=staf_user_confirmation_pk).exists())
        self.assertEqual(response.status_code, 404)


class ProfileEmailObjectsSetupMixin(object):

    def setUp(self):
        super(ProfileEmailObjectsSetupMixin, self).setUp()
        # regular user
        self.user_email_1 = EmailAddress.objects.add_email(
            user=self.user,
            email='user_first@example.com',
            make_primary=True)
        self.user_email_2 = EmailAddress.objects.add_email(
            user=self.user,
            email='user_second@example.com',
            make_primary=False)
        # staff user
        self.staff_email_1 = EmailAddress.objects.add_email(
            user=self.staff_user,
            email='staff_first@example.com',
            make_primary=True)
        self.staff_email_2 = EmailAddress.objects.add_email(
            user=self.staff_user,
            email='staff_second@example.com',
            make_primary=False)


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cached_db')
class ProfileEmailMakePrimaryViewTestCase(
      GetViewUrlMixin,
      ProfileEmailConfirmationCommonMixin,
      ProfileEmailObjectsSetupMixin,
      AllAccountsApphooksTestCase):
    view_name = 'accounts_email_make_primary'

    def test_get_not_logged_in(self):
        email_pk = self.user_email_1.pk
        response = self._get_not_logged_in(pk=email_pk)
        self.assertEqual(response.status_code, 302)

    def test_get_logged_in(self):
        email_pk = self.user_email_2.pk
        response = self._get_logged_in(pk=email_pk)
        self.assertContains(
            response,
            'to make {0} your primary email'.format(
                self.user_email_2.email))

    def test_post_with_valid_pk(self):
        email_1_pk = self.user_email_1.pk
        email_2_pk = self.user_email_2.pk
        response = self._post_with_valid_pk(pk=email_2_pk)
        user_email_1 = EmailAddress.objects.get(pk=email_1_pk)
        user_email_2 = EmailAddress.objects.get(pk=email_2_pk)
        self.assertFalse(user_email_1.is_primary)
        self.assertTrue(user_email_2.is_primary)
        self.assertEqual(response.status_code, 302)

    def test_post_with_not_valid_pk(self):
        response = self._post_with_not_valid_pk()
        user_email_1 = EmailAddress.objects.get(pk=self.user_email_1.pk)
        self.assertTrue(user_email_1.is_primary)
        self.assertEqual(response.status_code, 404)

    def test_post_for_another_user(self):
        staf_user_email_pk = self.staff_email_2.pk
        response = self._post(pk=staf_user_email_pk)
        self.assertTrue(EmailAddress.objects.filter(
            pk=staf_user_email_pk).exists())
        self.assertEqual(response.status_code, 404)


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cached_db')
class ProfileEmailDeleteViewTestCase(
      GetViewUrlMixin,
      ProfileEmailConfirmationCommonMixin,
      ProfileEmailObjectsSetupMixin,
      AllAccountsApphooksTestCase):
    view_name = 'accounts_email_delete'

    def test_get_not_logged_in(self):
        # we are using second email, because user shouldn't be able to delete
        # the primary email
        email_pk = self.user_email_2.pk
        response = self._get_not_logged_in(pk=email_pk)
        self.assertEqual(response.status_code, 302)

    def test_get_logged_in(self):
        # we are using second email, because user shouldn't be able to delete
        # the primary email
        email_pk = self.user_email_2.pk
        response = self._get_logged_in(pk=email_pk)
        self.assertContains(
            response,
            'to remove {0} from your account'.format(
                self.user_email_2.email))

    def test_get_logged_in_for_another_user(self):
        staf_user_email_pk = self.staff_email_2.pk
        response = self._get_logged_in(pk=staf_user_email_pk)
        self.assertEqual(response.status_code, 404)

    def test_post_with_valid_pk(self):
        email_1_pk = self.user_email_1.pk
        email_2_pk = self.user_email_2.pk
        response = self._post_with_valid_pk(pk=email_2_pk)
        # first email exists
        self.assertTrue(
            EmailAddress.objects.filter(pk=email_1_pk).exists())
        # second email does not exists
        self.assertFalse(
            EmailAddress.objects.filter(pk=email_2_pk).exists())
        self.assertEqual(response.status_code, 302)

    def test_post_with_not_valid_pk(self):
        response = self._post_with_not_valid_pk()
        user_email_1 = EmailAddress.objects.filter(pk=self.user_email_1.pk)
        self.assertTrue(user_email_1.exists())
        self.assertEqual(response.status_code, 404)

    def test_post_with_primary_email_address(self):
        primary_email_pk = self.user_email_1.pk
        response = self._post_with_valid_pk(pk=primary_email_pk)
        user_email_1 = EmailAddress.objects.filter(pk=primary_email_pk)
        self.assertTrue(user_email_1.exists())
        self.assertEqual(response.status_code, 404)

    def test_post_for_another_user(self):
        staf_user_email_pk = self.staff_email_2.pk
        response = self._post(pk=staf_user_email_pk)
        self.assertTrue(EmailAddress.objects.filter(
            pk=staf_user_email_pk).exists())
        self.assertEqual(response.status_code, 404)


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cached_db')
class UserSettingsViewTestCase(GetViewUrlMixin,
                               AllAccountsApphooksTestCase):
    view_name = 'accounts_settings'

    def setUp(self):
        self.user = self.get_standard_user()
        self.staff_user = self.get_staff_user_with_std_permissions()
        super(UserSettingsViewTestCase, self).setUp()

    def test_get_not_logged_in(self):
        view_url = self.get_view_url()
        response = self.client.get(view_url)
        self.assertEqual(response.status_code, 302)

    def test_get_logged_in(self):
        self.client.login(username=self.user.username, password='standard')
        view_url = self.get_view_url()
        response = self.client.get(view_url)
        self.assertContains(response, 'Settings')
        self.assertContains(response, 'save')
