# Generated by Django 5.0.6 on 2024-06-06 18:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parser', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='product',
            name='ean',
            field=models.CharField(max_length=255, null=True),
        ),
    ]
