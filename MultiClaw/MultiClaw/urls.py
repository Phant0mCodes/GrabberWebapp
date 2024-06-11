"""
URL configuration for MultiClaw project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from users import views as user_views
from parser import views as parser_views

user_urls = [
    path('tos/', user_views.tos, name='tos'),
    path('register/', user_views.register, name='register'),
    path('login/', user_views.login_view, name='login'),
    path('logout/', user_views.logout_view, name='logout'),
    path('account/', user_views.account, name='account'),
    path('dashboard/', user_views.dashboard, name='dashboard'),
    path('topup/', user_views.topup, name='topup'),
    path('start/', user_views.start_grab, name='start'),
    path('start/<parser_name>', user_views.start_grab, name='start'),
    path('status/', user_views.status, name='status'),
    path('grabs/', user_views.grabs, name='grabs'),
    path('database/', user_views.database, name='database'),
    path('stats/', user_views.stats, name='stats'),
    path('generate_bitcoin_address/', user_views.generate_bitcoin_address, name='generate_bitcoin_address'),
    path('fetch_btc_rate_view/', user_views.fetch_btc_rate_view, name='fetch_btc_rate_view'),
    path('fetch_payment_status_view/', user_views.fetch_payment_status_view, name='fetch_payment_status_view'),
]

export_urls = [
    path('export/', parser_views.export, name='export'),
    path('export/<parser_name>/<destination>', parser_views.export, name='export'),
    path('check_shop_connection/', parser_views.check_shop_connection, name='check_shop_connection'),
]

parser_urls = [
    path('start_grab_thread/', user_views.start_grab_thread, name='start_grab_thread'),

]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include(user_urls)),
    path('', include(parser_urls)),
    path('', include(export_urls)),
    path("__reload__/", include("django_browser_reload.urls")),
]
