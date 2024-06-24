import django
django.setup()
from django.utils import timezone
import random
import sys
# import magic
import traceback
import mimetypes
import requests
import httpx
import json
import os
from asgiref.sync import sync_to_async
import asyncio
import time
import math
import yaml
import re
from dataclasses import dataclass
from typing import Tuple, Union, Any
from rich.prompt import Prompt
from rich import print
from concurrent import futures
from concurrent.futures import ThreadPoolExecutor
from rich.progress import (
    TextColumn,
    Progress,
    MofNCompleteColumn,
    SpinnerColumn,
    TimeElapsedColumn,
)
from hashlib import md5
from datetime import datetime, timedelta

from parser.models import ShopwareAccessToken, Image

def randomize_color(hex_color: str, offset: int = 6) -> str:
    while len(hex_color) < 7:
        hex_color += hex_color[-1]
    if '$' in hex_color:
        return hex_color

    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    r_offset, g_offset, b_offset = random.randint(-offset, offset), random.randint(-offset, offset), random.randint(-offset, offset)

    r = min(max(r + r_offset, 0), 255)
    g = min(max(g + g_offset, 0), 255)
    b = min(max(b + b_offset, 0), 255)

    return f"#{r:02x}{g:02x}{b:02x}"


@dataclass
class ConfigData:
    pass


