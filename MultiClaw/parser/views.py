from django.shortcuts import render
from parser.models import ShopwareShop
from parser.forms import ShopwareShopForm
from django.http import HttpResponse, JsonResponse, HttpRequest
import time
import pkgutil

from parser.SW6ApiHandler import SW6Shop
from parser import Parser

# @login_required
def export(request, parser_name=None, destination=None):
    
    available_parsers = [
        modname
        for i, (importer, modname, ispkg)
        in enumerate(pkgutil.iter_modules(Parser.__path__))
    ]
    
    form = ShopwareShopForm(initial={
        'user': request.user,
        'domain': 'traum-fahrrad.com',
        'username': 'adminpha',
        'password': '121416qQ**',
    })
            
    context = {
        'destinations': 
            [
                'Shopwae 6',
                'WooCommerce',
                'Shopify'                         
            ],
        'destination': destination,
        'form': form,
        'available_parsers': available_parsers,
    }
    
    return render(request, 'users/pages/export.html', context=context)


def check_shop_connection(request):
    
    user = request.user    
    instance = ShopwareShop()
    form = ShopwareShopForm(request.POST, instance=instance)
    
    print(form.errors)
    time.sleep(1)
    
    shop_auth = form.save()
    shop_auth.password = '121416qQ**'  # for testing only for now 
    
    shopware_instance = sw = SW6Shop(
        target=shop_auth.domain,
        username=shop_auth.username,
        password=shop_auth.password,
    )
        
    token_response = sw.fetch_access_token()
    for k, v in token_response.json().items():
        print(k, v)
    
    
    # time.sleep(1)
    
    return HttpResponse('test')