# Generated by Django 5.0.6 on 2024-06-24 07:42

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parser', '0025_image_uploaded_to_shops'),
    ]

    operations = [
        migrations.AlterField(
            model_name='product',
            name='manufacturer_image',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='manufacturer_images', to='parser.image'),
        ),
    ]