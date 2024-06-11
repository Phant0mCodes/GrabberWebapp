from django.contrib import admin
from .models import CustomUser, BitcoinAddress

# Register your models here.
admin.site.register(CustomUser)
admin.site.register(BitcoinAddress)