from django.db import models
from django.contrib.auth.models import AbstractUser
from datetime import datetime
from django.core.exceptions import ValidationError
from decimal import Decimal

class City(models.Model):
    name = models.CharField('Linn', max_length=50, blank=False, unique=True)

    def __str__(self):
        return self.name

class User(AbstractUser):
    tabel_number = models.CharField('Töötaja number', max_length=10, blank=False, unique=True)
    blocked = models.BooleanField('Blokeeritud', blank=False, default=False)
    city = models.ForeignKey('City', on_delete=models.PROTECT, related_name='users', default=1)
    balance = models.DecimalField('Saldo', max_digits=5, decimal_places=2, default=0.00)

class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('deposit', 'Sissemakse'),
        ('withdrawal', 'Väljamakse'),
        ('refund', 'Tagastus'),
    ]

    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField('Summa', max_digits=10, decimal_places=2)
    transaction_type = models.CharField('Tehingu tüüp', max_length=10, choices=TRANSACTION_TYPES)
    created_at = models.DateTimeField('Tehingu kuupäev', auto_now_add=True)
    description = models.TextField('Kirjeldus', blank=True)
    payment_reference = models.CharField('Makse identifikaator', max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_transaction_type_display()} - {self.amount} EUR"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Uuendame kasutaja saldot tehingu salvestamisel
        if self.transaction_type == 'deposit':
            self.user.balance += Decimal(str(self.amount))  # Teisendame stringi Decimaliks
        elif self.transaction_type == 'withdrawal':
            self.user.balance -= Decimal(str(self.amount))  # Teisendame stringi Decimaliks
        elif self.transaction_type == 'refund':
            self.user.balance -= Decimal(str(self.amount))  # Teisendame stringi Decimaliks
        self.user.save()

class table_number(models.Model):
    tabel_number = models.CharField('Tabelinumber', max_length=10, blank=False, unique=True)
    def __str__(self):
        return self.tabel_number

class category(models.Model):
    category_name = models.CharField('Kategooria', max_length=25, blank=False)
    def __str__(self):
        return self.category_name

class weekday(models.Model):
    weekday_name = models.CharField('Päev', max_length=15, blank=False)
    def __str__(self):
        return self.weekday_name

class dish(models.Model):
    dish_name = models.CharField('Roog', max_length=50, blank=False)
    dish_price = models.DecimalField('Hind', max_digits=10, decimal_places=2, blank=False)
    category = models.ForeignKey('category', on_delete=models.CASCADE)
    def __str__(self):
        return f"{self.category}, {self.dish_name} ({self.dish_price} EUR)"

class week(models.Model):
    number = models.IntegerField('Nädal', blank=False)
    def __str__(self):
        return str(self.number)

class menu(models.Model):
    week_number = models.ForeignKey('week', on_delete=models.PROTECT)
    weekday_id = models.ForeignKey('weekday', on_delete=models.PROTECT)
    dish_id = models.ForeignKey('dish', on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)  # Lisame loomiskuupäeva välja

    def __str__(self):
        return f"(Nädal {self.week_number}, {self.weekday_id}) {self.dish_id}"

class order(models.Model):
    order_number = models.BigIntegerField('Tellimuse number')
    user_id = models.ForeignKey('User', on_delete=models.PROTECT)
    menu_id = models.ForeignKey('Menu', on_delete=models.PROTECT)
    quantity = models.IntegerField('Kogus', blank=False)
    city = models.ForeignKey('City', on_delete=models.PROTECT, related_name='orders')

    def __str__(self):
        return f"{self.order_number}, {self.user_id}, {self.menu_id}, {self.quantity}, {self.city}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            # Genereerime tellimuse numbri
            current_year = datetime.now().year
            week_number = int(self.menu_id.week_number.number)
            day_number = int(self.menu_id.weekday_id.id)
            tabel_number = int(self.user_id.tabel_number)
            
            # Kui praegune nädal on 52 ja tellimus on nädalale 1, siis suurendame aastat ühe võrra
            if datetime.now().isocalendar()[1] == 52 and week_number >= 1:
                current_year += 1
            elif datetime.now().isocalendar()[1] == 1 and datetime.now().month == 12:
                current_year += 1
            else:
                current_year = current_year

            # Moodustame tellimuse numbri
            self.order_number = int(f"{current_year}{week_number:02d}{day_number:02d}{tabel_number:05d}")
        
        # Kontrollime, kas kasutajal on tellimuse maksmiseks piisavalt vahendeid
        total_amount = self.quantity * self.menu_id.dish_id.dish_price
        if self.user_id.balance >= total_amount:
            # Loome tehingu vahendite lahutamiseks
            Transaction.objects.create(
                user=self.user_id,
                amount=total_amount,
                transaction_type='withdrawal',
                description=f"Makse saldolt tellimuse {self.order_number} eest"
            )
        super().save(*args, **kwargs)
    
class ArchivedOrder(models.Model):
    STATUS_CHOICES = [
        (1, 'Väljastatud'),
        (3, 'Aegunud'),
    ]

    order_number = models.BigIntegerField('Tellimuse number', unique=True)
    user_tabel_number = models.CharField('Kasutaja tabelinumber', max_length=10)
    user_username = models.CharField('Kasutajanimi', max_length=150)
    dishes = models.TextField('Roogad', blank=True)
    city_name = models.CharField('Linn', max_length=50)
    total_amount = models.DecimalField('Tellimuse summa', max_digits=10, decimal_places=2, blank=False)
    archived_at = models.DateTimeField(auto_now_add=True)  # Tellimuse arhiveerimise kuupäev
    status = models.PositiveIntegerField(choices=STATUS_CHOICES, default=3)

    def __str__(self):
        return f"{self.order_number}, {self.user_username}, {self.dishes}, {self.city_name}, {self.total_amount}, Staatus: {self.get_status_display()}"

    def clean(self):
        if self.status not in [1, 2, 3]:
            raise ValidationError("Vigane staatusväärtus.")

    @staticmethod
    def archive_order(order_number):
        # Kasutame otse order mudelit
        order_items = order.objects.filter(order_number=order_number)
        if not order_items.exists():
            return

        user = order_items.first().user_id
        city = order_items.first().city
        total_amount = sum(order_item.quantity * order_item.menu_id.dish_id.dish_price for order_item in order_items)

        dish_list = []
        for order_item in order_items:
            dish = order_item.menu_id.dish_id
            dish_list.append(f"{dish.dish_name} ({order_item.quantity} tk.) ({order_item.menu_id.dish_id.dish_price} EUR)")

        dishes_str = ', '.join(dish_list)

        ArchivedOrder = ArchivedOrder.objects.create(
            order_number=order_number,
            user_tabel_number=user.tabel_number,
            user_username=user.username,
            dishes=dishes_str,
            city_name=city.name,
            total_amount=total_amount,
            status=3  # Vaikimisi staatus on 'Paid'
        )

        order_items.delete()
