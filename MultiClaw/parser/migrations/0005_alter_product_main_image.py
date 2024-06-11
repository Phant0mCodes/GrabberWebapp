# Generated by Django 5.0.6 on 2024-06-06 19:19

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parser', '0004_alter_product_details_description_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='product',
            name='main_image',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='main_image_of', to='parser.image'),
        ),
    ]