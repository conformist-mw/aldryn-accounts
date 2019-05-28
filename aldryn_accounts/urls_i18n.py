# -*- coding: utf-8 -*-
from django.conf import settings

try:
    from django.conf.urls import include, url
except ImportError:
    from django.conf.urls.defaults import include, url

from . import views, utils


accounts_urlpatterns = [
    url(r'^signup/$', utils.get_signup_view().as_view(), name='accounts_signup'),
    url(r'^signup/email/resend-confirmation/$', views.SignupEmailResendConfirmationView.as_view(),
        name='accounts_signup_email_resend_confirmation'),
    url(r'^signup/email/confirmation-sent/$', views.SignupEmailConfirmationSentView.as_view(),
        name='accounts_signup_email_confirmation_sent'),
    url(r'^signup/email/sent/$', views.SignupEmailSentView.as_view(), name='accounts_signup_email_sent'),

    url(r'^login/$', utils.get_login_view().as_view(), name='login'),
    url(r'^logout/$', views.LogoutView.as_view(), name='logout'),

    url(r'^password-reset/$', views.password_reset, name='password_reset'),  # new name should be password_reset
    url(r'^password-reset/sent/$', views.password_reset_done, name='password_reset_done'),
    url(r'^password-reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        views.password_reset_confirm, name='password_reset_confirm'),
    url(r'^password-reset/done/$', views.password_reset_complete, name='password_reset_complete'),

    url(r'^email/confirm/(?P<key>\w+)/$', views.ConfirmEmailView.as_view(), name='accounts_confirm_email'),
]


profile_index_urlpatterns = [
    url(r'^$', views.ProfileView.as_view(), name='accounts_profile'),
]


profile_settings_urlpatterns = [
    url(r'^$', views.UserSettingsView.as_view(), name='accounts_settings')
]


associations_urlpatterns = [
    url(r'^$', views.ProfileAssociationsView.as_view(), name='accounts_profile_associations'),
]


change_password_urlpatterns = [
    url(r'^$', views.ChangePasswordView.as_view(), name='accounts_change_password'),
    url(r'^create/$', views.CreatePasswordView.as_view(), name='accounts_create_password'),
]


email_settings_urlpatterns = [
    url(r'^$', views.ProfileEmailListView.as_view(), name='accounts_email_list'),
    url(r'^confirmation/(?P<pk>\d+)/re-send/$', views.ProfileEmailConfirmationResendView.as_view(), name='accounts_email_confirmation_resend'),
    url(r'^confirmation/(?P<pk>\d+)/cancel/$', views.ProfileEmailConfirmationCancelView.as_view(), name='accounts_email_confirmation_cancel'),
    url(r'^(?P<pk>\d+)/delete/$', views.ProfileEmailDeleteView.as_view(), name='accounts_email_delete'),
    url(r'^(?P<pk>\d+)/make_primary/$', views.ProfileEmailMakePrimaryView.as_view(), name='accounts_email_make_primary'),
]

ALDRYN_ACCOUNTS_USE_PROFILE_APPHOOKS = getattr(settings, 'ALDRYN_ACCOUNTS_USE_PROFILE_APPHOOKS', False)
if not ALDRYN_ACCOUNTS_USE_PROFILE_APPHOOKS:
    accounts_urlpatterns += [
        url(r'^profile/settings/', include(profile_settings_urlpatterns)),
        url(r'^profile/associations/', include(associations_urlpatterns)),
        url(r'^profile/password/', include(change_password_urlpatterns)),
        url(r'^profile/email/', include(email_settings_urlpatterns)),
        url(r'^profile/', include(profile_index_urlpatterns)),
    ]

prefix = getattr(settings, 'ALDRYN_ACCOUNTS_URLS_PREFIX', '')
prefix = '{}/'.format(prefix) if prefix else ''

urlpatterns = [
    url(r'^{}'.format(prefix), include((accounts_urlpatterns, 'aldryn_accounts'), namespace='aldryn_accounts'))
]
