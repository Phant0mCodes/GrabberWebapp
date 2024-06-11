from unittest.mock import patch
from django.test import TestCase
from parser.Core import Core

class CoreModuleTest(TestCase):

    def setUp(self):
        self.core = Core()
        core.product_url_list = [
            'https://www.fahrrad-xxl.de/flyer-gotour3-7-43-m000068761',
            'https://www.fahrrad-xxl.de/cube-reaction-hybrid-performance-500-m000065440',
            'https://www.fahrrad-xxl.de/cube-nuroad-pro-m000065407'
        ]
        
    def test_download_products(self):
        product_urls = ['url1', 'url2']
        result = self.core.download_products(product_urls)
        expected_result = ... # Define your expected result
        self.assertEqual(result, expected_result)

    # def test_grab_single_category(self):
    #     # Replace 'category' with an appropriate test category
    #     category = 'test_category'
    #     result = self.core.grab_single_category(category)
    #     expected_result = ... # Define your expected result
    #     self.assertEqual(result, expected_result)

    # def test_scan_single_child_category(self):
    #     category = 'test_category'
    #     result = self.core.scan_single_child_category(category)
    #     expected_result = ... # Define your expected result
    #     self.assertEqual(result, expected_result)

    # def test_scan_child_categories(self):
    #     parent_category = 'test_parent_category'
    #     result = self.core.scan_child_categories(parent_category)
    #     expected_result = ... # Define your expected result
    #     self.assertEqual(result, expected_result)

    # def test_get_product_urls_from_category(self):
    #     category = 'test_category'
    #     result = self.core.get_product_urls_from_category(category)
    #     expected_result = ... # Define your expected result
    #     self.assertEqual(result, expected_result)


