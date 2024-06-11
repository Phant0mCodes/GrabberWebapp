import dataclasses
import itertools
import json
import random
import re
import shutil
import sys
import traceback
from dataclasses import asdict
from typing import Type
# import numpy as np
import threading
import atexit
# import chromedriver_autoinstaller
import csv
import time
# import undetected_chromedriver as uc
import requests
import os
import yaml
import asyncio
import httpx

from hashlib import md5
from pathlib import Path
from abc import abstractmethod, ABC
from requests import Response
from string import ascii_uppercase
from concurrent import futures
from concurrent.futures import ThreadPoolExecutor, Future
from django.db import transaction
from asgiref.sync import sync_to_async
# from selenium import webdriver

# from src.Product import Product, Child, ProductMessages
from parser.models import (
    Category,
    Product, 
    ProductMessages, 
    Features, 
    GrabSettings, 
    Modes,
    Image,
    ProductReview
)

# from src.DefaultConfig import DefaultConfig
from bs4 import BeautifulSoup as Bs
# from sw6_api.sw6_api import SW6Shop
from urllib.parse import urlencode


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36',
    'x-dg-portal': '27',
}
LOCK = threading.Lock()

PRODUCT_PARSER = 'html.parser'  # [lxml, html.parser]
PRODUCT_PARSER = 'lxml'  # Just comment this line to use html.parser
apply_discount = True
discount = 32.78  # int for %
discount_factor = (100 - discount) / 100
images_zip = False


ENERGY_ICONS = {
    'A': 'https://i.imgur.com/w01c9ha.png',
    'B': 'https://i.imgur.com/dCAhu3Q.png',
    'C': 'https://i.imgur.com/DNvtddA.png',
    'D': 'https://i.imgur.com/b8vKRIS.png',
    'E': 'https://i.imgur.com/WsDzBb7.png',
    'F': 'https://i.imgur.com/QKFt0V6.png',
    'G': 'https://i.imgur.com/WwZbMR5.png',
    'A+': 'https://i.postimg.cc/8CNyVSPw/A.webp',
    'A++': 'https://i.postimg.cc/PJg4VGRW/A.webp',
    'A+++': 'https://i.postimg.cc/CMRp2j25/A.webp',
}

