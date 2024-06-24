# users/views.py
import importlib
import asyncio
from threading import Thread
from importlib import import_module
from dataclasses import asdict, fields
from django.http import HttpResponse, JsonResponse, HttpRequest
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from bitcoinaddress import Wallet
import requests
import pkgutil
from users.forms import CustomUserCreationForm, CustomAuthForm
from users.models import BitcoinAddress
from parser import Parser
from parser.forms import SettingsForm
from parser.models import Modes, Settings
from parser.Core import Core

def tos(request):
    return HttpResponse()


def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        
        if form.is_valid():
            form.save()
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            login(request, user)
            
            return redirect('dashboard')
    else:
        form = CustomUserCreationForm()

    return render(request, 'users/register.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        form = CustomAuthForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('dashboard')
    else:
        form = CustomAuthForm()
    return render(request, 'users/login.html', {'form': form})


def logout_view(request):
    print(request.user.credits_amount)
    logout(request)
    return redirect('dashboard')


@login_required
def account(request):
    return render(request, 'users/account.html')


@login_required
def dashboard(request):
    return render(request, 'users/pages/dashboard.html')


# @login_required
def topup(request):
    
    pending_address = None
    user = request.user
    pending_addresses = BitcoinAddress.objects.filter(user=user, status__in=['pending', 'paid'])
    if pending_addresses:
        pending_address = pending_addresses[0]
        # check payment status
        status_data = fetch_payment_status(pending_address.public_address, pending_address.amount)
        if status_data['paid'] and pending_address.status == "pending":
            pending_address.status = 'paid'
            pending_address.transaction = status_data['txid']
            pending_address.status = 'paid'
            pending_address.confirmations = status_data['confirmations']
            pending_address.save()
            print('status is now paid')
        else:
            print('not paid yet, still pending')
        
    context = {
        'btc_rate': fetch_btc_rate(),
        'pending_address': pending_address,
        'test': 'testfromviews'
    }

    return render(request, 'users/pages/topup.html', context=context)


# @login_required
def start_grab(request, parser_name=None):
        
    available_parsers = [
        modname
        for i, (importer, modname, ispkg)
        in enumerate(pkgutil.iter_modules(Parser.__path__))
    ]
    features_instance = None
    features_fields = None
    settings = None
    
    settings_models = Settings.objects.filter(user=request.user, parser_name=parser_name)
    if settings_models:
        settings = settings_models[0]
        form = SettingsForm(instance=settings)
    
    else:
        form = SettingsForm(initial={
        'user': request.user,
        'parser_name': parser_name,
        'parser_mode': Modes.CATEGORY_URLS.name,
        'max_page_amount': 0,
        'min_price': 200,
        'max_price': 1000,
        }
    )
    
    if request.method == "POST":
        form = SettingsForm(request.POST, instance=settings)
        print(form.errors)
        if form.is_valid():
            form.save()
    
    if parser_name:
        module = importlib.import_module(f'parser.Parser.{parser_name}')
        parser: Core = getattr(module, parser_name)  # actually the parser module should be annotated, but for intellisense it is the core module
        features_instance = parser.FEATURES
        features_fields = [
            (getattr(features_instance, field.name), field.metadata) 
            for field in fields(features_instance)
        ]

    context = {
        'parsers': available_parsers,
        'parser_name': parser_name,
        'features_instance': features_instance,
        'features_fields': features_fields,
        'form': form,
        'settings': settings
    }
    
    return render(request, 'users/pages/start_grab.html', context=context)

@csrf_exempt
def start_grab_thread(request):
    parser_name = request.POST['parser_name']

    settings_model = Settings.objects.filter(user=request.user, parser_name=parser_name)[0]
    parser_module = importlib.import_module(f'parser.Parser.{parser_name}')
    parser_class = getattr(parser_module, parser_name)
    parser_instance: Core = parser_class(settings_model)
    
    asyncio.run(parser_instance.grab())
    
    if request.method == "POST":       
        return redirect('start')

# @login_required
def status(request):
    return render(request, 'users/pages/status.html')


# @login_required
def grabs(request):
    return render(request, 'users/pages/grabs.html')


# @login_required
def database(request):
    return render(request, 'users/pages/database.html')


# @login_required
def export(request):
    return render(request, 'users/pages/export.html')


# @login_required
def stats(request):
    return render(request, 'users/pages/stats.html')


def fetch_btc_rate():
    response = requests.get('https://blockchain.info/ticker')
    # print(response, response.text)
    return response.json()['EUR']['last']


def fetch_payment_status(bitcoin_address, amount):
    status_data = {
        'paid': False,
        'confirmations': 0,
        'txid': None
    }

    tx_url = f"https://blockstream.info/testnet/api/address/{bitcoin_address}/txs"
    # tx_url = f"https://blockstream.info/testnet/api/address/tb1q0mglz27fmaaw3haevp9exjgl23d603agxu6rs2/txs"
    tx_response = requests.get(tx_url)
    tx = tx_response.json()

    if not tx:
        return JsonResponse(status_data)
    transaction = tx[0]
    funded = transaction['vout'][0]['value']
    funded = amount
    if funded == amount:
        status_data['paid'] = True
        status_data['txid'] = transaction['txid']
        confirmed = transaction['status']['confirmed']
        if confirmed:
            tx_height = transaction['status']['block_height']
            current_height = requests.get('https://blockstream.info/testnet/api/blocks/tip/height').text
            status_data['confirmations'] = int(current_height) - tx_height + 1
    
    return status_data
    

def fetch_payment_status_view(request: HttpRequest):
    bitcoin_address = request.GET['bitcoin_address']
    amount = int(request.GET['amount'])
    
    # logic to return status and confirmation amount   
    status_data = fetch_payment_status(bitcoin_address, amount)
        
    return JsonResponse(status_data, safe=False)


def fetch_btc_rate_view(request):
    eur_amount = request.POST.get('eur-amount')
    btc_rate = fetch_btc_rate()
    
    btc_amount = round(int(eur_amount) / int(btc_rate), 8)
    
    return HttpResponse(btc_amount)


# @login_required
# @csrf_exempt
def generate_bitcoin_address(request):
    
    user = request.user
    
    if request.method == 'POST':
        print(request.POST)
        pass
        btc_amount = request.POST.get('btc-amount')
        eur_amount = request.POST.get('eur-amount')

        # wallet = Wallet('92kmjpRzXQaJeJMcBWDXXLJEyqRVYhAPGxRhvhQ5D4ha2W81WaM', testnet=True)
        # wallet = Wallet('cSkCTzMJuD3zsdbxHMxHitB6hrj6ztGRKRe3e1JqaFL4mB1gqB1j', testnet=True)
        
        wallet = Wallet('92kmjpRzXQaJeJMcBWDXXLJEyqRVYhAPGxRhvhQ5D4ha2W81WaM', testnet=True)
        priv_key = wallet.key.testnet.wif
        bitcoin_address = wallet.address.testnet.pubaddrtb1_P2WPKH
        
        model_data = {
            'user': user,
            'private_key': priv_key,
            'public_address': bitcoin_address,
            'amount': btc_amount,
        }
        
        address_model = BitcoinAddress(**model_data)
        address_model.save()

        context = {
            'btc_amount': btc_amount,
            'bitcoin_address': bitcoin_address,
        }
        return render(request, 'users/components/bitcoin_payment.html', context=context)
    
    return HttpResponse({'error': 'Invalid request'}, status=400)