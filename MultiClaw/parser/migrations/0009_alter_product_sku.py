# Generated by Django 5.0.6 on 2024-06-06 20:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parser', '0008_product_options'),
    ]

    operations = [
        migrations.AlterField(
            model_name='product',
            name='sku',
            field=models.CharField(default=None, max_length=255, null=True, unique=True),
        ),
    ]
