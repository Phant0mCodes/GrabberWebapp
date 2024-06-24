from django.shortcuts import render
from parser.models import ShopwareShop
from parser.forms import ShopwareShopForm
from django.http import HttpResponse, JsonResponse, HttpRequest
import time
import pkgutil
import asyncio
from django.views.decorators.csrf import csrf_exempt
from importlib import import_module

from parser.SW6ApiHandler import SW6Shop
from parser import Parser, Core
from parser.models import Settings
from parser.forms import SettingsForm

# @login_required
def export(request, parser_name=None):
    
    print(' export req ')
    
    available_parsers = [
        modname
        for i, (importer, modname, ispkg)
        in enumerate(pkgutil.iter_modules(Parser.__path__))
    ]
    
    shopware_form = ShopwareShopForm(initial={
        'user': request.user,
        'domain': 'traum-fahrrad.com',
        'username': 'adminpha',
        'password': '121416qQ**',
    })

    settings = None
    settings_form = None
    settings_models = Settings.objects.filter(user=request.user, parser_name=parser_name)
    if settings_models:
        settings = settings_models[0]
        settings_form = SettingsForm(instance=settings)
        print(settings.category_urls)
    
    if request.method == 'POST':
        settings_form = SettingsForm(request.POST, instance=settings)
        if settings_form.is_valid():
            settings_form.save()
    
    context = {
        'shopware_form': shopware_form,
        'available_parsers': available_parsers,
        'settings_form': settings_form,
        'parser_name': parser_name,
        'settings': settings,
    }
    
    return render(request, 'users/pages/export.html', context=context)


def check_shop_connection(request):  
    
    user = request.user    
    instance = ShopwareShop.objects.get(pk=request.POST['domain'])
    form = ShopwareShopForm(request.POST, instance=instance)
    
    shop_auth = form.save()
    
    shop_auth.password = '121416qQ**'  # for testing only for now 
    shop_auth.save()
    
    shopware_instance = sw = SW6Shop(
        target=form.data['domain'],
        username=form.data['username'],
        password=shop_auth.password,
    )
        
    token_response = sw.fetch_access_token()
    
    shop_auth.valid = True
    shop_auth.save()
        
    return HttpResponse('test')

@csrf_exempt
def start_export(request):
    
    parser_name = request.POST['parser_name']
    settings_model = Settings.objects.filter(user=request.user, parser_name=parser_name)[0]
    parser_module = import_module(f'parser.Parser.{parser_name}')
    parser_class = getattr(parser_module, parser_name)
    parser_instance: Core = parser_class(settings_model)
    
    asyncio.run(parser_instance.export())
    
    if request.method == "POST":       
        return HttpResponse()