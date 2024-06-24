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
import logging
from hashlib import md5
from pathlib import Path
from abc import abstractmethod, ABC
from requests import Response
from string import ascii_uppercase
from concurrent import futures
from concurrent.futures import ThreadPoolExecutor, Future
from django.db import transaction
from django.forms.models import model_to_dict
from asgiref.sync import sync_to_async
# from selenium import webdriver

# from src.Product import Product, Child, ProductMessages
from parser.models import (
    Category,
    Product, 
    ProductMessages, 
    Features, 
    Settings, 
    Modes,
    Image,
    ProductReview,
    ShopwareShop
)
from users.models import CustomUser
# from src.DefaultConfig import DefaultConfig
from bs4 import BeautifulSoup as Bs
# from sw6_api.sw6_api import SW6Shop
from parser.SW6ApiHandler import SW6Shop

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

logging.basicConfig(level=logging.ERROR, format='%(message)s')


class Core(ABC):

    DEBUG = True
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.child_category_urls = set()
        self.product_url_list = set()
        self.semaphore = asyncio.Semaphore(12)
        self.data_containers = []

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

    async def __get_target_shop_instance__(self):
        """
        return False if auth failed, else None
        """
        target_shop = await ShopwareShop.objects.aget(pk=self.settings.target_shop_id)
        
        self.target_shop_instance = SW6Shop(
            target_shop.domain,
            username=target_shop.username,
            password=target_shop.password
        )
        
        result = await self.target_shop_instance.obtain_access_token()
        
        if result:
            await self.target_shop_instance.init_sync()

        return result
    
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
        channel_layer = get_channel_layer()

        await self.save_product_to_db(product, product_images, reviews, child_products)
        
        
    @sync_to_async
    def save_product_to_db(self, product, product_images, reviews, child_products):
                
        with transaction.atomic():
            try:
                
                product.main_image.save()
                if product.manufacturer_image: 
                    product.manufacturer_image.save()
                product.save()
                product.images.set(product_images)
                    
                for child_product, child_product_images in child_products.items():
                    child_product.main_image.save()
                    child_product.save()
                    Image.objects.bulk_create(child_product_images, ignore_conflicts=True)            
                    child_product.images.set(child_product_images)
                
                ProductReview.objects.bulk_create(reviews, ignore_conflicts=True)
                
            except:
                
                print(f'PRODUCT {product} COULD NOT BE SAVED')
        
        
    async def download_products(self, product_url_list):
        
        collected_product_urls = self.product_url_list
        product_urls_from_db = set([
            product.source_url async for product in 
            Product.objects
            .filter(pk__in=collected_product_urls)
        ])

        product_urls_to_download = collected_product_urls - product_urls_from_db

        total_count = len(collected_product_urls)
        downloaded_count = len(product_urls_from_db)
        
        print(f'{downloaded_count}/{total_count} Downloading products...')

        fetch_tasks = [
            asyncio.create_task(self.fetch_url(url))
            for url in product_urls_to_download            
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

    ###
    
    async def __postprocess_uploaded_products__(
        self, 
        uploaded_product_skus: list, 
        uploaded_product_urls: list, 
        response: httpx.Response = None
        ):

        if response:
            if response.status_code not in [200, 204]:
                print(response.text)
                return
                    
        for url in uploaded_product_urls:
            product = await Product.objects.aget(pk=url)
            await product.uploaded_to_shops.aadd(self.target_shop_instance.target)
            message = f'✔ PRODUCT UPLOADED ✔ (URL: {url})'

        return 'OK'

    async def __sw6_upload_products__(self):
        container_size = 1

        if self.DEBUG:
            for data in self.data_containers:
                skus, urls, response = await self.target_shop_instance.create_products(data)
                await self.__postprocess_uploaded_products__(skus, urls, response)            

        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self.target_shop_instance.create_products(data))
                for data in self.data_containers
            ]
            for task in asyncio.as_completed(tasks):
                skus, urls, response = await task
                await self.__postprocess_uploaded_products__(skus, urls, response)  

    async def upload_products_to_shopware(self):
        """
        Uploads products to a SW6 instance
        Takes data from self.product_data_container list
        uses create_products() method from sw6_api module, from SW6Shop() class
        """
        uploaded_products = set([product async for product in self.target_shop.uploaded_products.all()])
        products_to_upload = self.products_from_db - uploaded_products
        total_count = len(self.products_from_db)
        uploaded_count = len(uploaded_products)
        
        print(f'{uploaded_count}/{total_count} products uploaded...')
        
        for product in products_to_upload:
            pass
            product_dict = await sync_to_async(model_to_dict)(product)

            product_dict['image_urls'] = [
                img.url for img in product_dict['images']
            ]
            del product_dict['images']

            child_products = [child async for child in product.children.all()]
            child_dicts = [
                await sync_to_async(model_to_dict)(child)
                for child in child_products
            ]

            for dct in child_dicts:
                dct['image_urls'] = [
                    img.url for img in dct['images']
                ]
                del dct['images']
            product_dict['children'] = child_dicts
            
            reviews = [rev async for rev in product.reviews.all()]
            review_dicts = [
                await sync_to_async(model_to_dict)(rev)
                for rev in reviews
            ]     
            product_dict['reviews'] = review_dicts
            
            for rev in product_dict['reviews']:
                rev['time'] = rev['time'].strftime("%Y-%m-%d %H:%M:%S")
            
            self.data_containers.append(product_dict)
        
        await self.__sw6_upload_products__()
           
    async def upload_manufacturer_images(self):
                
        # self.products_from_db = set([
        #     product async for product in Product
        #     .objects
        #     .filter(pk__in=self.product_urls_from_db)
        #     .select_related('manufacturer_image')
        # ][:1])
        
        manufacturer_images_from_db = set([
            p.manufacturer_image for p in self.products_from_db
        ])
                
        uploaded_manufacturer_images = set([image async for image in self.target_shop.uploaded_images.filter(image_type='manufacturer_image')])
        manufacturer_images_to_upload = manufacturer_images_from_db - uploaded_manufacturer_images
        total_count = len(manufacturer_images_from_db)
        uploaded_count = len(uploaded_manufacturer_images)
        
        print(f'{uploaded_count}/{total_count} Uploading manufacturer images...')

        # if self.DEBUG:
        #     for image in manufacturer_images_to_upload:
        #         response = await self.target_shop_instance.upload_media(image.url, image.filename)
        #         if response.status_code not in [200, 204]:
        #             message = f'✖ MEDIA UPLOAD ERROR ✖ URL: {image.url} | FILENAME: {image.filename}'
        #             print(response.status_code, response.json())
        #             error_message = response.json()['errors'][0]['code']
        #             print(error_message)

        #             match error_message:
        #                 case 'CONTENT__MEDIA_NOT_FOUND' | 'CONTENT__MEDIA_DUPLICATED_FILE_NAME' | 'CONTENT__MEDIA_ILLEGAL_FILE_NAME':
        #                     image: Image = image
        #                     await image.uploaded_to_shops.aadd(self.target_shop_instance.target)
                            
        #                 case _:
        #                     print('SOMETHING ELSE HAPPENED, WTF?')
        #                     print(error_message)
        #                     continue
                        
        #         await image.uploaded_to_shops.aadd(self.target_shop_instance.target)

        #     return

        tasks = [
            asyncio.create_task(self.target_shop_instance.upload_media(image.url, image.filename, media=image))
            for image in manufacturer_images_to_upload
        ]

        for task in asyncio.as_completed(tasks):
            response, image = await task
            if response.status_code not in [200, 204]:
                message = f'✖ MEDIA UPLOAD ERROR ✖ URL: {image.url} | FILENAME: {image.filename}'
                print(response.status_code, response.json())
                error_message = response.json()['errors'][0]['code']
                print(error_message)

                match error_message:
                    case ('CONTENT__MEDIA_NOT_FOUND' | 
                          'CONTENT__MEDIA_DUPLICATED_FILE_NAME' | 
                          'CONTENT__MEDIA_ILLEGAL_FILE_NAME'):
                        await image.uploaded_to_shops.aadd(self.target_shop_instance.target)
                        
                    case _:
                        print('SOMETHING ELSE HAPPENED, WTF?')
                        print(error_message)
                        continue
        
            await image.uploaded_to_shops.aadd(self.target_shop_instance.target)
            message = f'✔ MEDIA UPLOADED ✔ (URL: {image.url} | FILENAME: {image.filename})'
            # print(message)
          
    async def upload_product_images(self):
        
        child_products = set([
            child 
            for product in self.products_from_db 
            async for child in product.children.all()
        ])

        all_products = self.products_from_db.union(child_products)
        
        product_images_from_db = set([
            image
            for product in all_products
            async for image in product.images.filter(image_type='product_image')
        ])
                
        uploaded_product_images = set([image async for image in self.target_shop.uploaded_images.filter(image_type='product_image')])
        product_images_to_upload = product_images_from_db - uploaded_product_images
        total_count = len(product_images_from_db)
        uploaded_count = len(uploaded_product_images)
        
        print(f'{uploaded_count}/{total_count} Uploading product images...')
        
        # if self.DEBUG:
        # if False:
        #     print('DEBUGGING PRODUCT IMAGE UPLOADS')
        #     for image in product_images_to_upload:
        #         response = await self.target_shop_instance.upload_media(image.url, image.filename)
        #         if response.status_code not in [200, 204]:
        #             message = f'✖ MEDIA UPLOAD ERROR ✖ URL: {image.url} | FILENAME: {image.filename}'
        #             print(response.status_code, response.json())
        #             error_message = response.json()['errors'][0]['code']
        #             print(error_message)

        #             match error_message:
        #                 case 'CONTENT__MEDIA_NOT_FOUND' | 'CONTENT__MEDIA_DUPLICATED_FILE_NAME' | 'CONTENT__MEDIA_ILLEGAL_FILE_NAME':
        #                     image: Image = image
        #                     await image.uploaded_to_shops.aadd(self.target_shop_instance.target)
                            
        #                 case _:
        #                     print('SOMETHING ELSE HAPPENED, WTF?')
        #                     print(error_message)
        #                     continue
                        
        #         await image.uploaded_to_shops.aadd(self.target_shop_instance.target)
        #         message = f'✔ MEDIA UPLOADED ✔ (URL: {image.url} | FILENAME: {image.filename})'
        #         print(message)
                
        #     return

        tasks = [
            asyncio.create_task(self.target_shop_instance.upload_media(image.url, image.filename, media=image))
            for image in product_images_to_upload
        ]

        for task in asyncio.as_completed(tasks):
            response, image = await task

            if response.status_code not in [200, 204]:
                message = f'✖ MEDIA UPLOAD ERROR ✖ URL: {image.url} | FILENAME: {image.filename}'
                logging.info(response.status_code, response.json())
                error_message = response.json()['errors'][0]['code']
                logging.info(error_message)

                match error_message:
                    case ('CONTENT__MEDIA_NOT_FOUND' | 
                          'CONTENT__MEDIA_DUPLICATED_FILE_NAME' | 
                          'CONTENT__MEDIA_ILLEGAL_FILE_NAME'):
                        image: Image = image
                        await image.uploaded_to_shops.aadd(self.target_shop_instance.target)
                        
                    case _:
                        logging.info('SOMETHING ELSE HAPPENED, WTF?')
                        logging.info(error_message)
                        continue
        
            await image.uploaded_to_shops.aadd(self.target_shop_instance.target)
            message = f'✔ MEDIA UPLOADED ✔ (URL: {image.url} | FILENAME: {image.filename})'

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
    
    ###

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

    async def grab(self):
        
        user = await CustomUser.objects.aget(pk=self.settings.user_id)
        user.grab_lock = True
        await user.asave()
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

        # user.grab_lock = False
        # await user.asave()
        
    async def export(self):
        await self.__get_target_shop_instance__()
        
        self.target_shop = await ShopwareShop.objects.aget(pk=self.settings.target_shop_id)
        self.product_urls_from_db = self.settings.product_urls.splitlines()
        self.products_from_db = set([
            product async for product in 
            Product.objects
            .filter(pk__in=self.product_urls_from_db)
            .select_related('manufacturer_image')
        ])
        await self.upload_products_to_shopware()
        await self.upload_manufacturer_images()
        await self.upload_product_images()
    
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
                        await asyncio.sleep(random.randint(5, 25))
                        print('asyncio slept well')
                        
    @staticmethod
    async def fetch_url_with_playwright(url): ...


if __name__ == "__main__":
    self = Core('FahrradXXL')

