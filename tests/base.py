# -*- coding: utf-8 -*-


import random
import string
import sys

from cms import api
from cms.apphook_pool import apphook_pool
from cms.appresolver import clear_app_resolvers
from cms.exceptions import AppAlreadyRegistered
from cms.test_utils.testcases import CMSTestCase
from cms.utils import get_cms_setting
from django.conf import settings
from django.core.cache import cache
try:
    from django.urls import clear_url_caches
except ImportError:
    # Django <= 1.10
    from django.core.urlresolvers import clear_url_caches

from aldryn_accounts import cms_app


class CleanUpMixin(object):
    apphook_objects = None

    def tearDown(self):
        """
        Do a proper cleanup, delete everything what is preventing us from
        clean environment for tests.
        :return: None
        """
        self.reset_all()
        cache.clear()
        super(CleanUpMixin, self).tearDown()

    def get_apphook_objects(self):
        return self.apphook_objects #if self.apphook_objects else []

    def get_apphook_config(self):
        """
        Implement this method if you need to delete apphook.
        Should return app_hook config instance.
        """
        return getattr(self, 'app_config', None)

    def reset_apphook_cmsapp(self, apphook_objects=None):
        """
        For tests that should not be polluted by previous setup we need to
        ensure that app hooks are reloaded properly. One of the steps is to
        reset the relation between EventListAppHook and EventsConfig
        """
        if apphook_objects is None:
            apphook_objects = self.get_apphook_objects()
        for apphook_object in apphook_objects:
            app_config = getattr(apphook_object, 'app_config', None)
            if app_config and getattr(app_config, 'cmsapp', None):
                delattr(apphook_object.app_config, 'cmsapp')
            if getattr(app_config, 'cmsapp', None):
                delattr(app_config, 'cmsapp')

    def reset_all(self):
        """
        Reset all that could leak from previous test to current/next test.
        :return: None
        """
        apphook_objects = self.get_apphook_objects()
        for apphook_object in apphook_objects:
            self.delete_app_module(apphook_object.__module__)
        self.reload_urls(apphook_objects)
        self.apphook_clear()

    def delete_app_module(self, app_modules=None):
        """
        Remove APP_MODULE from sys.modules. Taken from cms.
        :return: None
        """
        if app_modules is None:
            app_modules = [apphook_object.__module__
                           for apphook_object in self.get_apphook_objects()]
        for app_module in app_modules:
            if app_module in sys.modules:
                del sys.modules[app_module]

    def apphook_clear(self):
        """
        Clean up apphook_pool and sys.modules. Taken from cms with slight
        adjustments and fixes.
        :return: None
        """
        try:
            apphooks = apphook_pool.get_apphooks()
        except AppAlreadyRegistered:
            # there is an issue with discover apps, or i'm using it wrong.
            # setting discovered to True solves it. Maybe that is due to import
            # from aldryn_events.cms_app which registers EventListAppHook
            apphook_pool.discovered = True
            apphooks = apphook_pool.get_apphooks()

        for name, label in list(apphooks):
            if apphook_pool.apps[name].__class__.__module__ in sys.modules:
                del sys.modules[apphook_pool.apps[name].__class__.__module__]
        apphook_pool.clear()
        self.reset_apphook_cmsapp()

    def reload_urls(self, apphook_objects=None):
        """
        Clean up url related things (caches, app resolvers, modules).
        Taken from cms.
        :return: None
        """
        clear_app_resolvers()
        clear_url_caches()

        if apphook_objects is None:
            apphook_objects = self.get_apphook_objects()

        apphooked_urls = []
        for apphook_object in apphook_objects:
            app_module = apphook_object.__module__
            package = app_module.split('.')[0]
            apphooked_urls.append('{0}.urls'.format(package))

        # build url modules
        url_modules = ['cms.urls']
        url_modules += apphooked_urls
        url_modules.append(settings.ROOT_URLCONF)

        for module in url_modules:
            if module in sys.modules:
                del sys.modules[module]


class AcountsSetupMixin(object):
    set_up_apphooks = True

    def setUp(self):
        self.template = get_cms_setting('TEMPLATES')[0][0]
        self.language = settings.LANGUAGES[0][0]
        self.root_page = api.create_page(
            'root page',
            self.template,
            self.language, published=True)
        pages_to_publish = [self.root_page]
        if self.set_up_apphooks:
            self.page_profile_index = self.create_app_page(
                app_hook_name='AldrynAccountsUserProfileIndexApphook')
            self.page_profile_settings = self.create_app_page(
                app_hook_name='AldrynAccountsUserProfileSettingsApphook')
            self.page_profile_change_password = self.create_app_page(
                app_hook_name='AldrynAccountsUserProfileChangePasswordApphook')
            self.page_profile_email_settings = self.create_app_page(
                app_hook_name='AldrynAccountsUserProfileEmailSettingsApphook')
            pages_to_publish += [
                self.page_profile_index,
                self.page_profile_settings,
                self.page_profile_change_password,
                self.page_profile_email_settings,
            ]
        self.plugin_page = api.create_page(
            title="plugin_page",
            template=self.template,
            language=self.language,
            parent=self.root_page,
            published=True
        )
        pages_to_publish.append(self.plugin_page)
        for page in pages_to_publish:
            for language, _ in settings.LANGUAGES[1:]:
                api.create_title(language, page.get_slug(), page)
                page.publish(language)

    def create_app_page(self, page_name=None, app_hook_name=None):
        if app_hook_name is None:
            app_hook_name = self.get_apphook_object().__name__
        if page_name is None:
            page_name = '{0} page'.format(app_hook_name)
        page = api.create_page(
            page_name,
            self.template,
            self.language,
            published=True,
            apphook=app_hook_name,
        )
        return page

    @classmethod
    def rand_str(cls, prefix='', length=23, chars=string.ascii_letters):
        return prefix + ''.join(random.choice(chars) for _ in range(length))


class AllAccountsApphooksTestCase(CleanUpMixin,
                                  AcountsSetupMixin,
                                  CMSTestCase):
    apphook_objects = [
        cms_app.AldrynAccountsUserProfileIndexApphook,
        cms_app.AldrynAccountsUserProfileSettingsApphook,
        cms_app.AldrynAccountsUserProfileChangePasswordApphook,
        cms_app.AldrynAccountsUserProfileEmailSettingsApphook,
    ]
