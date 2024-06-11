from dataclasses import dataclass, field
from django.db import models
from enum import Enum
from users.models import CustomUser
from uuid import uuid4

class Category(models.Model):
    source_url = models.CharField(primary_key=True, max_length=2550)
    source_shop = models.CharField(max_length=255)
    name = models.CharField(max_length=255, default=None, null=True)
    path = models.CharField(max_length=1024, default=None, null=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, default=None, related_name='children')
    has_products = models.BooleanField(default=True, blank=True)
    child_urls = models.TextField(default=None, null=True)
    product_urls = models.JSONField(default=None, null=True)


def default_shipping_tags():
    return ['STANDARD']

class Product(models.Model):
    PRODUCT_TYPES = [
        ('single', 'single'),
        ('parent', 'parent'),
        ('child', 'child'),
    ]

    # uuid = models.UUIDField(default=uuid4().hex, unique=True)
    source_url = models.CharField(primary_key=True, max_length=2550, blank=True, unique=True)
    category = models.ForeignKey(Category, on_delete=models.DO_NOTHING, null=True)
    source_shop = models.CharField(max_length=255, null=True)    
    
    product_type = models.CharField(max_length=10, choices=PRODUCT_TYPES, default='single')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, related_name='children')
    main_image = models.ForeignKey('parser.Image', on_delete=models.CASCADE, null=True, related_name='main_image_of')
    images = models.ManyToManyField('parser.Image', blank=True, related_name='image_of')   
     
    name = models.CharField(max_length=255, blank=True)
    sku = models.CharField(max_length=255, default=None, null=True, unique=True)
    product_number = models.CharField(max_length=255, blank=True)
    ean = models.CharField(max_length=255, null=True)
    manufacturer_number = models.CharField(max_length=255, null=True)
    manufacturer_name = models.CharField(max_length=255, null=True)
    manufacturer_image = models.ForeignKey('parser.Image', on_delete=models.CASCADE, null=True)  # need to decide if it is an object or the model
    # manufacturer_image = models.ManyToManyField('parser.Image', null=True)  # need to decide if it is an object or the model

    options = models.JSONField(null=True, default=None)

    strike_price = models.FloatField(max_length=100, default=0)
    price = models.FloatField(max_length=100, default=0)
    short_description = models.TextField(null=True)
    html_description = models.TextField(null=True)
    details_description = models.TextField(null=True)

    energy_class = models.CharField(max_length=1000, null=True, default=None)
    energy_icon_url = models.CharField(max_length=1000, null=True, default=None)
    energy_icon_filename = models.CharField(max_length=1000, null=True, default=None)
    energy_icon_ext = models.CharField(max_length=1000, null=True, default=None)
    energy_label_url = models.CharField(max_length=1000, null=True, default=None)
    energy_label_filename = models.CharField(max_length=1000, null=True, default=None)
    energy_label_ext = models.CharField(max_length=1000, null=True, default=None)
    energy_pdf_url = models.CharField(max_length=1000, null=True, default=None)
    energy_pdf_filename = models.CharField(max_length=1000, null=True, default=None)
    energy_pdf_ext = models.CharField(max_length=1000, null=True, default=None)
    
    purchase_unit = models.FloatField(default=0)
    reference_unit = models.IntegerField(default=0)
    pack_unit = models.CharField(max_length=255, default='ST')
    pack_unit_plural = models.CharField(max_length=255, default='ST')
    unit = models.CharField(max_length=255, null=None, blank=True)
    shipping_tags = models.JSONField(default=list)
    currency = models.CharField(max_length=5, default='EUR')
    weight = models.FloatField(default=None, null=True)
    lenght = models.FloatField(default=None, null=True)
    height = models.FloatField(default=None, null=True)
    width = models.FloatField(default=None, null=True)
    # reviews = models.ManyToManyField('ProductReview', related_name='reviews', blank=True)
    
    
class Image(models.Model):
    IMAGE_TYPES = [
        ('product_image', 'product_image'),
        ('manufacturer_image', 'manufacturer_image'),
        ('other_image', 'other_image'),
    ]
    url = models.CharField(primary_key=True, max_length=1000)
    filename = models.CharField(max_length=1000, default=None)
    source_shop = models.CharField(max_length=255, null=True)    
    # for_product = models.ForeignKey("parser.Product", on_delete=models.CASCADE, related_name='of_product')
    image_type = models.CharField(max_length=100, choices=IMAGE_TYPES)


class ProductReview(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    for_product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    title = models.CharField(max_length=1000)
    content = models.TextField(max_length=5000)
    points = models.FloatField()
    time = models.DateTimeField()
    
    def __str__(self):
        return f'{self.title} - {self.content[:10]} - {self.points} - {self.time}'
    

class Modes(Enum):
    CATEGORY_URLS = 'Category URLs'
    PRODUCT_URLS = 'Product URLs'
    KEYWORDS = 'Keywords'
    ALL_PRODUCTS = 'All products'
    
    def __str__(self):
        return self.value


class GrabSettings(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    parser_name = models.CharField(max_length=100)
    parser_mode = models.CharField(max_length=100, choices=Modes._member_map_.items())
    max_page_amount = models.IntegerField(verbose_name="Max category pages", default=2)
    min_price = models.IntegerField(default=200)
    max_price = models.IntegerField(default=700)
    category_urls = models.TextField(verbose_name="Category URLs", blank=True)
    product_urls = models.TextField(verbose_name="Product URLs", blank=True, default='https://www.fahrrad-xxl.de/carver-drift-e-510-m000009360')
    keywords = models.TextField(verbose_name="Keywords", max_length=1000, blank=True)


class ShopwareShop(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    domain = models.CharField(max_length=255, primary_key=True)
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=255, blank=True)
    valid = models.BooleanField(null=True, default=None)


class ShopwareAccessToken(models.Model):
    shop = models.ForeignKey("parser.ShopwareShop", on_delete=models.CASCADE, primary_key=True)
    token = models.CharField(max_length=255)
    created = models.DateTimeField(auto_now=True)
    valid_until = models.DateTimeField()
    
    
class GrabStatus(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    settings_model = models.ForeignKey(GrabSettings, on_delete=models.CASCADE)
    status = models.CharField(max_length=100, choices=[
        ('active', 'active'),
        ('pending', 'pending'),
        ('running', 'running'),
        ('error', 'error'),
        ('terminated', 'terminated'),
        ('finished', 'finished'),
    ])
    
        
class ProductMessages:
    saved = "PRODUCT SAVED"
    no_ean = 'NO EAN'
    no_js = "NO JSON MINSCRIPT DATA"
    no_cat = "NO CATEGORY FOUND"
    no_price = "NO PRICE"
    no_image = "NO IMAGE"
    no_decode = "JSON DECODE ERROR"
    no_brand = "NO BRAND"
    
    
@dataclass
class Features:
    variation_support: bool = field(default=False, metadata={'field_name': 'Variation support'})
    child_category_scanner: bool = field(default=False, metadata={'field_name': 'Child category scanner'})
    price_filter: bool = field(default=False, metadata={'field_name': 'Price filter'})
    page_limit: bool = field(default=False, metadata={'field_name': 'Page Limit'})
    eek: bool = field(default=False, metadata={'field_name': 'Energy efficiency'})
    all_products: bool = field(default=False, metadata={'field_name': 'All products'})
    