class Core(ABC):

    DEBUG = True
    
    def __init__(self, settings: GrabSettings):
        self.settings = settings
        self.child_category_urls = set()
        self.product_url_list = set()
        self.semaphore = asyncio.Semaphore(12)

    # @staticmethod
    # def generate_random_product_number(pre):
    #     number = random.randint(1000000, 9999999)
    #     tail = random.randint(10000, 99999)
    #     return f'{pre}{number}{tail}'

    # @staticmethod
    # def generate_seo_description(description_html):
    #     unwrapped = re.sub('Beschreibung\W+', '', Bs(description_html, 'lxml').text)
    #     unwrapped = re.sub('\n+', ' - ', unwrapped)[:165]
    #     unwrapped = re.sub('.{3}$', '...', unwrapped)
    #     return unwrapped

    # @staticmethod
    # def generate_seo_title(product_name):
    #     return re.sub(r'[^\w\s]\s*', '', product_name) + ' - kaufen'

    # @staticmethod
    # def clean_category_url(url):
    #     if url.endswith('/'):
    #         url = url[:-1]
    #     # return url.split('?')[0]
    #     return url

    async def grab_single_category(self, category_url: str) -> None:
        
        self.category = Category(
            source_url=category_url,
            source_shop=self.PARSER_NAME,
        )
        
        await self.category.asave()
        
        await self.scan_child_categories(category_url)
        
        for child_category_url in self.child_category_urls.copy():
            
            child_category = Category(
                source_url=child_category_url, 
                source_shop=self.PARSER_NAME,
                parent = self.category,
                has_products=True
            )
            
            #TODO: Handle IF RECOLLECT PRODUCT URLs IN FUTURE IF NECESSARY
            if False: pass # Placehlder for "if set to recollet product URLs"
                
            else:
                if not child_category.product_urls:
                    product_urls = await self.get_product_urls_from_category(child_category_url)
                    child_category.product_urls = product_urls
                    await child_category.asave()
                    self.product_url_list.update(product_urls)

            self.child_category_urls.remove(child_category_url)
            
    def scan_single_child_category(self, child_category_url): 
        pass
        child_category = Category.objects.get(child_category_url)

    async def scan_child_categories(self, category_url: str):
        self.child_category_urls.add(category_url)
        c = 0
        while True:
            c += 1
            old_child_amount = len(self.child_category_urls)

            for url in self.child_category_urls.copy():
                self.scan_single_child_category(url)
            new_child_amount = len(self.child_category_urls)
            if new_child_amount == old_child_amount:
                break
              
    async def get_product_urls_from_category(self, category_url: str) -> dict:
        """
        Motorland method to override in child classes (Parser Modules)
        :category_url = provided category URL
        This method checks the amount of products and pagination existance
        Extracts products from the first site using self.get_product_urls()
        downloads als category pages with a ThreadPoolExecutor
        extracts all product URLs in a for loop usind self.get_product_urls()
        """
        item_amount, page_iterable, collected_product_urls = await self.__process_category__(category_url)
        collected_product_urls = dict(zip(collected_product_urls, [1 for _ in collected_product_urls]))
        mp = self.settings.max_page_amount
        page_iterable = page_iterable[:mp - 1] if mp else page_iterable
        
        tasks = await self.__generate_page_url_tasks__(page_iterable)
        
        for p, task in enumerate(asyncio.as_completed(tasks), start=2):
            product_urls = self.__process_category_page__(await task)
            product_urls = dict(zip(product_urls, [p for _ in product_urls]))
            collected_product_urls.update(product_urls)
        
        return collected_product_urls
            
    def __process_category_page__(self, response: requests.Response) -> set:
        soup = Bs(response.content, 'lxml')
        return self.get_product_urls(soup)

    async def __generate_page_url_tasks__(self, page_iterable: list) -> list:
        return [
            asyncio.create_task(self.fetch_url(url))
            for url in page_iterable
        ]

    @abstractmethod
    def __process_category__(self, category_url) -> (int, list, set): ... # product_amount, category_page_urls, product_urls (from first page)
    
    @abstractmethod
    def __process_child_category__(self, response: requests.Response, child_url: str) -> (bool, list): ...

    @staticmethod
    @abstractmethod
    def get_product_urls(soup: Bs) -> set:
        """
        Motorland method to override in child classes (Parser Modules)
        :soup = soup of a category (page) URL with products
        extracts product URLs from soup and returns as list
        """
        pass

    def fetch_all_main_categories(self) -> None:
        """
        This method fetches main categories from homepage
        and writes the URLs to the category input file
        """
        return

    async def __process_downloaded_product__(self, response, url):
        
        html = response.content
        soup = Bs(html, "lxml")
                
        product, product_images, reviews, child_products, message = await self.get_product_data(soup, url)
        await self.save_product_to_db(product, product_images, reviews, child_products)
        
    @sync_to_async
    def save_product_to_db(self, product, product_images, reviews, child_products):   
        with transaction.atomic():
        
            product.main_image.save()
            product.manufacturer_image.save()
            product.save()
            product.images.set(product_images)
                
            for child_product, child_product_images in child_products.items():
                child_product.save()
                Image.objects.bulk_create(child_product_images, ignore_conflicts=True)            
                child_product.images.set(child_product_images)
            
            ProductReview.objects.bulk_create(reviews, ignore_conflicts=True)
        
    async def download_products(self, product_url_list):
            
        fetch_tasks = [
            asyncio.create_task(self.fetch_url(url))
            for url in product_url_list            
        ]

        process_tasks = []
        
        for fetch_task in asyncio.as_completed(fetch_tasks):
            response = await fetch_task
            process_tasks.append(
                asyncio.create_task(
                    self.__process_downloaded_product__(
                        response, 
                        response.request.url
                    )
                )
            )
                
        await asyncio.gather(*process_tasks)
        
    def __save_image_urls_to_database__(self):
        pass

    @abstractmethod
    async def get_product_data(self, soup: Bs, url) -> (Product, Type[ProductMessages]):
        raise NotImplemented('This method must be mplemented in child class')

    @abstractmethod
    async def get_category(self, soup: Bs) -> Category:
        raise NotImplemented('This method must be mplemented in child class')
    
    def __download_image__(self, url, filename):
        # url = url.split('?')[0] + '.jpeg'
        path = f'{self.product_images_dir}/{filename}'
        if not os.path.exists(path):
            content = self.fetch_url(url).content
            with open(path, 'wb') as img_:
                img_.write(content)

    def download_images(self):

        downloaded_images = os.listdir(self.product_images_dir)
        urls_from_category = self.cur.execute(f"""
        SELECT product_urls FROM {self.parser_name}_categories
        WHERE url IN ({", ".join(f"'{item}'" for item in self.filter_categories)})
        """).fetchall()
        urls_from_category = [json.loads(subtup[0]) for subtup in urls_from_category]
        urls_from_category = set(item for subtup in urls_from_category for item in subtup)

        image_data = self.cur.execute(
            f"""
            SELECT url u, filename f FROM {self._conf.parser_name}_product_images 
            WHERE u != '""'
            AND f NOT IN ({','.join(f"'{fn}'" for fn in downloaded_images)})
            AND product IN ({','.join(f"'{fn}'" for fn in urls_from_category)})
            """).fetchall()

        print(image_data.__len__())
        to_download_count = len(image_data)
        downloaded_count = len(os.listdir(self.product_images_dir))
        self.signals.upload_progress_reset.emit()
        self.signals.product_uploader_format.emit('DOWNLOADING PRODUCT IMAGES (%v / %m)')
        self.signals.product_upl_list.emit(to_download_count + downloaded_count)
        self.signals.existing_products2.emit(downloaded_count)

        if not self.DEBUG:
            with ThreadPoolExecutor() as ex:
                jobs = [
                    ex.submit(
                        self.__download_image__,
                        url,
                        filename
                    )
                    for url, filename in image_data
                ]

                for _ in futures.as_completed(jobs):
                    self.signals.product_upl_progress.emit()
                    
        else:
            for url, filename in image_data:
                self.__download_image__(url, filename)
                self.signals.product_upl_progress.emit()

    def __postprocess_uploaded_products__(self, uploaded_product_skus: list, uploaded_product_urls: list, response: requests.Response = None):

        if response:
            if response.status_code not in [200, 204]:
                print(response.text)
        self.cur.executemany(
            f"INSERT OR REPLACE INTO `{self._conf.target}_uploaded_products` VALUES(?, ?)",
            list(zip(self.__jsonify_for_db__(uploaded_product_skus), self.__jsonify_for_db__(uploaded_product_urls)))
        )
        self.con.commit()

        for sku in uploaded_product_skus:
            message = f'✔ PRODUCT UPLOADED ✔ (SKU: {sku})'

        return 'OK'

    def __sw6_upload_products__(self):
        container_size = 1

        # if self.data_containers:
        #
        #     all_existing_products = self.target_shop_instance.get_all_products()
        #     all_parents = [p for p in all_existing_products if not p['attributes']['parentId']]
        #     all_existing_parent_urls = [item['attributes']['customFields']['grab_add_source_url'] for item in all_parents]
        #
        #     for data in self.data_containers.copy():
        #         if data['url'] in all_existing_parent_urls:
        #             self.__postprocess_uploaded_products__([data['sku']], [data['url']])
        #             self.data_containers.remove(data)

        if not self.DEBUG:
            with ThreadPoolExecutor(max_workers=12) as executor:
                uploads = [
                    executor.submit(self.target_shop_instance.create_products, data)
                    for data in self.data_containers
                ]
                for future in futures.as_completed(uploads):
                    try:
                        self.__postprocess_uploaded_products__(*future.result())
                    except Exception:
                        traceback.print_exc()
                        sys.exit()

        else:
            for data in self.data_containers:
                skus, urls, response = self.target_shop_instance.create_products(data)
                print(skus, urls, response)
                self.__postprocess_uploaded_products__(skus, urls, response)

    def __sw6_update_existing_products__(self):
        print('updating')
        urls_from_category = self.cur.execute(f"""
        SELECT product_urls FROM {self.parser_name}_categories
        WHERE url IN ({", ".join(f"'{item}'" for item in self.child_category_urls)})
        """).fetchall()
        urls_from_category = [json.loads(subtup[0]) for subtup in urls_from_category]
        urls_from_category = [item for subtup in urls_from_category for item in subtup]
        existing_ids = [
            p['id'] for p in self.target_shop_instance.get_all_products()
            if not p['attributes']['parentId']
        ]
        data_containers = self.cur.execute((f"""
            SELECT * FROM `{self.parser_name}_products`
            WHERE url NOT IN (SELECT url FROM `{self._conf.target}_uploaded_products`)
            AND url IN ({", ".join([f"'{json.dumps(u)}'" for u in urls_from_category])})
            """)).fetchall()
        data_containers = [
            Product(*[json.loads(col) for col in row]).__dict__
            for row in data_containers
        ]

        to_patch_datas = [
            dc
            for dc in data_containers
            if md5(dc['sku'].encode()).hexdigest() in existing_ids
        ]
        del existing_ids
        del data_containers

        to_upload_count = len(to_patch_datas)

        self.signals.upload_progress_reset.emit()
        self.signals.product_uploader_format.emit('UPLOADING PRODUCTS (%v / %m)')
        self.signals.product_upl_list.emit(to_upload_count)

        if not self.DEBUG:
            with ThreadPoolExecutor(max_workers=12) as ex:
                jobs = [
                    ex.submit(self.target_shop_instance.create_products, data)
                    for data in to_patch_datas
                ]

                for future in futures.as_completed(jobs):
                    self.__postprocess_uploaded_products__(*future.result())

        else:
            for data in to_patch_datas:
                _, _, response = self.target_shop_instance.create_products([data])
                print(response)
                if response.status_code not in [200, 204]:
                    print(response.text)
                self.signals.product_upl_progress.emit()

    def upload_products(self):
        """
        Uploads products to a SW6 instance
        Takes data from self.product_data_container list
        uses create_products() method from sw6_api module, from SW6Shop() class
        """
        self.cur.execute(f"""
        CREATE TABLE IF NOT EXISTS `{self._conf.target}_uploaded_products`
        (sku, url UNIQUE)
        """)
        self.con.commit()

        uploaded_count = len(self.cur.execute((f"""
        SELECT * FROM `{self._conf.target}_uploaded_products`
        """)).fetchall())

        if self._conf.mode == 'Category list':
            self.urls_from_category = self.cur.execute(f"""
            SELECT product_urls FROM {self.parser_name}_categories
            WHERE url IN ({", ".join(f"'{item}'" for item in self.filter_categories)})
            """).fetchall()
            self.urls_from_category = [json.loads(subtup[0]) for subtup in self.urls_from_category]
            self.urls_from_category = set(item for subtup in self.urls_from_category for item in subtup)
            self.data_containers = self.cur.execute((f"""
                SELECT * FROM `{self.parser_name}_products`
                WHERE url NOT IN (SELECT url FROM `{self._conf.target}_uploaded_products`)
                AND url IN ({", ".join([f"'{json.dumps(u)}'" for u in self.urls_from_category])})
                AND category IS NOT NULL
                """)).fetchall()
            self.data_containers = [
                Product(*[json.loads(col) for col in row]).__dict__
                for row in self.data_containers
            ]

        elif self._conf.mode == 'Product List':
            self.data_containers = self.cur.execute((f"""
                SELECT * FROM `{self.parser_name}_products`
                WHERE url NOT IN (SELECT url FROM `{self._conf.target}_uploaded_products`)
                AND url IN ({", ".join([f"'{json.dumps(u)}'" for u in self.to_upload_product_url_list])})
                AND category IS NOT NULL
                """)).fetchall()
            self.data_containers = [
                Product(*[json.loads(col) for col in row]).__dict__
                for row in self.data_containers
            ]

        to_upload_count = len(self.data_containers)

        self.signals.upload_progress_reset.emit()
        self.signals.product_uploader_format.emit('UPLOADING PRODUCTS (%v / %m)')
        self.signals.product_upl_list.emit(to_upload_count + uploaded_count)

        self.signals.existing_products2.emit(uploaded_count)

        if self._conf.shop_cms == 'Shopware 6':
            if self._conf.update_only:
                self.__sw6_update_existing_products__()
            else:
                self.__sw6_upload_products__()

        # elif self._conf.shop_cms == 'Shopify':
        #
        #     def add_energy_class_metafields(pr: shopify.Product, container):
        #         energy_class = shopify.Metafield()
        #         energy_class.namespace = 'EnergyEfficiency'
        #         energy_class.type = "single_line_text_field"
        #         energy_class.key = 'Energieklasse'
        #         energy_class.value = container['energy_class']
        #         result = pr.add_metafield(energy_class)
        #
        #         muta = '''
        #             mutation StagedUploadsCreate($input: [StagedUploadInput!]!) {
        #               stagedUploadsCreate(input: $input) {
        #                 stagedTargets {
        #                   parameters {
        #                     name
        #                     value
        #                     __typename
        #                   }
        #                   resourceUrl
        #                   url
        #                   __typename
        #                 }
        #                 userErrors {
        #                   field
        #                   message
        #                   __typename
        #                 }
        #                 __typename
        #               }
        #             }
        #         '''
        #         file = open('ASSET_MMS_81072439.pdf', 'rb')
        #         variables = {
        #             "input": {
        #                 "filename": "testdatasheet",
        #                 "mimeType": "application/pdf",
        #                 "resource": "FILE",
        #                 # "fileSize": str(pdf.seek(0, os.SEEK_END)),
        #                 "httpMethod": "POST"
        #             }
        #         }
        #         response = json.loads(shopify.GraphQL().execute(muta, variables=variables))
        #
        #         data = response['data']['stagedUploadsCreate']['stagedTargets'][0]
        #         files = {
        #             item['name']: (None, item['value'])
        #             for item in data['parameters']
        #         }
        #         files['file'] = file
        #         source_url = data['resourceUrl']  # The URL to be passed as originalSource in CreateMediaInput and FileCreateInput for the productCreateMedia and fileCreate mutations.
        #         post_url = data['url']
        #         r = requests.request('POST', post_url, files=files)
        #
        #         muta = '''
        #             mutation FileCreateMutation($input: [FileCreateInput!]!) {
        #               fileCreate(files: $input) {
        #                 files {
        #                   alt
        #                   ... on GenericFile {
        #                     id
        #                     createdAt
        #                   }
        #                   ... on MediaImage {
        #                     id
        #                     createdAt
        #                   }
        #                   ... on Video {
        #                     id
        #                     createdAt
        #                   }
        #                 }
        #                 userErrors {
        #                   code
        #                   field
        #                   message
        #                 }
        #               }
        #             }
        #         '''
        #         muta = '''
        #         mutation fileCreate($files: [FileCreateInput!]!) {
        #           fileCreate(files: $files) {
        #             files {
        #               alt
        #             }
        #             userErrors {
        #               field
        #               message
        #             }
        #           }
        #         }
        #         '''
        #
        #         variables = {
        #             "files": {
        #                 # "alt": "alternative texte for the test pdf",
        #                 # "contentType": "",
        #                 "originalSource": source_url
        #             }
        #         }
        #         response = json.loads(shopify.GraphQL().execute(muta, variables=variables))
        #
        #
        #         # for file upload 3 operations:
        #         # 1 StagedUploadsCreate
        #         # 2 POST request to https://shopify-staged-uploads.storage.googleapis.com/
        #         # 3 FileCreateMutation
        #
        #         variables = {
        #             "files": {
        #                 "alt": "testpdf",
        #                 "contentType": "FILE",
        #                 "originalSource": container['energy_pdf_url']
        #             }
        #         }
        #         muta = '''
        #         mutation fileCreate($files: [FileCreateInput!]!) {
        #           fileCreate(files: $files) {
        #             files {
        #               alt
        #               createdAt
        #             }
        #           }
        #         }'''
        #         result = shopify.GraphQL().execute(muta, variables=variables)
        #
        #     def upload_to_shopify(container):
        #
        #         single = True if len(container['children']) == 0 else False
        #         product = shopify.Product()
        #         product.title = container['product_name']
        #         product.vendor = container['manufacturer_name']
        #         product.body_html = container['description_html'] + container['description_tail']
        #         product.sku = container['sku']
        #         product.barcode = container['ean']
        #         product.image_urls = []
        #
        #         energy_class = shopify.Metafield()
        #         energy_class.namespace = 'EnergyEfficiency'
        #         energy_class.type = "single_line_text_field"
        #         energy_class.key = 'Energieklasse'
        #         energy_class.value = container['energy_class']
        #
        #
        #
        #         result = product.add_metafield(energy_class)
        #
        #         for u in container['image_urls']:
        #             image = shopify.Image()
        #             image.product_id = product.id
        #             image.src = u
        #             product.image_urls.append(image)
        #         if single:
        #             product.save()
        #             variant = product.attributes['variants'][0]
        #             variant.barcode = container['ean']
        #             variant.sku = container['product_number']
        #             variant.compare_at_price = container['strike_price']
        #             variant.price = container['purchase_price']
        #             variant.weight = 0.5
        #
        #             product.save()
        #
        #         options = [child['options'] for child in container['children']]
        #         product_result = product.save()
        #
        #         names = set([
        #             name for optset in options for name in optset.keys()
        #         ])
        #         product.options = [
        #             {
        #                 'name': key,
        #                 'values': list(set(optset[key] for optset in options))
        #             }
        #             for key in names
        #         ]
        #         product.variants = []
        #
        #         for child in container['children']:
        #             variant = shopify.Variant()
        #             variant.product_id = product.id
        #             variant.option1 = child['options']['Farbe']
        #             variant.option2 = child['options']['Größe']
        #             variant.barcode = child['ean']
        #             variant.compare_at_price = str(child['strike_price'])
        #             variant.price = str(child['purchase_price'])
        #             variant.sku = child['product_number']
        #             variant.inventory_management = 'shopify'
        #             product.variants.append(variant)
        #
        #         product_result = product.save()
        #         print(f'{product_result=}')
        #         if not product_result:
        #             return
        #         images_map = {
        #             child['options']['Farbe']: {
        #                 'url': child['image_urls'][0],
        #                 'variant_ids': []
        #             }
        #             for child in container['children']
        #         }
        #
        #         for variant in product.variants:
        #             images_map[variant.option1]['variant_ids'].append(variant.id)
        #
        #         for color, obj in images_map.items():
        #             image = shopify.Image()
        #             image.product_id = product.id
        #             image.src = obj['url']
        #             image.variant_ids = obj['variant_ids']
        #             image_result = image.save()
        #             print(f'{image_result=}')
        #
        #         inventory_ids = [variant.attributes['inventory_item_id'] for variant in product.variants]
        #         for item_id in inventory_ids:
        #             inventory_level = shopify.InventoryLevel.find_first(inventory_item_ids=item_id)
        #             print(f'{inventory_level=}')
        #             inventory_result = shopify.InventoryLevel.set(
        #                 inventory_item_id=item_id, location_id=inventory_level.location_id, available=999)
        #             print(f'{inventory_result=}')
        #
        #     for container in list(self.product_data_container.values()):
        #             try:
        #                 upload_to_shopify(container)
        #             except KeyError:
        #                 print(Exception)
        #
        #     # 10.01.2023
        #     # for container in list(self.product_data_container.values())[:2]:
        #     #     product = {
        #     #         'input': {
        #     #             'title': container['product_name'],
        #     #             'productType': 'test',
        #     #             'vendor': 'manufacturer_name',
        #     #         }
        #     #     }
        #     #     with open('test.jsonl', 'a') as j:
        #     #         j.write(json.dumps(product, indent=4) + '\n')
        #     #
        #     #     result = json.loads(shopify.GraphQL().execute('''
        #     #         mutation {
        #     #           stagedUploadsCreate(input:{
        #     #             resource: BULK_MUTATION_VARIABLES,
        #     #             filename: "bulkproductcreate",
        #     #             mimeType: "text/jsonl",
        #     #             httpMethod: POST
        #     #           }){
        #     #             userErrors{
        #     #               field,
        #     #               message
        #     #             },
        #     #             stagedTargets{
        #     #               url,
        #     #               resourceUrl,
        #     #               parameters {
        #     #                 name,
        #     #                 value
        #     #               }
        #     #             }
        #     #           }
        #     #         }'''))
        #     #     params = result['data']['stagedUploadsCreate']['stagedTargets'][0]['parameters']
        #     #
        #     #     files = {
        #     #         item['name']: (None, item['value'])
        #     #         for item in result['data']['stagedUploadsCreate']['stagedTargets'][0]['parameters']
        #     #     }
        #     #     files['file'] = open('test.jsonl', 'rb')
        #     #
        #     #     r = requests.request('POST', 'https://shopify-staged-uploads.storage.googleapis.com/', files=files)
        #     #     xml = xmltodict.parse(r.content)
        #     #     upload_path = '/'.join(xml['PostResponse']['Location'].split('/')[4:])
        #     #     result = json.loads(shopify.GraphQL().execute(f'''
        #     #         mutation {{
        #     #           bulkOperationRunMutation(
        #     #             mutation: "mutation call($input: ProductInput!) {{ productCreate(input: $input) {{ product {{id title variants(first: 10) {{edges {{node {{id title inventoryQuantity }}}}}}}} userErrors {{ message field }} }} }}",
        #     #             stagedUploadPath: "{upload_path}") {{
        #     #             bulkOperation {{
        #     #               id
        #     #               url
        #     #               status
        #     #             }}
        #     #             userErrors {{
        #     #               message
        #     #               field
        #     #             }}
        #     #           }}
        #     #         }}
        #     #         '''))
        #     #
        #     #     # with ThreadPoolExecutor(max_workers=5) as executor:
        #     #     #
        #     #     #     uploads = [executor.submit(upload_to_shopify, container) for container in self.product_data_container]
        #     #     #     [progress.update(progress_task, advance=1) for _ in futures.as_completed(uploads)]

    def upload_manufacturer_images(self):
        query = f"""
        CREATE TABLE IF NOT EXISTS `{self._conf.target}_uploaded_manufacturer_images`
        (url UNIQUE, manufacturer_name)
        """
        self.cur.execute(query)
        self.con.commit()
        uploaded_count = len(self.cur.execute((f"""
        SELECT * FROM `{self._conf.target}_uploaded_manufacturer_images`
        """)).fetchall())

        image_data = self.cur.execute(
            f"""
            SELECT DISTINCT manufacturer_image_url u, manufacturer_name f FROM {self._conf.parser_name}_products
            WHERE u != '""'
            AND url IN (SELECT url FROM '{self._conf.target}_uploaded_products')
            AND u NOT IN (SELECT url FROM `{self._conf.target}_uploaded_manufacturer_images`)
            """).fetchall()
        image_data = [tuple(json.loads(col) for col in row) for row in image_data]

        to_upload_count = len(image_data)
        self.signals.upload_progress_reset.emit()
        self.signals.product_uploader_format.emit('UPLOADING MANUFACTURER IMAGES (%v / %m)')
        self.signals.product_upl_list.emit(to_upload_count + uploaded_count)
        self.signals.existing_products2.emit(uploaded_count)

        if not self.DEBUG:

            with ThreadPoolExecutor(max_workers=12) as executor:
                jobs = {
                    executor.submit(self.target_shop_instance.upload_media, url, filename, file_bytes=True): (url, filename)
                    # executor.submit(self.target_shop_instance.upload_media, url, filename): (url, filename)
                    for url, filename in image_data
                }
                for future in futures.as_completed(jobs):
                    response = future.result()
                    print(response)
                    query = f"""
                    INSERT OR REPLACE INTO `{self._conf.target}_uploaded_manufacturer_images` 
                    VALUES(?,?)
                    """
                    self.cur.execute(query, self.__jsonify_for_db__(jobs[future]))
                    self.signals.product_upl_progress.emit()
                    self.con.commit()

        else:
            for url, filename in image_data:
                # resp = self.target_shop_instance.upload_media(url, filename, file_bytes=True)
                resp = self.target_shop_instance.upload_media(url, filename)
                print(url, filename)

    def upload_product_images(self):
        self.cur.execute(f"""
        CREATE TABLE IF NOT EXISTS `{self._conf.target}_uploaded_product_images`
        (url UNIQUE, filename)
        """)
        self.con.commit()
        uploaded_count = len(self.cur.execute((f"""
        SELECT * FROM `{self._conf.target}_uploaded_product_images`
        """)).fetchall())

        uploaded_products = self.cur.execute(f"""
        SELECT REPLACE(url, '"', '') FROM '{self._conf.target}_uploaded_products'
        """).fetchall()

        image_data = self.cur.execute(
            f"""
            SELECT url u, filename f FROM {self._conf.parser_name}_product_images 
            WHERE u != '""'
            AND product IN (SELECT REPLACE(url, '"', '') FROM '{self._conf.target}_uploaded_products')
            AND u NOT IN (SELECT url FROM `{self._conf.target}_uploaded_product_images`)            
            """).fetchall()

        to_upload_count = len(image_data)

        self.signals.upload_progress_reset.emit()
        self.signals.product_uploader_format.emit('UPLOADING PRODUCT IMAGES (%v / %m)')
        self.signals.product_upl_list.emit(to_upload_count + uploaded_count)
        self.signals.existing_products2.emit(uploaded_count)

        # if image_data:
        #     existing_images = self.target_shop_instance.get_all_media_with_file()
        #     existing_image_ids = [item['id'] for item in existing_images]
        #     records = []
        #     for image in image_data.copy():
        #         url, fname = image
        #         uuid = md5(url.encode()).hexdigest()
        #         if uuid in existing_image_ids:
        #             image_data.remove(image)
        #             records.append(image)
        #             message = f'✔ MEDIA UPLOADED ✔ (URL: {url} | FILENAME: {fname})'
        #             self.signals.to_output.emit(f'<span style="color:{Colors.success}">{message}</span>')
        #             self.signals.product_upl_progress.emit()
        #
        #     print('inserting existing media to database')
        #
        #     self.cur.executemany(f"""
        #     INSERT OR REPLACE INTO `{self._conf.target}_uploaded_product_images` VALUES(?,?)
        #     """, records)
        #     self.con.commit()
        #
        #     print('inserting existing media to database done...')

        if not self.DEBUG:

            with ThreadPoolExecutor(max_workers=12) as executor:
                jobs = {
                    executor.submit(self.target_shop_instance.upload_media, url, re.sub('\W', '-', filename)): (url, filename)
                    # executor.submit(self.target_shop_instance.upload_media, url, re.sub('\W', '-', filename), file_bytes=True): (url, filename)
                    for url, filename in image_data
                }
                for future in futures.as_completed(jobs):
                    # print('processing...')
                    self.signals.product_upl_progress.emit()
                    response = future.result()
                    u, f = jobs[future]
                    if response.status_code not in [200, 204]:
                        message = f'✖ MEDIA UPLOAD ERROR ✖ URL: {u} | FILENAME: {f}'
                        # print(response.text)
                        print(response.status_code, response.json())
                        error_message = response.json()['errors'][0]['code']
                        print(error_message)

                        match error_message:
                            case 'CONTENT__MEDIA_NOT_FOUND' | 'CONTENT__MEDIA_DUPLICATED_FILE_NAME' | 'CONTENT__MEDIA_ILLEGAL_FILE_NAME':
                                self.cur.execute(f"""
                                    INSERT OR REPLACE INTO `{self._conf.target}_uploaded_product_images` VALUES(?,?)
                                    """, (u, f))
                                self.con.commit()

                            case _:
                                print('SOMETHING ELSE HAPPENED, WTF?')
                                print(error_message)

                    else:
                        self.cur.execute(f"""
                        INSERT OR REPLACE INTO `{self._conf.target}_uploaded_product_images` VALUES(?,?)
                        """, (u, f))
                        self.con.commit()
                        message = f'✔ MEDIA UPLOADED ✔ (URL: {u} | FILENAME: {f})'
                        # print(message)

        else:
            message = f'!!! DEBUG MODE !!! (Product image_urls will be uploaded one by one)'
            # self.signals.to_output.emit(f'<span style="color:{Colors.info}">{message}</span>')
            for url, filename in image_data:
                u, f = url, filename
                response = self.target_shop_instance.upload_media(url, filename, file_bytes=True)
                # response = self.target_shop_instance.upload_media(url, filename)
                if response.status_code not in [200, 204]:
                    message = f'✖ MEDIA UPLOAD ERROR ✖ URL: {u} | FILENAME: {f}'
                    # print(response.text)
                    print(response.status_code, response.json())
                    error_message = response.json()['errors'][0]['code']
                    print(error_message)

                    match error_message:
                        case 'CONTENT__MEDIA_NOT_FOUND' | 'CONTENT__MEDIA_DUPLICATED_FILE_NAME' | 'CONTENT__MEDIA_ILLEGAL_FILE_NAME':
                            self.cur.execute(f"""
                                INSERT OR REPLACE INTO `{self._conf.target}_uploaded_product_images` VALUES(?,?)
                                """, (u, f))
                            self.con.commit()

                        case _:
                            print('SOMETHING ELSE HAPPENED, WTF?')
                # assert response.status_code == 204
                else:
                    self.cur.execute(f"""
                    INSERT OR REPLACE INTO `{self._conf.target}_uploaded_product_images` VALUES(?,?)
                    """, (u, f))
                    self.con.commit()
                    message = f'✔ MEDIA UPLOADED ✔ (URL: {u} | FILENAME: {f})'
                    print(message)
                self.signals.product_upl_progress.emit()

    def upload_energy_media(self):
        self.cur.execute(f"""
        CREATE TABLE IF NOT EXISTS `{self._conf.target}_uploaded_energy_media`
        (url UNIQUE, filename)
        """)
        self.con.commit()

        energy_icons_data = [
            tuple(json.loads(col) for col in row)
            for row in self.cur.execute(f"""
            SELECT DISTINCT energy_icon_url u, energy_icon_filename f FROM {self._conf.parser_name}_products 
            WHERE energy_class != '""'
            AND u NOT IN (SELECT url FROM `{self._conf.target}_uploaded_energy_media`)
            """).fetchall()
        ]

        self.signals.upload_progress_reset.emit()
        self.signals.product_uploader_format.emit('UPLOADING ENERGY ICONS (%v / %m)')
        self.signals.product_upl_list.emit(len(energy_icons_data))
        with ThreadPoolExecutor() as ex:
            jobs = [
                ex.submit(
                    self.target_shop_instance.upload_media,
                    url,
                    md5(url.encode()).hexdigest()[:10] + filename.replace('+', 'plus'),
                    file_bytes=True
                )
                for url, filename in energy_icons_data
            ]

            for future in futures.as_completed(jobs):
                self.signals.product_upl_progress.emit()

        for url, filename in energy_icons_data:
            resp = self.target_shop_instance.upload_media(
                url,
                md5(url.encode()).hexdigest()[:10] + filename.replace('+', 'plus'),
                file_bytes=True
            )
            print(resp)

        ###################################################################
        uploaded_count = len(self.cur.execute((f"""
        SELECT * FROM `{self._conf.target}_uploaded_energy_media`
        """)).fetchall())
        to_upload_count = len(self.cur.execute((f"""
        SELECT DISTINCT energy_label_url u FROM {self._conf.parser_name}_products 
        WHERE u NOT IN (SELECT url FROM `{self._conf.target}_uploaded_energy_media`)
        """)).fetchall())

        media_data = self.cur.execute(f"""
        SELECT DISTINCT energy_label_url u, energy_label_filename f FROM {self._conf.parser_name}_products 
        WHERE u != '""'
        AND url IN (SELECT url FROM '{self._conf.target}_uploaded_products')
        AND u NOT IN (SELECT url FROM `{self._conf.target}_uploaded_energy_media`)
        """).fetchall()
        media_data = [tuple(json.loads(col) for col in row) for row in media_data]

        self.signals.upload_progress_reset.emit()
        self.signals.product_uploader_format.emit('UPLOADING ENERGY LABELS (%v / %m)')
        self.signals.product_upl_list.emit(to_upload_count + uploaded_count)
        self.signals.existing_products2.emit(uploaded_count)

        # with ThreadPoolExecutor(max_workers=12) as executor:
        if not self.DEBUG:
            executor = ThreadPoolExecutor(max_workers=12)
            jobs = {
                executor.submit(self.target_shop_instance.upload_media, url, filename, file_bytes=True): (url, filename)
                for url, filename in media_data
            }
            for future in futures.as_completed(jobs):
                try:
                    response = future.result()
                    self.cur.execute(f"""
                    INSERT OR REPLACE INTO `{self._conf.target}_uploaded_energy_media` VALUES(?,?)
                    """, self.__jsonify_for_db__(jobs[future]))
                    self.signals.product_upl_progress.emit()
                    self.con.commit()
                except KeyError as k:
                    print(k)
                    pass

        else:
            for url, filename in media_data:
                response = self.target_shop_instance.upload_media(url, filename, file_bytes=True)
                print(response)
                print(url, filename)
        ###################################################################
        uploaded_count = len(self.cur.execute((f"""
        SELECT * FROM `{self._conf.target}_uploaded_energy_media`
        """)).fetchall())
        to_upload_count = len(self.cur.execute((f"""
        SELECT DISTINCT energy_pdf_url u FROM {self._conf.parser_name}_products 
        WHERE u NOT IN (SELECT url FROM `{self._conf.target}_uploaded_energy_media`)
        """)).fetchall())
        media_data = self.cur.execute(f"""
        SELECT DISTINCT energy_pdf_url u, energy_pdf_filename f FROM {self._conf.parser_name}_products 
        WHERE u != '""'
        AND url IN (SELECT url FROM '{self._conf.target}_uploaded_products')
        AND u NOT IN (SELECT url FROM `{self._conf.target}_uploaded_energy_media`)
        """).fetchall()
        media_data = [tuple(json.loads(col) for col in row) for row in media_data]

        self.signals.upload_progress_reset.emit()
        self.signals.product_uploader_format.emit('UPLOADING ENERGY DATASHEETS (%v / %m)')
        self.signals.product_upl_list.emit(to_upload_count + uploaded_count)
        self.signals.existing_products2.emit(uploaded_count)

        with ThreadPoolExecutor(max_workers=12) as executor:
            jobs = {
                executor.submit(self.target_shop_instance.upload_media, url, filename, file_bytes=True): (url, filename)
                for url, filename in media_data
            }
            for future in futures.as_completed(jobs):
                try:
                    response = future.result()
                    self.cur.execute(f"""
                    INSERT OR REPLACE INTO `{self._conf.target}_uploaded_energy_media` VALUES(?,?)
                    """, self.__jsonify_for_db__(jobs[future]))
                    self.signals.product_upl_progress.emit()
                    self.con.commit()
                except KeyError as k:
                    print(k)
                    pass

    async def __grab_category_list__(self, category_url_list):
        
        for category_url in category_url_list:
            await self.grab_single_category(category_url)
        
    def __grab_by_keyword__(self):
        print('[red][!] The function to grab with keyword search is not available yet! Exiting app...')
        sys.exit()

    def __grab_product_list__(self):
        
        product_urls_from_settings = self.settings.product_urls.splitlines()
        [self.product_url_list.add(url) for url in product_urls_from_settings]

    def __grab_all__(self):
        self.fetch_all_main_categories()
        self.__grab_category_list__()

    def grab_old(self):
        """
        starts the parsing process depending on config
        :single product mode
        :list of products (URLs)
        :single category mode
        :list of categories provided through category_input.txt (defeult)
        :keywords search
        """

        if self._conf.mode == 'Category list':
            self.__grab_category_list__()

        elif self._conf.mode == 'Keywords':
            self.__grab_by_keyword__()

        elif self._conf.mode == 'Product List':
            self.__grab_product_list__()

        elif self._conf.mode == 'ALL':
            self.__grab_all__()

        self.download_products()

        if self._conf.download_product_csv:
            # self.write_to_jtl_csv()
            # self.write_to_woocommerce_csv()
            self.write_to_shopify_csv()

        if self._conf.download_product_images:
            self.download_images()

        if self._conf.upload_to_shop:
            self.upload_products()
            if self._conf.upload_product_images:
                self.upload_manufacturer_images()
                self.upload_product_images()
                self.upload_energy_media()

    def dev_grab(self):
        if self._conf.mode == 'Category list':
            self.__grab_category_list__()

        elif self._conf.mode == 'Product List':
            self.__grab_product_list__()

        elif self._conf.mode == 'Keywords':
            self.__grab_by_keyword__()

        elif self._conf.mode == 'ALL':
            self.__grab_all__()

        self.download_products()
        if self._conf.upload_to_shop:
            self.__get_target_shop_instance__()

    async def grab(self):
        print('start grab')
        start_time = time.time()
        if self.settings.parser_mode == Modes.CATEGORY_URLS.name:
            category_url_list = self.settings.category_urls.splitlines()
            await self.__grab_category_list__(category_url_list)

        if self.settings.parser_mode == Modes.PRODUCT_URLS.name:
            self.__grab_product_list__()

        if self.settings.parser_mode == Modes.KEYWORDS.name:
            print('grab keywords')
            
        if self.settings.parser_mode == Modes.ALL_PRODUCTS.name:
            print('grab all')
        
        await self.download_products(self.product_url_list)
        
        concurrent_duration = time.time() - start_time
        print(f"grab took: {concurrent_duration:.2f} seconds")
        
    def fetch_url_old(
            self,
            url: str,
            allow_redirects: bool = True,
            browser: bool = False,
            undetected: bool = False,
            method: str = 'GET',
            payload=None,
            headers={},
    ) -> Response | str:
        """
        Make a GET request to the provided URL
        Can handle few situations where request status code is not 200

        :url: URL for the request
        :allow_redirects: bool, option to allow or restrict redirects
        :return: response object
        """

        print(f'DOWNLOADING {url}')

        default_headers = HEADERS
        default_headers.update(headers)
        if not browser:
            request_arguments = dict(
                method=method,
                url=url,
                allow_redirects=allow_redirects,
                params=payload,
                headers=default_headers
            )

            if method == 'POST':
                del request_arguments['params']
                request_arguments['json'] = payload

            status_code = None
            while status_code != 200:
                try:
                    response = requests.request(**request_arguments)
                    # print(request_arguments)
                    status_code = response.status_code

                    match status_code:
                        case 200:
                            return response
                        case 404:
                            message = f'! WARNING ! | STATUS CODE: {status_code} | SOURCE URL: {url} | RESPONSE URL: {response.url}'
                            print(message)
                            return response
                        case 500:
                            message = f'✖ NETWORK ERROR ✖ | STATUS CODE: {status_code} | SOURCE URL: {url} | RESPONSE URL: {response.url}'
                            print(message)
                            return response
                        case _:
                            message = f'✖ NETWORK ERROR ✖ | STATUS CODE: {status_code} | SOURCE URL: {url} | RESPONSE URL: {response.url}'
                            print(message)
                            time.sleep(random.randint(5, 20))

                except requests.exceptions.ConnectionError:
                    time.sleep(random.randint(15, 35))

        else:
            pass
            # if not undetected:
            #     options = webdriver.ChromeOptions()
            #     # options.add_experimental_option("prefs", {
            #     #     "profile.managed_default_content_settings.javascript": 2
            #     # })
            #     # options.add_experimental_option("detach", True)
            #     options.headless = True
            #     options.add_argument(f'user-agent={headers["User-Agent"]}')
            #     options.add_argument('--blink-settings=imagesEnabled=false')
            #     chromedriver_autoinstaller.install()
            #     driver = webdriver.Chrome(options=options)
            #     driver.get(url)
            #     html = driver.page_source
            #     driver.quit()
            #     return html
            #
            # else:
            #     options = uc.ChromeOptions()
            #     options.headless = True
            #     options.add_argument('--blink-settings=imagesEnabled=false')
            #     # options.add_experimental_option("detach", True)
            #     driver = uc.Chrome(options=options)
            #     driver.get(url)
            #     html = driver.page_source
            #     driver.quit()
            #     return html
            #

    # @staticmethod
    async def fetch_url(self, url) -> httpx.Response:
        print(f'fetching {url}')
        return await self.fetch_url_httpx(url)
    
    # @staticmethod
    async def fetch_url_httpx(self, url) -> httpx.Response:
        async with self.semaphore:
            async with httpx.AsyncClient() as client:
                status_code = None
                while status_code != 200:
                    try:
                        response = await client.get(url)
                        response.raise_for_status()
                        status_code = response.status_code

                        match status_code:
                            case 200:
                                return response
                            case 404:
                                message = f'! WARNING ! | STATUS CODE: {status_code} | SOURCE URL: {url} | RESPONSE URL: {response.url}'
                                print(message)
                                self.signals.to_network_output.emit(f'<span style="color:{Colors.info}">{message}</span>')
                                return response
                            case 500:
                                message = f'✖ NETWORK ERROR ✖ | STATUS CODE: {status_code} | SOURCE URL: {url} | RESPONSE URL: {response.url}'
                                return response
                            case _:
                                message = f'✖ NETWORK ERROR ✖ | STATUS CODE: {status_code} | SOURCE URL: {url} | RESPONSE URL: {response.url}'
                                time.sleep(random.randint(5, 20))

                    except (httpx.ConnectTimeout, httpx.ReadTimeout):
                        print('Connection Timeout, async sleeping now')
                        asyncio.sleep(random.randint(5, 25))
                        print('asyncio slept well')
                        
    @staticmethod
    async def fetch_url_with_playwright(url): ...


if __name__ == "__main__":
    self = Core('FahrradXXL')

