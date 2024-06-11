from parser import Core


class Quelle(Core.Core):
    HOSTNAME = 'https://quelle.de'
    FEATURES = Core.Features(
        child_category_scanner=True,
        variation_support=True,
        price_filter=True,
        page_limit=True,
        eek=True,
        all_products=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def __process_category__(self, category_url) -> (int, list, set):
        f = self.settings.min_price
        t = self.settings.max_price
        filter_string = f'{{"filter_price":["{f}-{t}"]}}'
        filter_string_bytes = filter_string.encode()
        tail = '?f=' + base64.urlsafe_b64encode(filter_string_bytes).decode()

        pl = {
            'f': base64.urlsafe_b64encode(filter_string.encode()).decode()
        }
        category_url += tail
        response = await self.fetch_url(category_url)
        soup = Bs(response.content, 'lxml')
        scr = json.loads(soup.select_one('#__NEXT_DATA__').text)
        result = scr['props']['pageProps']['fallback']['search-api-result']['searchresult']['result']

        product_amount = result['count']

        product_urls = self.get_product_urls(result)

        pages = int(product_amount / 72) + 1 if product_amount % 72 != 0 else int(product_amount / 72)
        if self._conf.max_pages:
            pages = self._conf.max_pages_amount if self._conf.max_pages_amount < pages else pages

        category_page_urls = [
            f'{category_url}&p={p}' for p in range(2, pages + 1)
        ]

        return product_amount, category_page_urls, product_urls

    def __process_category_page__(self, response: requests.Response) -> list:
        if response.status_code == 500:
            return []
        soup = Bs(response.content, 'lxml')
        scr = json.loads(soup.select_one('#__NEXT_DATA__').text)
        result = scr['props']['pageProps']['fallback']['search-api-result']['searchresult']['result']
        return self.get_product_urls(result)
    
    def get_product_urls(self, result: dict) -> list:
        return list(
            f"{self.hostname}/p/{product['masterSku']}"
            for product in result['products']
        )
        
    def get_product_data(self, soup: Bs, url) -> (Product, str):


        message = msg.saved

        js = json.loads(soup.select_one('#__NEXT_DATA__').string)
        res = js['props']['pageProps']['urqlState']

        to_js = iter(res)
        js = res[next(to_js)]
        while 'product' not in js['data']:
            js = res[next(to_js)]
        js = json.loads(js['data'])['product']

        # DEFINE VARIABLES
        category_string = soup.select_one('script:-soup-contains("itemListElement")').text
        category_js = json.loads(category_string)
        category: list = ['QUELLE'] + [item['item']['name'] for item in category_js['itemListElement']][1:]
        product_number: str = self.pre + str(random.randrange(10000000, 99999999)) + str(random.randrange(10000, 99999))
        sku: str = js['akl']
        ean: str = js['ean']
        manufacturer_number: str = ''
        strike_price: float = js['price']['valueOld'] / 100 if js['price']['valueOld'] is not None else 0
        purchase_price: float = js['price']['value'] / 100

        description_html = js['longDescription']

        description_tail = '<h3>Technische Daten</h3>'
        description_tail += f'\n<div class="features_attributes">'

        for group in js['oocv']:
            headline = group['headline']

            description_tail += f'\n\t<table class="attributes_features_table aft">'
            description_tail += f'\n\t\t<thead class="aft_caption">'
            description_tail += f'\n\t\t\t<tr>'
            description_tail += f'\n\t\t\t\t<th>{headline}</th>'
            description_tail += f'\n\t\t\t\t<th></th>'
            description_tail += f'\n\t\t\t</tr>'
            description_tail += f'\n\t\t</thead>'
            description_tail += '\n\t\t<tbody>'

            for row in group['rows']:
                description_tail += '\n\t\t\t<tr>'
                description_tail += f'\n\t\t\t\t<td class="aft_name"><div>{row["key"]}</div></td>'
                description_tail += f'\n\t\t\t\t<td class="aft_values">'

                values = row['value'].splitlines()

                for value in values:
                    description_tail += f'\n\t\t\t\t\t<div>{value}</div>'
                description_tail += '\n\t\t\t\t</td>'
                description_tail += '\n\t\t\t</tr>'

            description_tail += '\n\t\t</tbody>'
            description_tail += '\n\t</table>'
        description_tail += '\n</div>'
        description_tail = description_tail.expandtabs(4)

        short_description_element = soup.select_one('[data-testid="sellingpoints"]')
        if short_description_element:
            if 'data-testid' in short_description_element.attrs:
                del short_description_element.attrs['data-testid']
            short_description_element.attrs['class'] = 'attributes_selling_points'
            short_description: str = str(short_description_element)
        else:
            short_description = ''

        short_description = '<div class="product__short__description__ql">'
        short_description += '<ul class="selling__points">'
        for point in js['sellingPoints']:
            short_description += f'<li>{point}</li>'
        short_description += '</ul></div>'

        properties: dict = {}
        manufacturer_name: str = js['brand']['name'] if js['brand'] is not None else 'NoName'
        manufacturer_image_url: str = js['brand']['image'] if js['brand'] is not None else ''
        product_name: str = js['name'].replace('»', '"').replace('«', '"')
        image_urls: list = [item['url'] for item in js['media'] if item['type'] == 'IMAGE']

        subbed_sku = re.sub(r'\D', '', sku)
        alt_name = re.sub('[/\s\W]+', '-', html.unescape(product_name))
        image_filenames: list = [
            f"{subbed_sku}_product_image_{alt_name}_{str(p + 1).zfill(2)}"
            for p in range(len(image_urls))
        ]
        purchase_unit: int = 0
        reference_unit: int = 1
        pack_unit: str = 'ST'
        pack_unit_plural: str = 'ST'
        unit: str = ''
        children: list[Child.__dict__] = []

        en = False if not js['powerEfficiencyFlags'] else True

        if en:
            energy_data = js['powerEfficiencyFlags'][0]

            energy_class: str = energy_data['level']
            energy_icon_filename: str = f"{energy_class}.png"
            energy_icon_url: str = self.energy_icons[energy_class]
            energy_icon_ext: str = ''
            energy_label_filename: str = f"{md5(product_number.encode()).hexdigest()}_EEK_LABEL.jpg"
            energy_label_url: str = energy_data['link']
            energy_label_ext: str = ''
            energy_pdf_filename: str = f"{md5(product_number.encode()).hexdigest()}_EEK_DATENBLATT.pdf"
            datasheet_datas = js['downloads']
            iter_energy_data = iter(datasheet_datas)
            energy_pdf_data = None
            energy_pdf_url_type = None
            while energy_pdf_url_type != 'PRODUCT_DATASHEET':
                energy_pdf_data = next(iter_energy_data)
                energy_pdf_url_type = energy_pdf_data['type']
            energy_pdf_url: str = energy_pdf_data['link']
            energy_pdf_ext: str = ''

        else:
            energy_class = energy_icon_filename = energy_label_filename = energy_pdf_filename = \
                energy_icon_url = energy_label_url = energy_pdf_url = energy_icon_ext = \
                energy_label_ext = energy_pdf_ext = ''

        currency = 'EUR'
        shipping = js['delivery']['deliverySize']
        match shipping:
            case 'DEFAULT':
                shipping_tags = ['STANDARD']
            case 'S' | 'L':
                shipping_tags = ['SPEDITION']
            case _:
                print(f'shipping type is {shipping}, need to handle, fallback to STANDARD')
                shipping_tags = ['STANDARD']

        review_count = js['seoRating']['product']['reviewCount']
        if review_count:
            reviews = self.get_product_reviews(js['akl'])
        else:
            reviews = []

        product_data = Product(
            url=url,
            category=category,  # list of category hierarchy
            product_number=product_number,
            sku=sku,
            ean=ean,
            manufacturer_number=manufacturer_number,
            strike_price=strike_price,  # UVP
            purchase_price=purchase_price,  # actual price
            description_html=description_html,
            description_tail=description_tail,
            short_description=short_description,
            properties=properties,
            manufacturer_name=manufacturer_name,
            manufacturer_image_url=manufacturer_image_url,
            product_name=product_name,
            energy_class=energy_class,
            energy_icon_filename=energy_icon_filename,  # really png ?
            energy_icon_url=energy_icon_url,  # really png ?
            energy_icon_ext=energy_icon_ext,
            energy_label_filename=energy_label_filename,
            energy_label_url=energy_label_url,
            energy_label_ext=energy_label_ext,
            energy_pdf_filename=energy_pdf_filename,
            energy_pdf_url=energy_pdf_url,
            energy_pdf_ext=energy_pdf_ext,
            image_urls=image_urls,
            image_filenames=image_filenames,
            purchase_unit=purchase_unit,  # shows "content: x" in frontend
            reference_unit=reference_unit,
            pack_unit=pack_unit,
            pack_unit_plural=pack_unit_plural,
            unit=unit,
            children=children,
            currency=currency,
            shipping_tags=shipping_tags,
            reviews=reviews,
        )

        all_variation_skus = {
            v['sku']
            for child in js['dimensions']
            for v in child['values']
        }

        if len(all_variation_skus) == 1:
            pass
            # child = __extract_child__(soup, js)
            # product_data.children.append(child)

        elif len(all_variation_skus) > 1:

            blanco_url_element = soup.select_one('link[rel="canonical"]')
            blanco_url = blanco_url_element['href'] if 'quelle.de' in blanco_url_element['href'] else f"{self.hostname}{blanco_url_element['href']}"
            first_child_urls = {
                f"{blanco_url}/?sku={sku}"
                for sku in all_variation_skus
            }
            second_child_urls = set()
            with ThreadPoolExecutor(max_workers=12) as executor:
                jobs = [
                    executor.submit(self.fetch_url, url)
                    for url in first_child_urls
                ]
                for future in futures.as_completed(jobs):
                    response = future.result()
                    soup = Bs(response.content, 'lxml')

                    js = json.loads(soup.select_one('#__NEXT_DATA__').string)
                    res = js['props']['pageProps']['urqlState']
                    to_js = iter(res)
                    js = res[next(to_js)]
                    while 'product' not in js['data']:
                        js = res[next(to_js)]
                    js = json.loads(js['data'])['product']

                    more_skus = {
                        v['sku']
                        for child in js['dimensions']
                        for v in child['values']
                    }
                    more_child_urls = {
                        f"{blanco_url}/?sku={sku}"
                        for sku in more_skus
                    }
                    second_child_urls.update(more_child_urls)

                    child = self.__extract_child__(soup, js)

                    if child not in product_data.children:
                        product_data.children.append(child)

            second_child_urls.difference_update(first_child_urls)

            with ThreadPoolExecutor(max_workers=12) as executor:
                jobs = [
                    executor.submit(self.fetch_url, url)
                    for url in second_child_urls
                ]
                for future in futures.as_completed(jobs):
                    response = future.result()
                    soup = Bs(response.content, 'lxml')

                    js = json.loads(soup.select_one('#__NEXT_DATA__').string)
                    res = js['props']['pageProps']['urqlState']
                    to_js = iter(res)
                    js = res[next(to_js)]
                    while 'product' not in js['data']:
                        js = res[next(to_js)]
                    js = json.loads(js['data'])['product']

                    child = self.__extract_child__(soup, js)

                    if child not in product_data.children:
                        product_data.children.append(child)

        else:
            print(f"len of all variation SKUs is not 1 and not greater then one (must be 0, need to check)")

        product_data.children = [child.__dict__ for child in product_data.children if child is not None]

        return product_data, message

    def __extract_child__(self, soup: Bs, js) -> Union[Child, None]:
        name: str = js['name']
        sku: str = js['sku']
        product_number: str = self.pre + str(random.randrange(10000000, 99999999)) + str(random.randrange(10000, 99999))
        ean: str = js['ean']
        mpn: str = ''
        strike_price: float = js['price']['valueOld'] / 100 if js['price']['valueOld'] is not None else 0
        purchase_price: float = js['price']['value'] / 100
        try:
            options: dict = {
                option['displayName']: [
                    value['displayText']
                    for value in option['values']
                    if value['isSelected']
                ][0]
                for option in js['dimensions']
            }
        except IndexError:
            pass
            return None

        for key in options.copy():
            if not key:
                del options[key]

        description_html = js['longDescription']
        description_tail = '<h3>Technische Daten</h3>'
        description_tail += f'\n<div class="features_attributes">'

        for group in js['oocv']:
            headline = group['headline']

            description_tail += f'\n\t<table class="attributes_features_table aft">'
            description_tail += f'\n\t\t<thead class="aft_caption">'
            description_tail += f'\n\t\t\t<tr>'
            description_tail += f'\n\t\t\t\t<th>{headline}</th>'
            description_tail += f'\n\t\t\t\t<th></th>'
            description_tail += f'\n\t\t\t</tr>'
            description_tail += f'\n\t\t</thead>'
            description_tail += '\n\t\t<tbody>'

            for row in group['rows']:
                description_tail += '\n\t\t\t<tr>'
                description_tail += f'\n\t\t\t\t<td class="aft_name"><div>{row["key"]}</div></td>'
                description_tail += f'\n\t\t\t\t<td class="aft_values">'

                values = row['value'].splitlines()

                for value in values:
                    description_tail += f'\n\t\t\t\t\t<div>{value}</div>'
                description_tail += '\n\t\t\t\t</td>'
                description_tail += '\n\t\t\t</tr>'

            description_tail += '\n\t\t</tbody>'
            description_tail += '\n\t</table>'
        description_tail += '\n</div>'
        description_tail = description_tail.expandtabs(4)

        short_description_element = soup.select_one('[data-testid="sellingpoints"]')
        if short_description_element:
            if 'data-testid' in short_description_element.attrs:
                del short_description_element.attrs['data-testid']
            short_description_element.attrs['class'] = 'attributes_selling_points'
            short_description: str = str(short_description_element)
        else:
            short_description = ''

        short_description = '<div class="product__short__description__ql">'
        short_description += '<ul class="selling__points">'
        for point in js['sellingPoints']:
            short_description += f'<li>{point}</li>'
        short_description += '</ul></div>'

        image_urls: list = [item['url'] for item in js['media'] if item['type'] == 'IMAGE']
        subbed_sku = re.sub(r'\D', '', sku)
        alt_name = re.sub('[/\s\W]+', '-', html.unescape(name))
        image_filenames: list = [
            f"{subbed_sku}_product_image_{alt_name}_{str(p + 1).zfill(2)}"
            for p in range(len(image_urls))
        ]
        purchase_unit: int = 0
        reference_unit: int = 1
        pack_unit: str = 'ST'
        pack_unit_plural: str = 'ST'
        unit: str = ''
        currency = 'EUR'

        return Child(
            name=name,
            product_number=product_number,
            sku=sku,
            ean=ean,
            manufacturer_number=mpn,
            strike_price=strike_price,
            purchase_price=purchase_price,
            options=options,  # ?
            description_html=description_html,
            description_tail=description_tail,
            image_urls=image_urls,
            image_filenames=image_filenames,
            purchase_unit=purchase_unit,  # shows "content: x" in frontend
            reference_unit=reference_unit,
            pack_unit=pack_unit,
            pack_unit_plural=pack_unit_plural,
            unit=unit,
            currency=currency,
        )

    def get_product_reviews(self, akl: str) -> list[dict]:
        """
        :akl = Quelle product ID for the parent product
        """
        review_url = f'https://www.quelle.de/_next/data/shopping_app/de/p/{akl}/rating.json'
        headers = {
            'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
        }

        response = requests.get(review_url, headers=headers)

        res = response.json()['pageProps']['urqlState']

        to_js = iter(res)
        js = res[next(to_js)]
        while 'rating' not in json.loads(js['data']):
            js = res[next(to_js)]
        js = json.loads(js['data'])['rating']

        data = js['product']['reviews']

        return [
            {
                'title': rev['title'] if rev['title'] else '   ',
                'content': rev['description'] if rev['description'] else '   ',
                'points': rev['rating'],
                'time': f"{rev['created']} {random.randint(0, 24)}:{random.randint(0, 59)}:{random.randint(0, 59)}",
            }
            for rev in data
        ]
