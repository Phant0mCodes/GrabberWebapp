# myapp/models.py
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models
from django.utils import timezone

class CustomUser(AbstractUser):
    jabber_address = models.CharField(max_length=255, blank=True, null=True)

    groups = models.ManyToManyField(Group, related_name='customuser_set', blank=True)
    user_permissions = models.ManyToManyField(Permission, related_name='customuser_set', blank=True)
    tos_accepted = models.BooleanField(default=True)
    credits_amount = models.IntegerField(default=0)
    def __str__(self):
        return self.username

class BitcoinAddress(models.Model):
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('confirmed', 'Confirmed'),
        ('canceled', 'Canceled'),
        ('transfered', 'Transfered'),
    ]
    
    """
    STATUS CHOICES:
    :pending: User created a new address to topup.
    :paid: User made a transfer of the right mount of funds
    :confirmed: Transaction got 3/3 confirmations
    :canceled: Topup process canceled due to User cancelation or 60 minutes overdue
    :transfered: funds trannsfered to cold wallet
    """
    
    user = models.ForeignKey(CustomUser, on_delete=models.DO_NOTHING)
    private_key = models.CharField(max_length=150)
    transaction = models.CharField(max_length=255, default=None, null=True)
    public_address = models.CharField(max_length=150)
    creation_time = models.DateTimeField(default=timezone.now)
    amount = models.DecimalField(max_digits=100, decimal_places=8)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    confirmations = models.IntegerField(default=0)
    
    def is_expired(self):
        expiration_time = self.creation_time + timezone.timedelta(minutes=60)
        return timezone.now() > expiration_time