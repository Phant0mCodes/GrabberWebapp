import html
import random
import re
import json
from hashlib import md5
from dataclasses import asdict
from lxml import etree
from parser.Core import Core
from parser.models import (
    Product, 
    ProductMessages, 
    Features, 
    GrabSettings, 
    Category, 
    Image,
    ProductReview
)
from bs4 import BeautifulSoup as Bs
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
from asgiref.sync import sync_to_async


class FahrradXXL(Core):
    HOSTNAME = 'https://fahrrad-xxl.de'    
    FEATURES = Features(
        child_category_scanner=False,
        variation_support=True,
        price_filter=True,
        page_limit=True,
        eek=False,
        all_products=False
    )
    PARSER_NAME = 'FahrradXXL'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __process_child_category__(self, jobs, future): ...

    async def scan_child_categories(self, category_url: str):
        # category = Category.objects.aget(pk=category_url)
        category = Category(pk=category_url)
        category.has_products = True
        await category.asave()
        self.child_category_urls.add(category_url)

    async def __process_category__(self, category_url) -> (int, list, set):
        # product_amount, category_page_urls, product_urls (from first page)
        if '?' in category_url:
            parsed = urlparse(category_url)
            query = parsed.query
            parsed = parsed._replace(query=urlencode('', True))
            category_url = urlunparse(parsed)

        else:

            if not category_url.endswith('/'):
                category_url += '/'

            f = self.settings.min_price
            t = self.settings.max_price
            query = urlencode({
                'pfrom': f,
                'pto': t,
                'punit': '€',
                'o': 'popularity'
            })

        response = await self.fetch_url(f'{category_url}?{query}')
        soup = Bs(response.content, 'lxml')

        item_amount = int(soup.select_one('.fxxl-warengruppe-category__info--header-quantity').text)

        product_urls = self.get_product_urls(soup)
        pages = soup.select('.fxxl-pager-bottom__item')
        if pages:
            pages_amount = int(pages[-2].a.text)
        else:
            pages_amount = 1

        category_page_urls = [
            f"{category_url}seite/{p}/?{query}"
            for p in range(2, pages_amount + 1)
        ]

        return item_amount, category_page_urls, product_urls

    def get_product_urls(self, soup: Bs) -> set:
        return set(
            a['href'] for a in soup.select('.fxxl-element-artikel>a')
        )

    async def get_product_data(self, soup: Bs, url=None) -> (Product, str):
        message = ProductMessages.saved
        category = await self.get_category(soup)
        product = Product(
            source_url=url, 
            category=category,
            source_shop=self.PARSER_NAME,            
        )
        
        try:
            base_jsons = soup.select_one('script:-soup-contains("utag_data_init"):-soup-contains("PageType")').string.strip().split(';')
            # json_0 = json.loads(base_jsons[1].replace('utag_data_init = ', ''))
            json_0 = json.loads(base_jsons[3].replace('utag_data_init = ', ''))
            json_1 = json.loads(soup.select_one('script[type="application/ld+json"]:-soup-contains("Product")').string)
        except:
            pass
            return None, ProductMessages.no_js
        
        script_tags = soup.find_all('script', text=True)

        for script_tag in script_tags:
            if 'additional_data' in script_tag.string and '{"xref":' in script_tag.string:
                script_content = script_tag.string
                match = re.search(r'additional_data\s*=\s*({.*?});', script_content, re.DOTALL)
                if match:
                    json_str = match.group(1)
                    additional_data = json.loads(json_str)
                    break
            else:
                pass
     
        json_1 = [json_1] if json_1.__class__ is dict else json_1
        
        product.name = str(soup.find('h1', class_="fxxl-artikel-detail__product_name").string)
        product.sku = json_0['ecommerce']['detail']['products'][0]['product_id']
        product.product_number = product.sku
        product.ean = None
        product.manufacturer_number = None
        product.manufacturer_name = json_0['ecommerce']['detail']['products'][0]['brand']
        manufacturer_image_tag = soup.select_one(f'img[title="{product.manufacturer_name}"]')
        manufacturer_image = Image(
            url=manufacturer_image_tag['data-src'],
            filename=f'{product.manufacturer_name}_logo',
            source_shop=self.PARSER_NAME,
            image_type='manufacturer_image'
        ) if manufacturer_image_tag else None
        
        product.manufacturer_image = manufacturer_image
            
        description_html = soup.select_one('#pvd-d')
        if description_html:
            description_html.select_one('#artikel-description-more-button').decompose()
            description_html.select_one('.fxxl-artikel-detail__section_header1').decompose()
            description_html = str(description_html)
        else:
            description_html = ''
            
        product.html_description = description_html

        description_tail = soup.select_one('#pvd-properties-cnt')
        if description_tail:
            el = description_tail.select_one('.fxxl-artikel-detail__property-error-report')
            if el:
                el.decompose()
            el = description_tail.find('div', text=re.compile(' Anleitungen und Zubehör '))
            if el:
                el.parent.decompose()

            description_tail['class'] = 'grng_detail_attributes'
            for div in description_tail.select('div'):
                if 'data-key' in div.attrs:
                    del div['data-key']
                if 'fxxl-artikel-detail__grouping-properties-grid' in div['class']:
                    div['class'] = 'grng_grid'
                elif 'fxxl-artikel-detail__grouping-properties-title' in div['class']:
                    div['class'] = 'grng_title'
                elif 'fxxl-artikel-detail__grouping-properties-grid-item' in div['class']:
                    div['class'] = 'grng_item'
            description_tail = '<h3 class="grng_header">Eigenschaften</h3>' + str(description_tail)
        else:
            description_tail = ''

        product.details_description = description_tail
        
        subbed_sku = re.sub('\W', '', product.sku) 
        alt_name = re.sub('[/\s\W]+', '-', html.unescape(product.name))
        rnd = random.randint(10000, 99999)               
        main_image = Image(
            url=soup.select_one('.fxxl-artikel-detail-slider1__item[data-idx="0"] > img[data-src]')['data-src'],
            filename=f"{subbed_sku}{rnd}_product_image_{alt_name}_{'1'.zfill(2)}",
            source_shop=self.PARSER_NAME,
            # for_product=product,
            image_type='product_image'
        )
                
        product.main_image = main_image

        product_images = [main_image]
        reviews = [
            ProductReview(
                id=rev['data-id'],
                for_product=product,
                title=rev.select_one('.pvd-r__review-author').text.strip(),
                content=re.sub('\s{2}', '\n', rev.select_one('.pvd-r__review-comment').text.strip()),
                points=rev['data-stars'],
                time=rev['data-published'] + '+02:00'
            )
            for rev in soup.select('.pvd-r__review')
        ]
                
        product.shipping_tags = ['STANDARD']
        # child_dict data
        product.product_type = 'parent'
        child_products = {}
        for child_dict in json_1:

            child_product: Product = Product(
                source_url=child_dict['sku'], 
                product_type='child'
                )
            child_product.source_shop = product.source_shop
            child_product.manufacturer_name = product.manufacturer_name
            child_product.parent = product
            child_product.manufacturer_image = product.manufacturer_image
            child_product.category = product.category
            child_product.shipping_tags = product.shipping_tags
            
            child_product.sku = child_dict['sku'].upper()
            child_product.product_number = child_product.sku
            child_product.name = child_dict['name']
            
            child_id = soup.find('div', {"data-artnum": child_product.product_number})["data-vid"]

            uvp_element = soup.select_one('div.fxxl-strike-price')
            uvp_string = uvp_element.text.replace(',-', ',00') if uvp_element else None
            child_product.strike_price = additional_data[child_id]['ecommerce']['add']['products'][0]['org_price']
            child_product.price = float(child_dict['offers']['price'])
            
            try: child_product.ean = child_dict['gtin13']
            except KeyError: pass

            var_values_tag = soup.find('div', class_="artikel_filial_matrix-list__container")
            color = var_values_tag.find('div', {
                'data-product-id': child_id}).find('div', class_=re.compile('color-code'))
            color = color.text.strip()
            if not color:
                color = 'basic'
            size = var_values_tag.find('div', {
                'data-product-id': child_id})['data-size']
            child_product.options = dict(Farbe=color, Größe=size)

            images_tag = soup.find('div', class_="fxxl-artikel-detail__images-box fxxl-container-mwd0")

            images_script = (images_tag.find(
                'div', {
                    'data-artnum': child_product.product_number.upper()}).script.string.split(';')[1].split(' =')[1].strip()).replace(
                '\n', '')

            image_urls = [img_data['src'] for img_data in eval(images_script)]
            subbed_sku = re.sub('\W', '', child_product.sku)
            alt_name = html.unescape(child_product.name)
            alt_name = re.sub('[/\s\W]+', '-', alt_name)
            rnd = random.randint(10000, 99999)
            image_filenames: list = [
                f"{subbed_sku}{rnd}_product_image_{alt_name}_{str(p + 1).zfill(2)}"
                for p in range(len(image_urls))
            ]
            
            child_product_images = [
                Image(
                    url=url,
                    filename=f"{subbed_sku}{rnd}_product_image_{alt_name}_{str(i + 1).zfill(2)}",
                    source_shop=self.PARSER_NAME,
                    # for_product=child_product,
                    image_type='product_image'
                )
                for i, url in enumerate(image_urls, start=2)
            ]
            
            child_products[child_product] = child_product_images
            
            
        return product, product_images, reviews, child_products, message

    async def get_category(self, soup) -> Category:
        parent_category = Category(
            source_url=self.HOSTNAME,
            source_shop=self.PARSER_NAME,
            name=self.PARSER_NAME,
            path=self.PARSER_NAME,
            parent=None
        )
        
        # await parent_category.asave()
        
        category_path = [self.PARSER_NAME]
        for li in soup.select('.fxxl-breadcrumb__element')[1:-1]:
            category_path += [li.a.string]
            category = Category(
                source_url=li.a['href'],
                source_shop=self.PARSER_NAME,
                name=li.a.string,
                path=category_path,
                parent=parent_category
            )
            
            parent_category = category            
            # await category.asave()
        
        return category
    
    async def get_product_images(self, soup) -> list[Image]:
        ...
    
if __name__ == "__main__":
    self = FahrradXXL()

