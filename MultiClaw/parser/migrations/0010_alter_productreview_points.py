# Generated by Django 5.0.6 on 2024-06-08 11:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parser', '0009_alter_product_sku'),
    ]

    operations = [
        migrations.AlterField(
            model_name='productreview',
            name='points',
            field=models.FloatField(),
        ),
    ]
