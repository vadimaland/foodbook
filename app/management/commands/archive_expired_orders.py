# app/management/commands/archive_expired_orders.py
from django.core.management.base import BaseCommand
from datetime import datetime
from django.db import transaction
from app.models import order, ArchivedOrder, User, menu, City
import logging
from django.core.mail import EmailMessage
import csv

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Arhiveeri aegunud tellimused, mille staatus on 3'

    def handle(self, *args, **options):
        self.stdout.write('Alustan aegunud tellimuste arhiveerimist...')
        report_data = self.archive_expired_orders()
        self.send_email_report(report_data)
        self.stdout.write('Arhiveerimine lõpetatud.')

    @transaction.atomic
    def archive_expired_orders(self):
        current_time = datetime.now()
        current_year = current_time.year
        current_week = current_time.isocalendar()[1]
        current_day = current_time.isocalendar()[2]

        # Kohanda aastat, kui on esimene nädal, kuid uus aasta pole veel alganud
        if current_week == 1 and current_time.month == 12:
            current_year += 1

        prefix = f"{current_year}{current_week:02d}{current_day:02d}"
        expired_orders = order.objects.filter(order_number__startswith=prefix)

        report_data = []

        for ord in expired_orders:
            if not ArchivedOrder.objects.filter(order_number=ord.order_number).exists():
                # Kogu andmed ArchivedOrder jaoks
                user = ord.user_id
                city = ord.city
                dishes = []
                total_amount = 0

                # Koguge selle tellimuse numbri kohta roogade andmed ja kogusumma
                order_items = order.objects.filter(order_number=ord.order_number)
                for item in order_items:
                    dish = item.menu_id.dish_id
                    # "шт." asendatakse "tk." (tükki)
                    dishes.append(f"{dish.dish_name} ({item.quantity} tk. {dish.dish_price} EUR)")
                    total_amount += item.quantity * dish.dish_price

                dishes_str = ', '.join(dishes)

                # Loo ArchivedOrder kirje
                archived_order = ArchivedOrder(
                    order_number=ord.order_number,
                    user_tabel_number=user.tabel_number,
                    user_username=user.username,
                    dishes=dishes_str,
                    city_name=city.name,
                    total_amount=total_amount,
                    status=3  # Aegunud
                )
                archived_order.save()

                # Kustuta algsed tellimused
                order_items.delete()
                logger.info(f"Arhiveeritud tellimus {ord.order_number} staatus 3-ga.")

                # Lisa aruande andmetesse
                report_data.append({
                    'order_number': ord.order_number,
                    'user_tabel_number': user.tabel_number,
                    'user_username': user.username,
                    'dishes': dishes_str,
                    'city_name': city.name,
                    'total_amount': total_amount,
                    'status': 3
                })
            else:
                logger.warning(f"Tellimus {ord.order_number} on juba arhiveeritud. Jätkan.")
        return report_data

    def send_email_report(self, report_data):
        # Loo CSV sisu
        csv_content = self.generate_csv(report_data, delimiter=',')

        # Valmista e-kirja sõnum
        if report_data:
            email_message = f"Arhiveeritud {len(report_data)} tellimust. Vaata manust CSV faili, et näha üksikasju."
        else:
            email_message = "Selle käivitamise jooksul ühtegi tellimust ei arhiveeritud."

        # Saada e-kiri
        subject = 'Aegunud tellimuste arhiveerimise aruanne'
        from_email = 'sookla@aquaphor.com'
        to_email = ['ee.it@aquaphor.com']

        email = EmailMessage(subject, email_message, from_email, to_email)
        email.attach('archived_orders.csv', csv_content, 'text/csv')
        email.send()

        self.stdout.write(f"E-kirja aruanne saadetud. {len(report_data)} tellimust arhiveeritud.")

    def generate_csv(self, report_data, delimiter=','):
        headers = ['Tellimuse number', 'Kasutaja tabelinumber', 'Kasutaja kasutajanimi', 'Roogad', 'Linna nimi', 'Kogusumma', 'Staatus']
        csv_content = []

        # Lisa päised
        csv_content.append(','.join(headers))

        # Lisa read
        for row in report_data:
            csv_content.append(
                f"{row['order_number']},{row['user_tabel_number']},{row['user_username']},{row['dishes']},{row['city_name']},{row['total_amount']},{row['status']}"
            )

        # Kui andmeid pole, lisa varurida
        if not csv_content[1:]:
            csv_content.append(',,,No archived orders,,,')
        return '\n'.join(csv_content)
