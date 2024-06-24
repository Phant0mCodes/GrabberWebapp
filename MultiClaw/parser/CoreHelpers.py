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


def generate_random_product_number(pre):
    number = random.randint(1000000, 9999999)
    tail = random.randint(10000, 99999)
    return f'{pre}{number}{tail}'


def generate_seo_description(description_html):
    unwrapped = re.sub('Beschreibung\W+', '', Bs(description_html, 'lxml').text)
    unwrapped = re.sub('\n+', ' - ', unwrapped)[:165]
    unwrapped = re.sub('.{3}$', '...', unwrapped)
    return unwrapped


def generate_seo_title(product_name):
    return re.sub(r'[^\w\s]\s*', '', product_name) + ' - kaufen'


def clean_category_url(url):
    if url.endswith('/'):
        url = url[:-1]
    # return url.split('?')[0]
    return url