class SW6Shop:

    def __init__(self, target, username=None, password=None):
        self.target = target
        self.shop_data = ConfigData()
        self.sync_url = f'https://{self.target}/api/_action/sync'
        self.username = username
        self.password = password
        
        print('SW6Shop instance initiated')
    
    async def init_sync(self):
        await self.read_shop_data_from_url()
        # self.create_sales_channel_rule()

    def save_shop_data(self):
        with open(f'{self.CACHEDIR}/{self.target}_shop_data.yaml', 'w') as shop_data_file:
            yaml.safe_dump(self.shop_data.__dict__, shop_data_file)

    def read_shop_data_from_file(self):
        from_file = yaml.safe_load(open(f'{self.CACHEDIR}/{self.target}_shop_data.yaml'))
        for key, value in from_file.items():
            setattr(self.shop_data, key, value)
        self.username = self.shop_data.username
        self.password = self.shop_data.password

    async def read_shop_data_from_url(self):
        shop_data = self.shop_data
        shop_data.username = self.username
        shop_data.password = self.password

        # Define the asynchronous tasks as a dictionary
        tasks = {
            'sales_channels': self.read_sales_channels(),
            'cms_layouts': self.generate_admin_request('POST', f'https://{self.target}/api/search/cms-page'),
            'sales_channel_type': self.generate_admin_request('POST', f'https://{self.target}/api/search/sales-channel-type'),
            'languages': self.generate_admin_request('POST', f'https://{self.target}/api/search/language'),
            'customer_group': self.generate_admin_request('POST', f'https://{self.target}/api/search/customer-group'),
            'currency': self.generate_admin_request('POST', f'https://{self.target}/api/search/currency'),
            'payment_method': self.generate_admin_request('POST', f'https://{self.target}/api/search/payment-method'),
            'shipping_method': self.generate_admin_request('POST', f'https://{self.target}/api/search/shipping-method'),
            'countries': self.generate_admin_request('POST', f'https://{self.target}/api/search/country'),
            'root_categories': self.generate_admin_request('POST', f'https://{self.target}/api/search/category'),
            'snippet_sets': self.generate_admin_request('POST', f'https://{self.target}/api/search/snippet-set'),
            'tax': self.generate_admin_request('POST', f'https://{self.target}/api/search/tax'),
            'delivery_time': self.generate_admin_request('POST', f'https://{self.target}/api/search/delivery-time'),
            'locales': self.generate_admin_request('POST', f'https://{self.target}/api/search/locale'),
            'rule': self.generate_admin_request('POST', f'https://{self.target}/api/search/rule'),
            'media_folder': self.generate_admin_request('POST', f'https://{self.target}/api/search/media-folder'),
            'media_default_folder': self.generate_admin_request('POST', f'https://{self.target}/api/search/media-default-folder'),
        }

        # Run the tasks concurrently
        results = await asyncio.gather(*tasks.values())

        # Map the results back to their task names
        results = dict(zip(tasks.keys(), results))

        # Process the results
        shop_data.sales_channels = results['sales_channels']
        shop_data.cms_layouts = results['cms_layouts'].json()['data']
        shop_data.newsletter_page_id = list(filter(lambda x: 'ewsletter' in x['attributes']['name'], shop_data.cms_layouts))[0]['id']
        shop_data.product_cms_page_id = list(filter(lambda x: any(name in x['attributes']['name'] for name in ['Produktseite', 'product']), shop_data.cms_layouts))[0]['id']
        shop_data.category_page_with_sidebar_id = list(filter(lambda x: 'idebar' in x['attributes']['name'], shop_data.cms_layouts))[0]['id']
        shop_data.type_id = list(filter(lambda x: x['attributes']['name'] == 'Storefront', results['sales_channel_type'].json()['data']))[0]['id']
        shop_data.export_type_id = list(filter(lambda x: any(name in x['attributes']['name'] for name in ['Produktvergleich', 'comparison']), results['sales_channel_type'].json()['data']))[0]['id']
        shop_data.storefront_sales_channels = list(filter(lambda x: x['attributes']['typeId'] == shop_data.type_id, shop_data.sales_channels))
        shop_data.tax_id = list(filter(lambda x: x['attributes']['taxRate'] == 19.0, results['tax'].json()['data']))[0]['id']
        locales = {
            item['id']: item['attributes']['code']
            for item in results['locales'].json()['data']
        }
        shop_data.languages = {
            locales[lng['attributes']['localeId']]: lng['id']
            for lng in results['languages'].json()['data']
        }
        shop_data.customer_group_id = results['customer_group'].json()['data'][0]['id']
        shop_data.currencies = {
            item['attributes']['isoCode']: item['id']
            for item in results['currency'].json()['data']
        }
        shop_data.payment_methods = {
            item['attributes']['name']: item['id']
            for item in results['payment_method'].json()['data']
        }
        shop_data.shipping_methods = {
            item['attributes']['name']: item['id']
            for item in results['shipping_method'].json()['data']
        }
        shop_data.countries = {
            item['attributes']['name']: item['id']
            for item in results['countries'].json()['data']
        }
        shop_data.root_category_ids = [
            item['id']
            for item in list(filter(lambda x: x['attributes']['parentId'] is None, results['root_categories'].json()['data']))
        ]
        shop_data.snippet_sets = {
            item['attributes']['name']: item['id']
            for item in results['snippet_sets'].json()['data']
        }
        shop_data.rules = {
            item['attributes']['name']: item['id']
            for item in results['rule'].json()['data']
        }
        shop_data.media_folders = {
            item['attributes']['name']: item['id']
            for item in results['media_folder'].json()['data']
        }
        prd_default_folder_id = [item for item in results['media_default_folder'].json()['data'] if item['attributes']['entity'] == 'product'][0]['id']
        shop_data.product_media_folder_id = [item for item in results['media_folder'].json()['data'] if item['attributes']['defaultFolderId'] == prd_default_folder_id][0]['id']

    async def obtain_access_token(self):
        """
        :return token string if token obtained or False if not
        """
            
        token, created = await ShopwareAccessToken.objects.aget_or_create(pk=self.target)

        if token.valid_until and timezone.now() < token.valid_until:
            return token.token

        response = self.fetch_access_token()
        if response.status_code != 200:
            return False
        response_data = response.json()
        token.token = response_data['access_token']
        token.valid_until = timezone.now() + timedelta(seconds=590)
        await token.asave()

        return token.token        

    def fetch_access_token(self):
        return httpx.post(f'https://{self.target}/api/oauth/token', json={
            'client_id': 'administration',
            'grant_type': 'password',
            'scopes': 'write',
            'username': self.username,
            'password': self.password
        })
    
    async def generate_headers(self, **kwargs):

        headers = {
            # 'Content-Type': 'application/json',
            'Authorization': f'Bearer {await self.obtain_access_token()}',
            'indexing-behavior': 'use-queue-indexing',
            # 'indexing-behavior': 'disable-indexing',
            'single-operation': '1'
        }
        for key, value in kwargs.items():
            headers[key] = value

        return headers

    async def generate_admin_request(self, method, url, payload=None, data=None, headers=None) -> httpx.Response:
        if not payload:
            payload = {}
        if not headers:
            headers = await self.generate_headers()

        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, json=payload, data=data, headers=headers, timeout=10)
            return response

    async def read_sales_channels(self):
        response = await self.generate_admin_request('POST', f'https://{self.target}/api/search/sales-channel')
        return response.json()['data']
    
    def helper_get_blocks(self, name, item):

        blocks = [
            {
                "id": md5(f'{self.target}_{name}_text_block'.encode()).hexdigest(),
                "position": 0,
                "type": "text",
                "sectionPosition": "main",
                "marginTop": "20px",
                "marginBottom": "20px",
                "marginLeft": "20px",
                "marginRight": "20px",
                "backgroundMediaMode": "cover",
                "slots": [
                    {
                        "id": md5(f'{self.target}_{name}_slot'.encode()).hexdigest(),
                        "config": {
                            "content": {
                                "source": "static",
                                "value": "",
                            },
                            "verticalAlign": {
                                "source": "static",
                                "value": None
                            }
                        },
                        "type": "text",
                        'slot': "content",
                        'translations': {
                            language_iso: {
                                'config': {
                                    'content': {
                                        "source": "static",
                                        "value": content,
                                    }
                                }
                            }
                            for language_iso, content in item.items()
                        }
                    }
                ]
            }
        ]

        if 'formular' in name:
            form_id = '3458ec0dbedf45c0a31d39fd00ec67df' if name == 'widerrufsformular' else '3bc758d7befd446f8a9757425115dc35'
            form_block = {
                "id": md5(f'{self.target}_{name}_form_block'.encode()).hexdigest(),
                "position": 1,
                "type": "form",
                "sectionPosition": "main",
                "marginTop": "20px",
                "marginBottom": "20px",
                "marginLeft": "20px",
                "marginRight": "20px",
                "backgroundMediaMode": "cover",
                "slots": [
                    {
                        "id": md5(f'{self.target}_{name}_form_slot'.encode()).hexdigest(),
                        "config": {
                            "type": {
                                "source": "static",
                                "value": "contact"
                            },
                            "title": {
                                "source": "static",
                                "value": ""
                            },
                            "mailReceiver": {
                                "source": "static",
                                "value": []
                            },
                            "defaultMailReceiver": {
                                "source": "static",
                                "value": True
                            },
                            "confirmationText": {
                                "source": "static",
                                "value": ""
                            }
                        },
                        "type": "form",
                        'slot': "content",
                    }
                ]
            }
            blocks += [form_block]

        return blocks

    def get_all_media_with_file(self, **kwargs) -> list:
        all_media = []
        i = 100
        payload = {
            "filter": [
                {
                    "type": "not",
                    "queries": [
                        {
                            "type": "equals",
                            "field": "fileName",
                            "value": None
                        }
                    ]
                },
            ],
            'total-count-mode': 1,
            'page': 1,
            'limit': i
        }

        print(f'[+] getting existing media from {self.target}')
        response = self.generate_admin_request('POST', f'https://{self.target}/api/search/media', payload)
        data = response.json()
        total = data['meta']['total']
        print(f'[+] {total} media found in {self.target}')

        media = data['data']
        all_media.extend(media)
        payload['total-count-mode'] = 0
        pages = total // i + 1

        with Progress(
                MofNCompleteColumn(),
                SpinnerColumn(),
                *Progress.get_default_columns(),
                TimeElapsedColumn(),
        ) as progress:
            progress_task = progress.add_task("[green bold]Reading media...", total=(pages - 1) * i)
            payloads = [
                {
                    "filter": [
                        {
                            "type": "not",
                            "queries": [
                                {
                                    "type": "equals",
                                    "field": "fileName",
                                    "value": None
                                }
                            ]
                        },
                    ],
                    'total-count-mode': 0,
                    'page': page,
                    'limit': i
                }
                for page in range(2, pages + 1)
            ]
            with ThreadPoolExecutor() as ex:
                url = f'https://{self.target}/api/search/media'
                jobs = [
                    ex.submit(
                        self.generate_admin_request,
                        'POST',
                        url,
                        payload
                    )
                    for payload in payloads
                ]

                for future in futures.as_completed(jobs):
                    response = future.result()
                    data = response.json()
                    media = data['data']
                    all_media.extend(media)
                    progress.update(progress_task, advance=i)

        return all_media

    def get_all_products(self, **kwargs) -> list:
        """
        **kwargs: payload=
        """

        all_products = []
        i = 100
        payload = {
            'total-count-mode': 1,
            'page': 1,
            'limit': i,
        }

        print(f'[+] getting existing products from {self.target}')
        response = self.generate_admin_request('POST', f'https://{self.target}/api/search/product', payload)
        data = response.json()
        total = data['meta']['total']
        print(f'[+] {total} products found in {self.target}')

        products = data['data']
        all_products.extend(products)
        payload['total-count-mode'] = 0
        pages = math.ceil(total / i)

        with Progress(
                MofNCompleteColumn(),
                SpinnerColumn(),
                *Progress.get_default_columns(),
                TimeElapsedColumn(),
        ) as progress:
            progress_task = progress.add_task("[green bold]Reading products...", total=(pages - 1) * i)
            payloads = [
                {
                    'total-count-mode': 0,
                    'page': page,
                    'limit': i,
                }
                for page in range(2, pages + 1)
            ]
            with ThreadPoolExecutor() as ex:
                url = f'https://{self.target}/api/search/product'
                jobs = [
                    ex.submit(
                        self.generate_admin_request,
                        'POST',
                        url,
                        payload
                    )
                    for payload in payloads
                ]

                for future in futures.as_completed(jobs):
                    response = future.result()
                    data = response.json()
                    products = data['data']
                    all_products.extend(products)
                    progress.update(progress_task, advance=i)

            # for page in range(2, pages + 1):
            #     payload['page'] = page
            #     response = self.generate_admin_request('POST', f'https://{self.target}/api/search/product', payload)
            #     data = response.json()
            #     products = data['data']
            #     all_products.extend(products)
            #     progress.update(progress_task, advance=i)

        return all_products

    def get_all_product_ids(self) -> list:
        if os.path.exists(f'{self.target} - all product ids.json'):
            all_products = json.loads(open(f'{self.target} - all product ids.json', 'r').read())

        else:

            all_products = []
            i = 100
            payload = {
                'total-count-mode': 1,
                'page': 1,
                'limit': i,
                "includes": {
                    "product": ["id"]
                }
            }

            print(f'[+] getting existing products from {self.target}')
            response = self.generate_admin_request('POST', f'https://{self.target}/api/search/product', payload)
            data = response.json()
            total = data['meta']['total']
            print(f'[+] {total} products found in {self.target}')

            products = data['data']
            all_products.extend(products)
            payload['total-count-mode'] = 0
            pages = math.ceil(total / payload['limit'])

            with Progress(
                    MofNCompleteColumn(),
                    SpinnerColumn(),
                    *Progress.get_default_columns(),
                    TimeElapsedColumn(),
            ) as progress:
                progress_task = progress.add_task("[green bold]Reading product Ids", total=(pages - 1) * i)
                for page in range(2, pages + 1):
                    payload['page'] = page
                    response = self.generate_admin_request('POST', f'https://{self.target}/api/search/product', payload)
                    data = response.json()
                    products = data['data']
                    all_products.extend(products)
                    progress.update(progress_task, advance=i)

            with open(f'{self.target} - all product ids.json', 'w') as product_file:
                product_file.write(json.dumps(all_products))

        return all_products

    def get_all_images(self) -> list:
        all_images = []
        i = 100
        payload = {
            'total-count-mode': 1,
            'page': 1,
            'limit': i,
        }

        print(f'[+] getting existing images from {self.target}')
        response = self.generate_admin_request('POST', f'https://{self.target}/api/search/media', payload)
        data = response.json()
        total = data['meta']['total']
        print(f'[+] {total} images found in {self.target}')

        images = data['data']
        all_images.extend(images)
        payload['total-count-mode'] = 0
        pages = total // payload['limit'] + 1

        payloads = [
            {
                'total-count-mode': 0,
                'page': page,
                'limit': i,
            }
            for page in range(2, pages + 1)
        ]

        with ThreadPoolExecutor() as ex:
            url = f'https://{self.target}/api/search/media'
            jobs = [
                ex.submit(
                    self.generate_admin_request,
                    'POST',
                    url,
                    payload
                )
                for payload in payloads
            ]

            for i, future in enumerate(futures.as_completed(jobs), start=1):
                response = future.result()
                data = response.json()
                images = data['data']
                print(len(images))
                all_images.extend(images)
                print(f'page {i}/{pages} done')

        all_images_ids = [item['id'] for item in all_images]

    def create_sales_channel_rule(self):
        rule_id = md5(f'{self.target}_sales_channel_rule'.encode()).hexdigest()

        payload = {
            "create_sales_channel_rule": {
                "entity": "rule",
                "action": 'upsert',
                "key": "write",
                'payload': [
                    {
                        "id": rule_id,
                        "name": f"sales channel is {self.target}",
                        "priority": 1,
                        "moduleTypes": {
                            "types": [
                                "shipping",
                                "payment",
                                "price",
                                "flow"
                            ]
                        },
                        "conditions": [
                            {
                                'id': md5(f'{rule_id}_1'.encode()).hexdigest(),
                                'type': 'orContainer',
                                'value': {},
                                'position': 0,
                                'children': [
                                    {
                                        'id': md5(f'{rule_id}_2'.encode()).hexdigest(),
                                        'type': 'andContainer',
                                        'value': {},
                                        'position': 0,
                                        'children': [
                                            {
                                                'id': md5(f'{rule_id}_3'.encode()).hexdigest(),
                                                'type': 'salesChannel',
                                                'value': {
                                                    'operator': '=',
                                                    "salesChannelIds": [
                                                        md5(self.target.encode()).hexdigest()
                                                    ]
                                                },
                                                'position': 0,
                                            },
                                        ],
                                    },
                                ],
                            },
                        ],
                    }
                ]
            }
        }
        print('[green][+] Rule created')
        return self.generate_admin_request('POST', self.sync_url, payload)

    def reduce_prices(self, discount_from: int, discount_to: int, ending: int = 95) -> None:
        f = discount_from
        t = discount_to
        s = 1 - ending / 100

        def helper_return_new_price(frm, to, price):
            if frm == to:
                neg_factor = frm / 100
            else:
                neg_factor = (random.randrange(frm, to) / 100)
            new_price = price * (1 - neg_factor)
            return int(new_price) - s

        all_products = self.get_all_products()

        id_price_map = {
            x['id']: {
                'price': x['attributes']['price'][0]['gross'],
                'listprice': x['attributes']['price'][0]['listPrice']['gross'] if x['attributes']['price'][0]['listPrice'] is not None else 0,
            }
            for x in all_products
        }
        currency_id = all_products[0]['attributes']['price'][0]['currencyId']

        payloads = [
            {
                "update_prices": {
                    "entity": "product",
                    "action": 'upsert',
                    'payload': [
                        {
                            'id': uuid,
                            'prices': [
                                {
                                    'id': md5(f'{uuid}_{self.target}_reduced_price'.encode()).hexdigest(),
                                    'price': [
                                        {
                                            'currencyId': currency_id,
                                            'gross': helper_return_new_price(f, t, price['price']),
                                            'net': helper_return_new_price(f, t, price['price']) / 1.19,
                                            'linked': True,
                                            'listPrice':
                                                {
                                                    'currencyId': currency_id,
                                                    'gross': price['listprice'],
                                                    'net': price['listprice'] / 1.19,
                                                    'linked': True
                                                }
                                        }
                                    ],
                                    'ruleId': md5(f'{self.target}_sales_channel_rule'.encode()).hexdigest(),
                                    'quantityStart': 1
                                },
                            ],
                        }
                    ]
                }
            }
            for uuid, price in id_price_map.items()
        ]

        with Progress(
                MofNCompleteColumn(),
                SpinnerColumn(),
                *Progress.get_default_columns(),
                TimeElapsedColumn(),
        ) as progress:
            progress_task = progress.add_task("[green bold]Updating product prices", total=len(payloads))

            with ThreadPoolExecutor() as ex:
                jobs = [
                    ex.submit(
                        self.generate_admin_request,
                        'POST',
                        self.sync_url,
                        payload
                    )
                    for payload in payloads
                ]

                for i, future in enumerate(futures.as_completed(jobs)):
                    response = future.result()
                    if response.status_code != 200:
                        print(response.text)
                    progress.update(progress_task, advance=1)

    def __generate_product_payload__(self, data: dict):
        shop_data = self.shop_data

        with open('product_dict.json', 'w') as fl:
            fl.write(json.dumps(data, indent=4))
        
        source_url = data['source_url']
        full_category = data['category_path']
        product_number = data['product_number']
        sku = str(data['sku'])
        name = data['name'][:255]
        ean = data['ean']
        description = data['html_description']
        description_tail = data['details_description']  # if 'description_tail' in data else ''
        short_description = data['short_description']  # if 'short_description' in data else ''
        manufacturer_number = data['manufacturer_number'][:100] if data['manufacturer_number'] else ''
        manufacturer_name = str(data['manufacturer_name'])
        manufacturer_image_url = data['manufacturer_image']
        strike_price = float(str(data['strike_price']).replace(',', '.'))
        purchase_price = float(str(data['price']).replace(',', '.')) if data['price'] else 0
        energy_class = data['energy_class']  # if 'energy_class' in data else ''
        energy_icon_filename = data['energy_icon_filename']  # if 'energy_icon_filename' in data else ''
        energy_icon_url = data['energy_icon_url']  # if 'energy_icon_filename' in data else ''
        time.sleep(3)
        energy_label_filename = data['energy_label_filename']  # if 'energy_label_filename' in data else ''
        energy_label_url = data['energy_label_url']  # if 'energy_label_filename' in data else ''
        energy_pdf_filename = data['energy_pdf_filename']  # if 'energy_datasheet_filename' in data else ''
        energy_pdf_url = data['energy_pdf_url']  # if 'energy_datasheet_filename' in data else ''
        image_urls = data['image_urls']
        properties = data['properties']
        children = data['children']
        currency = data['currency']

        unit = data['unit']
        purchase_unit = data['purchase_unit']
        reference_unit = data['reference_unit']
        pack_unit = data['pack_unit']
        pack_unit_plural = data['pack_unit_plural']

        product_id = md5(f"{sku}".encode()).hexdigest()
        manufacturer_media_id = md5(manufacturer_image_url.encode()).hexdigest()
        currency_id = shop_data.currencies[currency]
        tax_id = shop_data.tax_id
        product_cms_page_id = shop_data.product_cms_page_id
        category_cms_page_id = shop_data.category_page_with_sidebar_id
        delivery_time_id = md5('1-3'.encode()).hexdigest()

        # image_urls
        product_image_payload_data = [
            {
                'id': md5((product_id + md5(image_url.encode()).hexdigest()).encode()).hexdigest(),
                'media': {
                    'id': md5(image_url.encode()).hexdigest(),
                    'mediaFolderId': shop_data.product_media_folder_id,
                    # 'mediaFolder': {
                    #     'id': md5('API Product Media'.encode()).hexdigest(),
                    #     'name': 'API Product Media',
                    #     'configurationId': '381fbd435a594aafa817a9c207a77f9f',
                    # }
                },
                'position': i,
            } for i, image_url in enumerate(image_urls[:5])
        ]

        # categories
        if len(full_category) > 1:
            product_category_payload_data = {}
            new_level = product_category_payload_data
            for i, category_name in enumerate(full_category[:-1]):
                category_tree = ''.join(full_category[:i + 1])
                child_category_tree = ''.join(full_category[:i + 2])
                new_level['id'] = md5(category_tree.encode()).hexdigest()
                new_level['name'] = full_category[i]
                new_level['cmsPageId'] = category_cms_page_id
                new_level['children'] = [
                    {
                        'name': full_category[i + 1],
                        'cmsPageId': category_cms_page_id,
                        'id': md5(child_category_tree.encode()).hexdigest()
                    }
                ]
                new_level = new_level['children'][0]
        elif len(full_category) == 1:
            product_category_payload_data = {}
            new_level = product_category_payload_data
            category_tree = full_category[0]
            new_level['id'] = md5(category_tree.encode()).hexdigest()
            new_level['name'] = full_category[0]
            new_level['cmsPageId'] = category_cms_page_id

        custom_fields_payload_data = {
            'grab_add_source_url': source_url,
            'grab_add_short_description': short_description,
            'grab_add_description_tail': description_tail,
            'grab_add_energy_class': energy_class,
            'grab_add_energy_icon_filename': energy_icon_filename,
            'grab_add_energy_label_filename': energy_label_filename,
            'grab_add_energy_datasheet_filename': energy_pdf_filename,
            'grab_add_energy_class_file_type_media': md5(energy_icon_url.encode()).hexdigest() if energy_icon_url else None,
            'grab_add_energy_label_file_type_media': md5(energy_label_url.encode()).hexdigest() if energy_label_url else None,
            'grab_add_energy_datasheet_file_type_media': md5(energy_pdf_url.encode()).hexdigest() if energy_pdf_url else None,
        }
        custom_field_sets_payload_data = [
            {
                'name': field_name,
                'id': md5(field_name.encode()).hexdigest(),
                'type': 'html',
                'config': {
                    'componentName': "sw-text-editor",
                    'customFieldPosition': 1,
                    'customFieldType': "textEditor",
                    'label': {'en-GB': field_name}
                }
            }
            for field_name in custom_fields_payload_data
            if 'type_media' not in field_name
        ]
        custom_field_sets_payload_data += [
            {
                'name': field_name,
                'id': md5(field_name.encode()).hexdigest(),
                'type': 'text',
                'config': {
                    'componentName': "sw-media-field",
                    'customFieldPosition': 1,
                    'customFieldType': "media",
                    'label': {'en-GB': field_name}
                }
            }
            for field_name in custom_fields_payload_data
            if 'type_media' in field_name
        ]
        properties_payload_data = [
            {
                'group': {
                    'id': md5(name.encode()).hexdigest(),
                    'name': name
                },
                'id': md5((name + val).encode()).hexdigest(),
                'name': val
            }
            for name, values in properties.items() for val in values
            if val and 0 < len(val) < 255
        ]
        configurator_group_config_payload_data = [
            json.loads(x) for x in set(
                [
                    json.dumps(
                        {
                            'id': md5(option.encode()).hexdigest(),  # groupId
                            'representation': 'box',
                            'expressionForListings': False
                        }
                    ) for child_data in children for option in child_data['options']
                    if option
                ]
            )
        ]
        configurator_settings_payload_data = [
            json.loads(x) for x in set(
                [
                    json.dumps(
                        {
                            'id': md5((data['sku'] + value[:255]).encode()).hexdigest(),
                            'optionId': md5((option + value).encode()).hexdigest()
                        }
                    ) for child_data in children for option, value in child_data['options'].items()
                ]
            )
        ]
        children_payload_data = [
            {
                'name': child_data['name'][:255],
                'id': md5(f"{child_data['sku']}_child".encode()).hexdigest(),
                'price': [
                    {
                        'currencyId': currency_id,
                        'gross': float(str(child_data['price']).replace(',', '.')),
                        'net': float(str(child_data['price']).replace(',', '.')) / 1.19,
                        'linked': True,
                        'listPrice':
                            {
                                'currencyId': currency_id,
                                'gross': float(str(child_data['strike_price']).replace(',', '.')),
                                'net': float(str(child_data['strike_price']).replace(',', '.')) / 1.19,
                                'linked': True
                            }
                    }
                ],
                'productNumber': str(child_data['product_number']),
                'ean': child_data['ean'],
                'manufacturerNumber': child_data['manufacturer_number'][:100],
                'stock': 1000,
                'options': [
                    {
                        'group': {
                            'id': md5(option.encode()).hexdigest(),
                            'name': option[:255],
                        },
                        'id': md5((option + value).encode()).hexdigest(),
                        'name': value[:255],
                    } for option, value in child_data['options'].items()
                    if option and value
                ],
                'properties': properties_payload_data,
                # 'visibilities': [
                #     {
                #         'id': md5((f'{product_id}_{item["id"]}_visibility').encode()).hexdigest(),
                #         'salesChannelId': item["id"],
                #         'visibility': 30
                #     }
                #     for item in shop_data.sales_channels
                # ],
                'customFields': {
                    'grab_add_description_tail': child_data['details_description']},
                'media': [
                    {
                        'id': md5((md5(child_data['product_number'].encode()).hexdigest() + md5(
                            image_url.encode()).hexdigest()).encode()).hexdigest(),
                        'media': {
                            'id': md5(image_url.encode()).hexdigest(),
                            # 'mediaFolder': {
                            #     'name': 'API Product Media',
                            #     'id': md5('API Product Media'.encode()).hexdigest(),
                            #     'configurationId': '381fbd435a594aafa817a9c207a77f9f',
                            # }
                            'mediaFolderId': shop_data.product_media_folder_id
                        },
                        'position': i,
                    } for i, image_url in enumerate(child_data['image_urls'])
                ],
                'cover': {
                    'mediaId': md5(child_data['main_image'].encode()).hexdigest(),
                },
                'categories': [product_category_payload_data],

            } for child_data in children
        ]
        reviews_payload_data = [
            {
                'id': md5(f"{sku}_review_{i}".encode()).hexdigest(),
                'salesChannelId': shop_data.storefront_sales_channels[0]['id'],
                'languageId': shop_data.languages['de-DE'],
                'status': True,
                'title': rev['title'] if rev['title'] else 'Kein Betreff',
                'content': rev['content'] if rev['content'] else 'Alles super',
                'points': rev['points'],
                'createdAt': rev['time'],
            }
            for i, rev in enumerate(data['reviews'])

        ]
        tags_payload_data = [
            {
                'id': md5(tag_name.encode()).hexdigest(),
                'name': tag_name
            }
            for tag_name in data['shipping_tags']
        ]

        product_payload = {
            'children': children_payload_data,
            'configuratorSettings': configurator_settings_payload_data,
            'configuratorGroupConfig': configurator_group_config_payload_data,
            'taxId': tax_id,
            'stock': 1000,
            'id': product_id,
            'productNumber': str(product_number),
            'price': [
                {
                    'currencyId': currency_id,
                    'gross': purchase_price,
                    'net': purchase_price / 1.19,
                    'linked': True,
                    'listPrice':
                        {
                            'currencyId': currency_id,
                            'gross': strike_price,
                            'net': strike_price / 1.19,
                            'linked': True
                        }
                }
            ],
            'name': name,
            'properties': properties_payload_data,
            'customFieldSets': [
                {
                    'name': 'additional_product_data',
                    'id': md5('additional_product_data'.encode()).hexdigest(),
                    'relations': [
                        {
                            'id': md5(
                                f'customFieldSetsProductRelationsadditional_product_data'.encode()).hexdigest(),
                            'entityName': "product"
                        }
                    ],
                    'customFields': custom_field_sets_payload_data
                },
            ],
            'customFields': custom_fields_payload_data,
            'cmsPageId': product_cms_page_id,
            'visibilities': [
                {
                    'id': md5((f'{product_id}_{item["id"]}_visibility').encode()).hexdigest(),
                    'salesChannelId': item["id"],
                    'visibility': 30
                }
                for item in shop_data.sales_channels
            ],
            'ean': ean,
            'deliveryTimeId': delivery_time_id,
            'manufacturerNumber': manufacturer_number,
            'description': description,
            'manufacturer': {
                'name': manufacturer_name,
                'id': md5(manufacturer_name.encode()).hexdigest(),
                'media': {
                    'id': manufacturer_media_id,
                    'mediaFolder':
                        {
                            'id': md5('API Manufacurer Media'.encode()).hexdigest(),
                            'name': 'API Manufacurer Media',
                            'configurationId': '381fbd435a594aafa817a9c207a77f9f',
                        }
                }
            },
            'media': product_image_payload_data,
            'coverId': product_image_payload_data[0]['id'] if product_image_payload_data else None,
            'categories': [product_category_payload_data],
            'productReviews': reviews_payload_data,
            'tags': tags_payload_data,
        }

        return product_payload

    async def create_products(self, product_data: dict) -> (list, list, httpx.Response):
        """
        create a product with shopware 6 API

        datas is a list of dicts containing payload data
        dict is a data container
        use like:
        for data in datas:

            :data is a dict with the following keys:
                :category: []  # list of categories
                :product_number: ''
                :ean: ''
                :manufacturer_number: ''  # MPN
                :strike_price: ''
                :purchase_price: ''
                :description_html: ''  # main description text
                :description_tail: ''  # main description text, 2nd part
                :short_description: ''  # main short_description text
                :properties: {propery_name: property_value}  # grouping property groups in subgroups TODO
                :manufacturer: ''  # or brand, supplier...
                :manufacturer_image_url: ''
                :name: '' # (or title)
                :children: []  # (['child_data'] list of children-dicts with the following keys:
                    :product_number: ''
                    :ean: ''
                    :manufacturer_number: ''  # MPN
                    :name: ''
                    :description_html: ''  # if child product has its own description
                    :description_tail: ''  # if child product has its own description
                    :strike_price: ''
                    :purchase_price: ''
                    :options: {key:value, key2:value2}  # dict represents key:value pairs for options, e.g. color:red, size:M
                    :image_urls: []  # list of child_image urls

        TODO: check existing products to avoid unnessecery overwriting (not within controller, but within grab main()
        TODO: grouping property groups in subgroups
        TODO: develop property handling and "wesentliche Merkmale" handling
        TODO: add better docstring lol
        """
        shop_data = self.shop_data

        product_payload = self.__generate_product_payload__(product_data)

        energy_media_data = [
            {
                'id': md5(str(url).encode()).hexdigest(),
                'mediaFolder': {
                    'id': md5('ENERGY'.encode()).hexdigest(),
                    'name': 'ENERGY',
                    'configurationId': '381fbd435a594aafa817a9c207a77f9f',
                }
            }
            for url in [
                product_data['energy_icon_url'],
                product_data['energy_label_url'],
                product_data['energy_pdf_url']
            ]
        ]

        payload = {
            "create_product": {
                "entity": "product",
                "action": 'upsert',
                'payload': [product_payload]
            },
            "create_energy_media": {
                "entity": "media",
                "action": 'upsert',
                'payload': energy_media_data
            }
        }

        status = None
        while status != 200:
            response = await self.generate_admin_request('POST', self.sync_url, payload)
            status = response.status_code
            if status not in [200, 204]:
                print(response.status_code, response.text, str(product_data['sku']))
                time.sleep(5)
            else:
                pass
                # print('product uploaded')

        print('before return')
        
        return [str(product_data['sku'])], [product_data['source_url']], response

    def patch_product(self, data) -> requests.Response:
        payload = self.__generate_product_payload__(data)
        uuid = payload['id']
        url = f'https://{self.target}/api/product/id/{uuid}'
        return self.generate_admin_request('PATCH', url, payload)

    async def upload_media(self, url, filename, file_bytes=False, ext='webp', media=None) -> (httpx.Response, 'media'):
        uuid = md5(url.encode()).hexdigest()
        if file_bytes:
            headers = {
                # 'authority': 'i.otto.de',
                # 'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                # 'accept-language': 'en-US,en;q=0.9',
                # 'cache-control': 'no-cache',
                # 'pragma': 'no-cache',
                # 'sec-ch-ua': '"Chromium";v="110", "Not A(Brand";v="24", "Brave";v="110"',
                # 'sec-ch-ua-mobile': '?0',
                # 'sec-ch-ua-platform': '"Linux"',
                # 'sec-fetch-dest': 'document',
                # 'sec-fetch-mode': 'navigate',
                # 'sec-fetch-site': 'none',
                # 'sec-fetch-user': '?1',
                # 'sec-gpc': '1',
                # 'upgrade-insecure-requests': '1',
                'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
            }
            
            async with httpx.AsyncClient() as client:
                img_resp = await client.get(url, headers=headers)
                content_type = magic.Magic(mime=True).from_buffer(img_resp.content)
                ext = content_type.split('/')[1]
                data = img_resp.content

                if 'svg' in content_type:
                    content_type = 'image/png'
                    ext = 'png'
                    media_file_bytes = svg2png(bytestring=img_resp.text, parent_width=300, parent_height=150)
                    with open('test.png', 'wb') as ffb:
                        ffb.write(media_file_bytes)
                    data = media_file_bytes

                headers = self.generate_headers(**{'accept': 'application/vnd.api+json'})
                payload = {}
            
        else:
            headers = {}
            data = None
            payload = {
                'url': url
            }

        kwargs = {
            'data': data,
            'headers': headers,
            'payload': payload
        }

        query = f'?extension={ext}&fileName={filename}'

        status_code = 0
        while status_code not in [200, 204]:

            response = await self.generate_admin_request(
                'POST',
                f'https://{self.target}/api/_action/media/{uuid}/upload{query}',
                **kwargs
            )
            # status_code = response.status_code
            status_code = 200
            if status_code not in [200, 204]:

                error_message = response.json()['errors'][0]['code']
                print(response.text)
                print(error_message)

                await asyncio.sleep(10)

        if media:
            return response, media
        else:
            return response

    def upload_product_images(self, product_number, image_urls):

        responses = []

        with ThreadPoolExecutor(max_workers=10) as ex:
            jobs = [
                ex.submit(
                    self.upload_media,
                    f'{md5(product_number.encode()).hexdigest()}_product_image_{i + 1}',
                    url,
                )
                for i, url in enumerate(image_urls)
            ]

        return image_urls

    def delete_all_products(self) -> None:
        all_products = self.get_all_product_ids()

        all_ids = [{
                       "id": x['id']} for x in all_products]
        i = 100
        chunks = [all_ids[x:x + i] for x in range(0, len(all_ids), i)]

        # with ThreadPoolExecutor() as executor:
        #     with Progress() as progress:
        #         progress_task = progress.add_task("[red bold]Deleting products...", total=len(all_ids))
        #
        #         tasks = [
        #             executor.submit(
        #                 self.generate_admin_request,
        #                 'DELETE',
        #                 f'https://{self.target}/api/product/{id}')
        #             for id in all_ids
        #         ]
        #
        #         [progress.update(progress_task, advance=1) for _ in futures.as_completed(tasks)]
        with Progress(
                MofNCompleteColumn(),
                SpinnerColumn(),
                *Progress.get_default_columns(),
                TimeElapsedColumn(),
        ) as progress:
            progress_task = progress.add_task("[red bold]Deleting products", total=len(chunks))
            for batch in chunks:
                payload = {
                    'delete_products': {
                        "action": "delete",
                        "entity": "product",
                        "payload": batch,
                    },
                }
                response = self.generate_admin_request('POST', self.sync_url, payload)
                if response.status_code != 200:
                    print(response)
                progress.update(progress_task, advance=1)

    def delete_product_images(self):
        url = f'https://{self.target}/api/search/media'
        payload = {
            # "page": 1,
            # "limit": 25,
            "filter": [
                {
                    "type": "equals",
                    "field": "mediaFolderId",
                    "value": md5('API Product Media'.encode()).hexdigest()
                }
            ],
            "total-count-mode": 1
        }

        response = self.generate_admin_request('POST', url, payload)
        result = response.json()['data']

        product_image_uuids = [
            img['id']
            for img in result
        ]

        delete_payload = {
            'delete_images': {
                "entity": "media",
                "action": 'delete',
                'payload': [
                    {
                        'id': uuid
                    }
                    for uuid in product_image_uuids
                ]
            }
        }

        return self.generate_admin_request('POST', self.sync_url, delete_payload)

    #########

    def __install_single_plugin__(self, plugin_name: str) -> tuple[requests.Response]:
        install_app_response = self.generate_admin_request('POST', f'https://{self.target}/api/_action/extension/install/app/{plugin_name}')
        activate_app_response = self.generate_admin_request('PUT', f'https://{self.target}/api/_action/extension/activate/app/{plugin_name}')
        install_plugin_response = self.generate_admin_request('POST', f'https://{self.target}/api/_action/extension/install/plugin/{plugin_name}')
        activate_plugin_response = self.generate_admin_request('PUT', f'https://{self.target}/api/_action/extension/activate/plugin/{plugin_name}')

        return install_app_response, activate_app_response, install_plugin_response, activate_plugin_response

    def __install_swstore__(self) -> tuple[requests.Response]:
        return (self.generate_admin_request('POST', f'https://{self.target}/api/_action/extension/download/SwagExtensionStore'),
                self.generate_admin_request('POST', f'https://{self.target}/api/_action/extension/install/plugin/SwagExtensionStore'),
                self.generate_admin_request('PUT', f'https://{self.target}/api/_action/extension/activate/plugin/SwagExtensionStore'))

    def __install_stripe__(self) -> tuple[requests.Response]:
        return (self.generate_admin_request('POST', f'https://{self.target}/api/_action/extension/download/StripeShopwarePayment'),
                self.generate_admin_request('POST', f'https://{self.target}/api/_action/extension/install/plugin/StripeShopwarePayment'),
                self.generate_admin_request('PUT', f'https://{self.target}/api/_action/extension/activate/plugin/StripeShopwarePayment'))

    def install_and_activate_plugins(self) -> list[requests.Response]:
        with ThreadPoolExecutor() as ex:
            jobs = [
                ex.submit(self.__install_swstore__),
                # ex.submit(self.__install_stripe__)
            ]

        self.generate_admin_request('POST', f'https://{self.target}/api/_action/store/frw/finish')

        return [r.result() for r in jobs]

    def delete_old_sales_channels(self):

        sales_channels_ids = [uuid['id'] for uuid in self.shop_data.sales_channels]

        with ThreadPoolExecutor() as ex:
            jobs = [
                ex.submit(
                    self.generate_admin_request,
                    'DELETE',
                    f'https://{self.target}/api/sales-channel/{uuid}'
                )
                for uuid in sales_channels_ids
            ]

            responses = [f.result() for f in futures.as_completed(jobs)]

        self.shop_data.sales_channels.clear()
        self.shop_data.storefront_sales_channels.clear()
        self.save_shop_data()

        return responses

    def delete_old_legal_categories(self):

        uuid = md5('LEGAL'.encode()).hexdigest()
        return self.generate_admin_request('DELETE', f'https://{self.target}/api/category/{uuid}')

    def delete_old_legal_cms_layouts(self, keywords):
        to_delete_cms_layout_ids = [
            layout['id']
            for layout in self.shop_data.cms_layouts
            if any(pattern in layout['attributes']['name'] for pattern in keywords)
        ]

        with ThreadPoolExecutor() as ex:
            jobs = [
                ex.submit(
                    self.generate_admin_request,
                    'DELETE',
                    f'https://{self.target}/api/cms-page/{uuid}'
                )
                for uuid in to_delete_cms_layout_ids
            ]

            responses = [f.result() for f in futures.as_completed(jobs)]

        response = self.generate_admin_request('POST', f'https://{self.target}/api/search/cms-page')

        return responses

    def delete_old_shipping_methods(self):
        shipping_method_ids = [uuid for uuid in self.shop_data.shipping_methods.values()]

        with ThreadPoolExecutor() as ex:
            jobs = [
                ex.submit(
                    self.generate_admin_request,
                    'DELETE',
                    f'https://{self.target}/api/shipping-method/{uuid}'
                )
                for uuid in shipping_method_ids
            ]

            responses = [f.result() for f in futures.as_completed(jobs)]

        return responses

    def delete_old_payment_methods(self):
        payment_method_ids = [
            uuid for name, uuid in self.shop_data.payment_methods.items()
            if 'via Stripe' not in name
        ]

        with ThreadPoolExecutor() as ex:
            jobs = [
                ex.submit(
                    self.generate_admin_request,
                    'DELETE',
                    f'https://{self.target}/api/payment-method/{uuid}'
                )
                for uuid in payment_method_ids
            ]

            responses = [f.result() for f in futures.as_completed(jobs)]

        return responses

    def delete_old_delivery_times(self):
        delivery_times = [
            dt['id']
            for dt in self.generate_admin_request(
                'POST', f'https://{self.target}/api/search/delivery-time'
            ).json()['data']
        ]

        payload = {
            'delete_delivery_times': {
                'entity': 'delivery_time',
                'action': 'delete',
                'payload': [
                    {
                        'id': uuid
                    }
                    for uuid in delivery_times
                ]
            }
        }

        response = self.generate_admin_request('POST', self.sync_url, payload)

    def deactivate_flows(self):
        flows = self.generate_admin_request()

    def randomize_number_ranges(self):
        ranges = self.generate_admin_request('POST', f'https://{self.target}/api/search/number-range').json()['data']
        order_nr_id = [item['id'] for item in ranges if item['attributes']['name'] == 'Bestellungen'][0]
        customer_nr_id = [item['id'] for item in ranges if item['attributes']['name'] == 'Kunden'][0]
        invoice_nr_id = [item['id'] for item in ranges if item['attributes']['name'] == 'Rechnungen'][0]

        payloads = [
            {
                'id': order_nr_id,
                'pattern': "BE{n}",
                'start': random.randrange(20000, 9999999)
            },
            {
                'id': customer_nr_id,
                'pattern': "K{n}",
                'start': random.randrange(20000, 9999999)
            },
            {
                'id': invoice_nr_id,
                'pattern': "RE{n}",
                'start': random.randrange(20000, 9999999)
            },
        ]

        payload = {
            'update_number_ranges': {
                "entity": "number_range",
                "action": 'upsert',
                'payload': payloads
            }
        }

        return self.generate_admin_request('POST', self.sync_url, payload)

    def create_custom_css(self, inactive: list, css_data: dict):

        payloads = [
            {
                'id': md5(name.encode()).hexdigest(),
                'name': name,
                'active': True,
                'css': content
            }
            for name, content in css_data.items()
        ]
        payload = {
            "create_css": {
                "entity": "dne_custom_js_css",
                "action": 'upsert',
                'payload': payloads
            }
        }

        return self.generate_admin_request('POST', self.sync_url, payload)

    def create_custom_js(self, inactive: list, js_data: dict):

        payloads = [
            {
                'id': md5(name.encode()).hexdigest(),
                'name': name,
                'active': True,
                'js': content
            }
            for name, content in js_data.items()
        ]
        payload = {
            "create_js": {
                "entity": "dne_custom_js_css",
                "action": 'upsert',
                'payload': payloads
            }
        }

        return self.generate_admin_request('POST', self.sync_url, payload)

    def create_custom_templates(self, twig_data: dict, doc_twig_data: dict):

        payloads = [
            {
                'path': path.__str__(),
                'content': content
            }
            for path, content in twig_data.items()
        ]
        doc_payloads = [
            {
                'path': path,
                'content': content,
                'documents': True,
            }
            for path, content in doc_twig_data.items()
        ]

        url = f'https://{self.target}/api/_action/dne-templatemanager/save'

        with ThreadPoolExecutor() as ex:
            jobs = [
                ex.submit(self.generate_admin_request, 'POST', url, pl)
                for pl in payloads + doc_payloads
            ]
            responses = [future.result() for future in futures.as_completed(jobs)]

        return responses

    def create_cms_layouts(self, sites_contents: dict):

        payloads = [
            {
                'id': md5(f'{self.target}_{name}_page'.encode()).hexdigest(),
                'name': f'{self.target}_{name}',
                'type': 'page',
                'sections': [
                    {
                        'id': md5(f'{self.target}_{name}_section'.encode()).hexdigest(),
                        'sizingMode': "boxed",
                        'type': "default",
                        'position': 0,
                        'blocks': self.helper_get_blocks(name, item)
                    }
                ]
            }
            for name, item in sites_contents.items()
        ]

        payload = {
            "create_cms_pages": {
                "entity": "cms_page",
                "action": 'upsert',
                'payload': payloads
            }
        }

        response = self.generate_admin_request('POST', self.sync_url, payload)

        return response

    def create_dummy_cms_layout(self):
        
        payloads = [
            {
                'id': md5(f'{self.target}_homepage'.encode()).hexdigest(),
                'name': f'{self.target} Homepage',
                'type': 'landingpage',
                'sections': [
                    {
                        'id': md5(f'{self.target}_homepage_section_0'.encode()).hexdigest(),
                        'sizingMode': "boxed",
                        'type': "default",
                        'position': 0,
                        'blocks': [
                            {
                                "id": md5(f'{self.target}_homepage_section_0_block_0'.encode()).hexdigest(),
                                "position": 0,
                                "type": "image",
                                "sectionPosition": "main",
                                "marginTop": "20px",
                                "marginBottom": "20px",
                                "marginLeft": "20px",
                                "marginRight": "20px",
                                "backgroundMediaMode": "cover",
                                "visibility": {
                                    "mobile": True,
                                    "tablet": True,
                                    "desktop": True
                                },
                                "slots": [
                                    {
                                        "id": md5(f'{self.target}_homepage_section_0_block_0_slot_0'.encode()).hexdigest(),
                                        "type": "image",
                                        "slot": "image",
                                        "config": {
                                            "media": {
                                                "source": "default",
                                                "value": "framework/assets/default/cms/preview_mountain_large.jpg"
                                            },
                                            "displayMode": {
                                                "source": "static",
                                                "value": "standard"
                                            },
                                            "url": {
                                                "source": "static",
                                                "value": None
                                            },
                                            "newTab": {
                                                "source": "static",
                                                "value": False
                                            },
                                            "minHeight": {
                                                "source": "static",
                                                "value": "340px"
                                            },
                                            "verticalAlign": {
                                                "source": "static",
                                                "value": None
                                            }
                                        },
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'id': md5(f'{self.target}_homepage_section_1'.encode()).hexdigest(),
                        'sizingMode': "boxed",
                        'type': "default",
                        'position': 1,
                        'blocks': [
                            {
                                "id": md5(f'{self.target}_homepage_section_1_block_0'.encode()).hexdigest(),
                                "position": 0,
                                "type": "text",
                                "sectionPosition": "main",
                                "marginTop": "20px",
                                "marginBottom": "20px",
                                "marginLeft": "20px",
                                "marginRight": "20px",
                                "backgroundMediaMode": "cover",
                                "visibility": {
                                    "mobile": True,
                                    "tablet": True,
                                    "desktop": True
                                },
                                "slots": [
                                    {
                                        "id": md5(f'{self.target}_homepage_section_1_block_0_slot_0'.encode()).hexdigest(),
                                        "type": "text",
                                        "slot": "content",
                                        "config": {
                                            "content": {
                                                "source": "static",
                                                "value": "About us headline"
                                            },
                                            "verticalAlign": {
                                                "source": "static",
                                                "value": None
                                            }
                                        },
                                    }
                                ]
                            },
                            {
                                "id": md5(f'{self.target}_homepage_section_1_block_1'.encode()).hexdigest(),
                                "position": 1,
                                "type": "text",
                                "sectionPosition": "main",
                                "marginTop": "20px",
                                "marginBottom": "20px",
                                "marginLeft": "20px",
                                "marginRight": "20px",
                                "backgroundMediaMode": "cover",
                                "visibility": {
                                    "mobile": True,
                                    "tablet": True,
                                    "desktop": True
                                },
                                "slots": [
                                    {
                                        "id": md5(f'{self.target}_homepage_section_1_block_1_slot_0'.encode()).hexdigest(),
                                        "type": "text",
                                        "slot": "content",
                                        "config": {
                                            "content": {
                                                "source": "static",
                                                "value": "About us content"
                                            },
                                            "verticalAlign": {
                                                "source": "static",
                                                "value": None
                                            }
                                        },
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'id': md5(f'{self.target}_homepage_section_2'.encode()).hexdigest(),
                        'sizingMode': "boxed",
                        'type': "default",
                        'position': 2,
                        'blocks': []
                    },
                    {
                        'id': md5(f'{self.target}_homepage_section_3'.encode()).hexdigest(),
                        'sizingMode': "boxed",
                        'type': "default",
                        'position': 3,
                        'blocks': [
                            {
                                "id": md5(f'{self.target}_homepage_section_3_block_0'.encode()).hexdigest(),
                                "position": 0,
                                "type": "text",
                                "sectionPosition": "main",
                                "marginTop": "20px",
                                "marginBottom": "20px",
                                "marginLeft": "20px",
                                "marginRight": "20px",
                                "backgroundMediaMode": "cover",
                                "visibility": {
                                    "mobile": True,
                                    "tablet": True,
                                    "desktop": True
                                },
                                "slots": [
                                    {
                                        "id": md5(f'{self.target}_homepage_section_3_block_0_slot_0'.encode()).hexdigest(),
                                        "type": "text",
                                        "slot": "content",
                                        "config": {
                                            "content": {
                                                "source": "static",
                                                "value": "Features"
                                            },
                                            "verticalAlign": {
                                                "source": "static",
                                                "value": None
                                            }
                                        },
                                    }
                                ]
                            },
                        ]
                    },
                ]
            }
        ]

        payload = {
            "create_cms_pages": {
                "entity": "cms_page",
                "action": 'upsert',
                'payload': payloads
            }
        }

        response = self.generate_admin_request('POST', self.sync_url, payload)

        return response

    def create_legal_categories(self, name_map: dict, parent_category_name_map: dict) -> requests.Response:

        shop_data = self.shop_data

        footer_info_categories = [
            'datenschutz',
            'agb',
            'impressum',
            # 'altgerate',
            'widerrufsbelehrung',
            'ruckgabe_erstattungsrichtlinie',
            'versand',
            'abrechnungsbedingungen'
        ]
        footer_support_categories = [
            'widerrufsformular',
            'cookies',
            'kontaktformular',
            'newsletter',
            # 'garantie',
            # 'faq',
            # 'defekt',
            'zahlung',
        ]
        service_categories = [
            'impressum',
            'datenschutz',
            'agb',
            'widerrufsbelehrung',
            'zahlung',
            'versand',
        ]

        payload = {
            "create_categories": {
                "entity": "category",
                "action": 'upsert',
                'payload': [
                    {
                        'id': md5('LEGAL'.encode()).hexdigest(),
                        'name': 'LEGAL',
                        'type': 'folder',
                        'children': [
                            {
                                'id': md5(f'{self.target}_LEGAL'.encode()).hexdigest(),
                                'name': f'{self.target} LEGAL',
                                'type': 'folder',
                                'visible': True,
                                'children': [
                                    {
                                        'id': md5(f'{self.target}_footer'.encode()).hexdigest(),
                                        'name': f'{self.target}_footer',
                                        'type': 'folder',
                                        'visible': True,
                                        'children': [
                                            {
                                                'id': md5(f'{self.target}_info'.encode()).hexdigest(),
                                                'name': "Informationen",
                                                'type': 'folder',
                                                'visible': True,
                                                'children': [
                                                    {
                                                        'id': md5(f'{self.target}_footer_info_{name}'.encode()).hexdigest(),
                                                        'name': name,
                                                        'type': 'page',
                                                        'visible': True,
                                                        'cmsPageId': md5(f'{self.target}_{name}_page'.encode()).hexdigest(),
                                                        "translations": {
                                                            lang_iso: {
                                                                "name": translated_name
                                                            }
                                                            for lang_iso, translated_name in item.items()
                                                        }
                                                    }
                                                    for name, item in name_map.items()
                                                    if name in footer_info_categories
                                                ],
                                                'translations': {
                                                    lang_iso: {
                                                        'name': translated_name
                                                    }
                                                    for lang_iso, translated_name
                                                    in parent_category_name_map['Informationen'].items()
                                                }
                                            },
                                            {
                                                'id': md5(f'{self.target}_support'.encode()).hexdigest(),
                                                'name': "Support",
                                                'type': 'folder',
                                                'visible': True,
                                                'children': [
                                                                {
                                                                    'id': md5(f'{self.target}_footer_support_{name}'.encode()).hexdigest(),
                                                                    'name': name,
                                                                    'type': 'page',
                                                                    'visible': True,
                                                                    'cmsPageId': md5(f'{self.target}_{name}_page'.encode()).hexdigest(),
                                                                    "translations": {
                                                                        lang_iso: {
                                                                            "name": translated_name
                                                                        }
                                                                        for lang_iso, translated_name in item.items()
                                                                    }
                                                                }
                                                                for name, item in name_map.items()
                                                                if name in footer_support_categories
                                                            ] + [
                                                                {
                                                                    'id': md5(f'{self.target}_footer_support_cookies'.encode()).hexdigest(),
                                                                    'name': "Cookie Einstellungen",
                                                                    'type': 'link',
                                                                    'linkType': "external",
                                                                    'visible': True,
                                                                    "externalLink": "/cookie/offcanvas",
                                                                    'translations': {
                                                                        lang_iso: {
                                                                            'name': translated_name}
                                                                        for lang_iso, translated_name
                                                                        in parent_category_name_map['Cookie Einstellungen'].items()
                                                                    }
                                                                },
                                                                {
                                                                    'id': md5(f'{self.target}_footer_support_newsletter'.encode()).hexdigest(),
                                                                    'name': 'Newsletter',
                                                                    'type': 'page',
                                                                    'visible': True,
                                                                    'cmsPageId': shop_data.newsletter_page_id
                                                                }
                                                            ],
                                                'translations': {
                                                    lang_iso: {
                                                        'name': translated_name}
                                                    for lang_iso, translated_name
                                                    in parent_category_name_map['Support'].items()
                                                }
                                            }
                                        ]
                                    },
                                    {
                                        'id': md5(f'{self.target}_service'.encode()).hexdigest(),
                                        'name': 'Service',
                                        'type': 'folder',
                                        'visible': True,
                                        'children': [
                                            {
                                                'id': md5(f'{self.target}_service_{name}'.encode()).hexdigest(),
                                                'name': name,
                                                'type': 'page',
                                                'cmsPageId': md5(f'{self.target}_{name}_page'.encode()).hexdigest(),
                                                "translations": {
                                                    lang_iso: {
                                                        "name": translated_name
                                                    }
                                                    for lang_iso, translated_name in item.items()
                                                }
                                            }
                                            for name, item in name_map.items()
                                            if name in service_categories
                                        ],
                                        'translations': {
                                            lang_iso: {
                                                'name': translated_name
                                            }
                                            for lang_iso, translated_name in
                                            parent_category_name_map['Service'].items()
                                        }
                                    },
                                ]
                            },
                        ],
                        'visible': True
                    }
                ]
            }
        }
        # r= self.generate_admin_request('POST', self.sync_url, payload).json()
        return self.generate_admin_request('POST', self.sync_url, payload)

    def create_snippet_set(self, language_iso):

        snipeet_set_payload = {
            "id": md5(f'{self.target}_{language_iso}_snippet_set'.encode()).hexdigest(),
            "name": f'{self.target}_{language_iso}_snippet_set',
            "baseFile": f"messages.{language_iso}",
            "iso": language_iso
        }

        payload = {
            "create_categories": {
                "entity": "snippet_set",
                "action": 'upsert',
                'payload': [snipeet_set_payload]
            }
        }

        return self.generate_admin_request('POST', self.sync_url, payload)

    def edit_snippets(self, snippets_contents: dict, language_iso: str) -> requests.Response:

        set_id = md5(f'{self.target}_{language_iso}_snippet_set'.encode()).hexdigest()

        with ThreadPoolExecutor() as ex:
            url = f'https://{self.target}/api/_action/snippet-set'
            jobs = {
                ex.submit(self.generate_admin_request, 'POST', url, {
                    'filters': {
                        'term': name}}): {
                    'name': name,
                    'content': content['content']
                }
                for name, content in snippets_contents.items()
            }

            update_jobs = []
            payloads = []
            for future in futures.as_completed(jobs):
                name = jobs[future]['name']
                content = jobs[future]['content']
                result = future.result().json()
                snippets = result['data'][jobs[future]['name']] if result['data'] else None
                method = 'POST'
                snippet_id = list(filter(lambda x: x['setId'] == set_id, snippets))[0]['id'] if snippets else None
                method = 'PATCH' if snippet_id else 'POST'
                payload = {
                    'author': 'user',
                    'id': snippet_id,
                    'setId': set_id,
                    'translationKey': name,
                    'value': content,
                }
                payloads.append(payload)
                url = f'https://{self.target}/api/snippet' if method == 'POST' else f'https://{self.target}/api/snippet/{snippet_id}'
                update_jobs_data = {
                    'method': method,
                    'payload': payload,
                    'url': url
                }
                update_jobs.append(update_jobs_data)

        payload = {
            'edit_snippets': {
                "entity": "snippet",
                "action": 'upsert',
                'payload': payloads
            }
        }

        response = self.generate_admin_request('POST', self.sync_url, payload)

        # responses = []
        # with ThreadPoolExecutor() as ex:
        #     jobs = [
        #         ex.submit(
        #             self.generate_admin_request,
        #             item['method'],
        #             item['url'],
        #             item['payload']
        #         )
        #         for item in update_jobs
        #     ]
        #
        #     for future in futures.as_completed(jobs):
        #         response = future.result()
        #         responses.append(response)

        return response

    def create_rules(self):

        never_available_rule = {
            "id": md5('api never available'.encode()).hexdigest(),
            "name": f"api never available",
            "priority": 1,
            "moduleTypes": {
                "types": [
                    "shipping",
                    "payment",
                    "price",
                    "flow"
                ]
            },
            "conditions": [
                {
                    'id': md5('api never available 1'.encode()).hexdigest(),
                    'type': 'orContainer',
                    'value': {},
                    'position': 0,
                    'children': [
                        {
                            'id': md5('api never available 2'.encode()).hexdigest(),
                            'type': 'andContainer',
                            'value': {},
                            'position': 0,
                            'children': [
                                {
                                    'id': md5('api never available 3'.encode()).hexdigest(),
                                    'type': 'dateRange',
                                    "value": {
                                        "useTime": False,
                                        "fromDate": "2000-05-01T00:00:00+00:00",
                                        "toDate": "2001-10-01T00:00:00+00:00"
                                    },
                                    'position': 0,
                                },
                            ],
                        },
                    ],
                },
            ],
        }
        spedition_shipping_rule = {
            "id": md5('api spedition rule'.encode()).hexdigest(),
            "name": f"api spedition rule",
            "priority": 1,
            "moduleTypes": {
                "types": [
                    "shipping",
                    "payment",
                    "price",
                    "flow"
                ]
            },
            "conditions": [
                {
                    'id': md5('api spedition rule'.encode()).hexdigest(),
                    'type': 'orContainer',
                    'value': {},
                    'position': 0,
                    'children': [
                        {
                            'id': md5('api spedition rule 2'.encode()).hexdigest(),
                            'type': 'andContainer',
                            'value': {},
                            'position': 0,
                            'children': [
                                {
                                    "id": md5('api spedition rule 3'.encode()).hexdigest(),
                                    "type": "cartLineItemTag",
                                    "value": {
                                        "operator": "=",
                                        "identifiers": [
                                            md5('SPEDITION'.encode()).hexdigest()
                                        ]
                                    },
                                    "position": 0
                                },
                            ],
                        },
                    ],
                },
            ],
        }
        standard_shipping_rule = {
            "id": md5('api standard rule'.encode()).hexdigest(),
            "name": f"api standard rule",
            "priority": 1,
            "moduleTypes": {
                "types": [
                    "shipping",
                    "payment",
                    "price",
                    "flow"
                ]
            },
            "conditions": [
                {
                    'id': md5('api standard rule'.encode()).hexdigest(),
                    'type': 'orContainer',
                    'value': {},
                    'position': 0,
                    'children': [
                        {
                            'id': md5('api standard rule 2'.encode()).hexdigest(),
                            'type': 'andContainer',
                            'value': {},
                            'position': 0,
                            'children': [
                                {
                                    "id": md5('api standard rule 3'.encode()).hexdigest(),
                                    "type": "cartLineItemTag",
                                    "value": {
                                        "operator": "!=",
                                        "identifiers": [
                                            md5('SPEDITION'.encode()).hexdigest()
                                        ]
                                    },
                                    "position": 0
                                },
                            ],
                        },
                    ],
                },
            ],
        }

        payload = {
            "create rules": {
                "entity": "rule",
                "action": 'upsert',
                "key": "write",
                'payload': [
                    never_available_rule,
                    spedition_shipping_rule,
                    standard_shipping_rule
                ]
            }
        }
        self.generate_admin_request('POST', self.sync_url, payload)
        return self.generate_admin_request('POST', self.sync_url, payload)

    def create_payment_methods(self, payment_method_data) -> requests.Response:
        s = payment_method_data
        shop_data = self.shop_data
        media_folder_id = shop_data.media_folders['Payment Method Media']
        payment_method_payloads = []
        for tech_name, config in s.items():
            payload = {
                "id": md5(f"{tech_name}".encode()).hexdigest(),
                "name": config['name'],
                "active": True,
                "position": 0,
                'media': {
                    'id': md5(f'{tech_name}_logo.png'.encode()).hexdigest(),
                    'mediaFolderId': media_folder_id
                },
                "description": s[tech_name]['description'],
                "translations": s[tech_name]['translations'],
            }
            if tech_name == 'visa':
                payload['availabilityRuleId'] = md5('api never available'.encode()).hexdigest()
            payment_method_payloads.append(payload)

        final_payload = {
            "create_payment_method": {
                "entity": "payment_method",
                "action": 'upsert',
                "key": "write",
                'payload': payment_method_payloads
            }
        }

        response = self.generate_admin_request('POST', self.sync_url, final_payload)

        return response

    def create_shipping_methods(self, shipping_method_data) -> list[requests.Response]:
        s = shipping_method_data
        shop_data = self.shop_data
        media_folder_id = shop_data.media_folders['Payment Method Media']
        shipping_method_payloads = []
        for tech_name, config in s.items():
            f, t = s[tech_name]['delivery_time']
            delivery_time_name = f"{f}-{t}"
            payload = {
                "id": md5(f"{tech_name}".encode()).hexdigest(),
                "name": config['name'],
                "active": True,
                "position": 1,
                "availabilityRuleId": md5(config['rule_name'].encode()).hexdigest(),
                'media': {
                    'id': md5(f'{config["logo_name"]}_logo.png'.encode()).hexdigest(),
                    'mediaFolderId': media_folder_id
                },
                "deliveryTime": {
                    'id': md5(delivery_time_name.encode()).hexdigest(),
                    'max': s[tech_name]['delivery_time'][1],
                    'min': s[tech_name]['delivery_time'][0],
                    'name': delivery_time_name,
                    'unit': 'day',
                    'translations': {
                        'de-DE': {
                            'name': delivery_time_name + ' Tage'},
                        'en-UK': {
                            'name': delivery_time_name + ' days'},
                        'it-IT': {
                            'name': delivery_time_name + ' giorni'},
                    }
                },
                "description": s[tech_name]['description'],
                "translations": s[tech_name]['translations'],
            }

            if tech_name == 'standard':
                prices = [
                    {
                        "calculation": 2,
                        "currencyPrice": [
                            {
                                "currencyId": shop_data.currencies['EUR'],
                                "gross": config['price'],
                                "linked": True,
                                "net": config['price'] / 1.19
                            }
                        ],
                        "id": md5(f"{tech_name}_1".encode()).hexdigest(),
                        "quantityEnd": config['free_from'],
                        "quantityStart": 1,
                    },
                    {
                        "calculation": 2,
                        "currencyPrice": [
                            {
                                "currencyId": shop_data.currencies['EUR'],
                                "gross": 0,
                                "linked": True,
                                "net": 0
                            }
                        ],
                        "id": md5(f"{tech_name}_2".encode()).hexdigest(),
                        "quantityStart": config['free_from'],
                    },
                ]
            else:
                prices = [
                    {
                        "calculation": 2,
                        "currencyPrice": [
                            {
                                "currencyId": shop_data.currencies['EUR'],
                                "gross": config['price'],
                                "linked": True,
                                "net": config['price'] / 1.19
                            }
                        ],
                        "id": md5(f"{tech_name}_1".encode()).hexdigest(),
                        "quantityStart": 0,
                    },
                ]

            payload['prices'] = prices
            shipping_method_payloads.append(payload)

        responses = []
        with ThreadPoolExecutor() as ex:
            jobs = [
                ex.submit(
                    self.generate_admin_request,
                    'POST',
                    self.sync_url,
                    {
                        "create_shipping_method": {
                            "entity": "shipping_method",
                            "action": 'upsert',
                            "key": "write",
                            'payload': [payload]
                        }
                    }
                )
                for payload in shipping_method_payloads
            ]

            for f in futures.as_completed(jobs):
                responses.append(f.result())

        self.read_shop_data_from_url()
        self.save_shop_data()

        return responses

    def create_sales_channel(self, domain: str, language_iso: str, shipping_method_data) -> requests.Response:
        shop_data = self.shop_data
        payment_method_names = [
            # "Kreditkarte (via Stripe)",
            "Visa",
            "Kauf auf Rechnung",
            "Vorkasse",
        ]
        shipping_method_names = list(shipping_method_data.keys())
        response = self.generate_admin_request('GET', f'https://{self.target}/api/_action/access-key/sales-channel')
        access_key = response.json()['accessKey']

        sales_channel_payload = {
            "id": md5(self.target.encode()).hexdigest(),
            "typeId": shop_data.type_id,
            "languageId": shop_data.languages[language_iso],
            "customerGroupId": shop_data.customer_group_id,
            "currencyId": shop_data.currencies['EUR'],
            "paymentMethodId": shop_data.payment_methods['Vorkasse'],
            "shippingMethodId": md5(shipping_method_names[0].encode()).hexdigest(),
            "countryId": shop_data.countries['Deutschland'],
            "navigationCategoryId": random.choice(shop_data.root_category_ids),
            "footerCategoryId": md5(f'{self.target}_footer'.encode()).hexdigest(),
            "serviceCategoryId": md5(f'{self.target}_service'.encode()).hexdigest(),
            "name": self.target,
            "taxCalculationType": "vertical",
            "accessKey": access_key,
            "active": True,
            "currencies": [
                {
                    "id": shop_data.currencies['EUR']
                }
            ],
            "languages": [
                {
                    "id": shop_data.languages[language_iso]
                }
            ],
            "countries": [
                {
                    "id": shop_data.countries['Deutschland']
                }
            ],
            "paymentMethods": [
                {
                    "id": uuid
                }
                for name, uuid in shop_data.payment_methods.items()
                if name in payment_method_names
                   and name in shop_data.payment_methods
            ],
            "shippingMethods": [
                {
                    "id": md5(name.encode()).hexdigest()
                }
                for name in shipping_method_names
            ],
            "domains": [
                {
                    "id": md5(f'https://{self.target}'.encode()).hexdigest(),
                    "url": f"https://{self.target}",
                    "languageId": shop_data.languages[language_iso],
                    "currencyId": shop_data.currencies['EUR'],
                    "snippetSetId": md5(f'{self.target}_{language_iso}_snippet_set'.encode()).hexdigest(),
                    "hreflangUseOnlyLocale": False
                },
                {
                    "id": md5(f'http://{self.target}'.encode()).hexdigest(),
                    "url": f"http://{self.target}",
                    "languageId": shop_data.languages[language_iso],
                    "currencyId": shop_data.currencies['EUR'],
                    "snippetSetId": md5(f'{self.target}_{language_iso}_snippet_set'.encode()).hexdigest(),
                    "hreflangUseOnlyLocale": False
                },
                {
                    "id": md5(f'https://www.{self.target}'.encode()).hexdigest(),
                    "url": f"https://www.{self.target}",
                    "languageId": shop_data.languages[language_iso],
                    "currencyId": shop_data.currencies['EUR'],
                    "snippetSetId": md5(f'{self.target}_{language_iso}_snippet_set'.encode()).hexdigest(),
                    "hreflangUseOnlyLocale": False
                },
                {
                    "id": md5(f'http://www.{self.target}'.encode()).hexdigest(),
                    "url": f"http://www.{self.target}",
                    "languageId": shop_data.languages[language_iso],
                    "currencyId": shop_data.currencies['EUR'],
                    "snippetSetId": md5(f'{self.target}_{language_iso}_snippet_set'.encode()).hexdigest(),
                    "hreflangUseOnlyLocale": False
                },
            ]
        }

        payload = {
            "create_sales_channels": {
                "entity": "sales_channel",
                "action": 'upsert',
                "key": "write",
                'payload': [sales_channel_payload]
            }
        }
        response = self.generate_admin_request('POST', self.sync_url, payload)
        if response.status_code == 400:
            del sales_channel_payload['languages']
            del sales_channel_payload['navigationCategoryId']
            response = self.generate_admin_request('PATCH', f'https://{self.target}/api/sales-channel/{md5(domain.encode()).hexdigest()}', sales_channel_payload)

        self.shop_data.sales_channels = self.read_sales_channels()
        self.shop_data.storefront_sales_channels = list(
            filter(lambda x: x['attributes']['typeId'] == self.shop_data.type_id, shop_data.sales_channels))

        self.save_shop_data()
        return response

    def create_product_stream(self):
        product_stream_payload = {
            "id": md5(f'{self.target}_product_stream_all_active'.encode()).hexdigest(),
            "name": f'{self.target} all',
            "filters": [
                {
                    "id": md5(f'{self.target}filtercontainer1'.encode()).hexdigest(),
                    "operator": "OR",
                    "position": 0,
                    "queries": [
                        {
                            "id": md5(f'{self.target}filtercontainer2'.encode()).hexdigest(),
                            "operator": "AND",
                            "parentID": md5(f'{self.target}filtercontainer1'.encode()).hexdigest(),
                            "position": 0,
                            "queries": [
                                {
                                    "field": "active",
                                    "id": md5(f'{self.target}filtercontainer3'.encode()).hexdigest(),
                                    "parentID": md5(f'{self.target}filtercontainer2'.encode()).hexdigest(),
                                    "position": 0,
                                    "type": "equals",
                                    "value": "1"
                                }
                            ],
                            "type": "multi",
                        }
                    ],
                    "type": "multi",
                }
            ]
        }

        payload = {
            "create_product_stream": {
                "entity": "product_stream",
                "action": 'upsert',
                "key": "write",
                'payload': [product_stream_payload]
            }
        }
        response = self.generate_admin_request('POST', self.sync_url, payload)
        return response

    def create_product_export_sales_channel(self, export_template):
        payload = {
            'filter': [
                {
                    'type': 'equals',
                    'field': 'name',
                    'value': self.target
                }
            ]
        }
        parent_sales_channel = psc = self.generate_admin_request('POST',
                                                                 f'https://{self.target}/api/search/sales-channel',
                                                                 payload).json()['data'][0]['attributes']

        with ThreadPoolExecutor() as ex:
            jobs = [
                ex.submit(self.generate_admin_request, 'GET', f'https://{self.target}/api/_action/access-key/sales-channel')
                for _ in range(2)
            ]
            keys = [r.result().json()['accessKey'] for r in jobs]

        sales_channel_payload = {
            "accessKey": keys[0],
            "active": True,
            "countryId": psc["countryId"],
            "currencyId": psc["currencyId"],
            "customerGroupId": psc["customerGroupId"],
            "id": md5(f'{self.target}_export_sales_channel'.encode()).hexdigest(),
            "languageId": psc["languageId"],
            "name": f'{self.target} MC',
            "navigationCategoryId": psc["navigationCategoryId"],
            "paymentMethodId": psc["paymentMethodId"],
            "productExports": [
                {
                    "id": md5(f'{self.target}_product_export'.encode()).hexdigest(),
                    "productStreamId": md5(f'{self.target}_product_stream_all_active'.encode()).hexdigest(),
                    "storefrontSalesChannelId": md5(self.target.encode()).hexdigest(),
                    "salesChannelDomainId": md5(f'https://{self.target}'.encode()).hexdigest(),
                    "currencyId": psc["currencyId"],
                    "fileName": f"{random.randrange(1000000, 9999999)}.xml",
                    "accessKey": keys[1],
                    "encoding": "UTF-8",
                    "fileFormat": "xml",
                    "generateByCronjob": True,
                    "interval": 86400,
                    "headerTemplate": "<?xml version=\"1.0\" encoding=\"UTF-8\" ?>\n<rss version=\"2.0\" xmlns:g=\"http://base.google.com/ns/1.0\" xmlns:atom=\"http://www.w3.org/2005/Atom\">\n    <channel>\n        <atom:link href=\"{{ productExport.salesChannelDomain.url }}/store-api/product-export/{{ productExport.accessKey }}/{{ productExport.fileName }}\" rel=\"self\" type=\"application/rss+xml\" />\n        <title>{{ context.salesChannel.name }}</title>\n        <description>{# change your shop's description #}</description>\n        <link>{{ productExport.salesChannelDomain.url }}</link>\n        <language>{{ productExport.salesChannelDomain.language.locale.code }}</language>\n        <image>\n            <url>{# add your logo URL #}</url>\n            <title>{{ context.salesChannel.name }}</title>\n            <link>{{ productExport.salesChannelDomain.url }}</link>\n        </image>",
                    "bodyTemplate": export_template,
                    "footerTemplate": "</channel>\n</rss>"
                }
            ],
            "shippingMethodId": psc["shippingMethodId"],
            "taxCalculationType": "horizontal",
            "typeId": self.shop_data.export_type_id,
        }
        payload = {
            "create_sales_channels": {
                "entity": "sales_channel",
                "action": 'upsert',
                "key": "write",
                'payload': [sales_channel_payload]
            }
        }
        response = self.generate_admin_request('POST', self.sync_url, payload)
        return response

    def assign_random_theme(self) -> requests.Response:

        themes = self.generate_admin_request('POST', f'https://{self.target}/api/search/theme').json()['data']
        theme_ids = [
            item['id']
            for item in themes
            if item['attributes']['name'] != 'Shopware default theme'
        ]

        random_theme_id = random.choice(theme_ids)

        return self.generate_admin_request(
            'POST',
            f'https://{self.target}/api/_action/theme/{random_theme_id}/assign/{md5(self.target.encode()).hexdigest()}'
        )

    def randomize_theme_colors(self):
        pl = {
            'associations': {
                'salesChannels': {}
            }
        }
        colors = ['sw-color-buy-button', 'sw-color-brand-primary', 'sw-color-brand-secondary', 'sw-border-color', 'sw-background-color', 'sw-color-success', 'sw-color-info',
                  'sw-color-warning', 'sw-color-danger', 'sw-color-price', 'sw-color-buy-button-text', 'rhweb-body-border-color', 'rhweb-body-border-text-color']

        themes = self.generate_admin_request('POST', f'https://{self.target}/api/search/theme', payload=pl).json()['data']
        active_theme = next(filter(lambda x: x['relationships']['salesChannels']['data'], themes))
        patch_url = f'https://{self.target}/api/_action/theme/{active_theme["id"]}'
        theme_fields = active_theme['attributes']['baseConfig']['fields']
        color_fields = {
            name: value
            for name, value in theme_fields.items()
            # if 'color' in name
            if name in colors
        }

        color_payload = {
            field: {
                "value": attributes['value']}
            for field, attributes in color_fields.items()
        }

        color_payload = {
            field: {
                "value": randomize_color(attributes['value'])}
            for field, attributes in color_fields.items()
        }

        payload = {
            "config": color_payload
        }

        return self.generate_admin_request('PATCH', patch_url, payload=payload)

    def create_invoice(self, domain, company: dict) -> requests.Response:

        response = self.generate_admin_request('POST', f'https://{self.target}/api/search/document-type')
        result = response.json()['data']
        invoice_type_id = list(filter(lambda x: x['attributes']['technicalName'] == 'invoice', result))[0]['id']
        comp = ConfigData()
        for key, value in company.items():
            setattr(comp, key, value)

        payload = {
            "create_invoice": {
                "entity": "document_base_config",
                "action": 'upsert',
                'payload': [
                    {
                        "id": md5(f"{domain}_invoice".encode()).hexdigest(),
                        "documentTypeId": invoice_type_id,
                        "name": f"{domain}_invoice",
                        "global": False,
                        "config": {
                            "pageSize": "a4",
                            "pageOrientation": "portrait",
                            "displayHeader": True,
                            "displayLineItems": True,
                            "displayPageCount": True,
                            "displayPrices": True,
                            "displayFooter": True,
                            "displayCompanyAddress": True,
                            "companyName": comp.firma,
                            "companyEmail": f'{comp.pre}@{comp.domain}',
                            "companyAddress": comp.street,
                            "companyPhone": comp.phone,
                            "companyUrl": comp.domain,
                            "taxNumber": comp.tax_number,
                            "taxOffice": comp.city,
                            "vatId": comp.ust_id,
                            "bankName": "BANKNAME",
                            "bankIban": "IBAN",
                            "placeOfFulfillment": comp.city,
                            "placeOfJurisdiction": f'Deutschland <br /> {comp.amtsgericht}, {comp.hrb}',
                            "bankBic": "BIC",
                            "executiveDirector": comp.chef
                        },
                        "salesChannels": [
                            {
                                "id": md5(f'{domain}_invoice_sales_channel'.encode()).hexdigest(),
                                "documentBaseConfigId": md5(f'{domain}_invoice_base_config'.encode()).hexdigest(),
                                "salesChannelId": md5(domain.encode()).hexdigest(),
                                "documentTypeId": invoice_type_id
                            }
                        ],
                    }
                ]
            }
        }
        return self.generate_admin_request('POST', self.sync_url, payload)

    def edit_base_data(self, shop_name, shop_mail) -> requests.Response:
        url = f'https://{self.target}/api/_action/system-config/batch'
        payload = {
            md5(self.target.encode()).hexdigest(): {
                "core.basicInformation.email": shop_mail,
                "core.basicInformation.shopName": shop_name,
                "core.basicInformation.tosPage": md5(f'{self.target}_agb_page'.encode()).hexdigest(),
                "core.basicInformation.revocationPage": md5(
                    f'{self.target}_widerrufsbelehrung_page'.encode()).hexdigest(),
                "core.basicInformation.shippingPaymentInfoPage": md5(
                    f'{self.target}_versand_page'.encode()).hexdigest(),
                "core.basicInformation.privacyPage": md5(f'{self.target}_datenschutz_page'.encode()).hexdigest(),
                "core.basicInformation.imprintPage": md5(f'{self.target}_impressum_page'.encode()).hexdigest(),
                "core.basicInformation.http404Page": None,
                "core.basicInformation.contactPage": md5(f'{self.target}_kontaktformular_page'.encode()).hexdigest(),
                "core.basicInformation.newsletterPage": self.shop_data.newsletter_page_id
            }
        }
        return self.generate_admin_request('POST', url, payload=payload)

    def update_product_visibilities(self):
        all_products = self.get_all_products()
        all_product_ids = [item['id'] for item in all_products]
        shop_data = self.shop_data
        # 'visibilities': visibility_payload

        product_payloads = [
            {
                'id': product_id,
                'visibilities': [
                    {
                        'id': md5(f'{product_id}_{item["id"]}_visibility'.encode()).hexdigest(),
                        'salesChannelId': item["id"],
                        'visibility': 30
                    }
                ],
            }
            for product_id in all_product_ids
            for item in shop_data.storefront_sales_channels
        ]
        payloads = [
            {
                "update_visibilities": {
                    "entity": "product",
                    "action": 'upsert',
                    'payload': [batch]
                }
            }
            for batch in product_payloads
        ]

        with Progress(
                MofNCompleteColumn(),
                SpinnerColumn(),
                *Progress.get_default_columns(),
                TimeElapsedColumn(),
        ) as progress:
            progress_task = progress.add_task("[green bold]Updating product visibilities", total=len(payloads))

            with ThreadPoolExecutor() as ex:
                jobs = [
                    ex.submit(
                        self.generate_admin_request, 'POST', self.sync_url, payload
                    )
                    for payload in payloads
                ]

                for future in futures.as_completed(jobs):
                    response = future.result()
                    progress.update(progress_task, advance=1)


if __name__ == '__main__':
    import pdb
    
    self = SW6Shop(
        target='traum-fahrrad.com',
        username='adminpha',
        password='121416qQ**',
    )
    print("")
    # pdb.set_trace()
    # self.init_sync()
    # just for testing #
