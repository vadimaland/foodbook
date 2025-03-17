# app/management/commands/tabel_number.py
import csv
import io
import codecs
from django.core.management.base import BaseCommand
from django.core.mail import EmailMessage
from app.models import table_number, order, User

class Command(BaseCommand):
    help = 'Uuendab tabelinumbreid SMB jagatud kaustast, kustutab eemaldatud kasutajate tellimused ning saadab e-kirja aruande'

    def handle(self, *args, **kwargs):
        # Failitee mountitud SMB jagatud kaustale
        file_path = '/mnt/smb/tabel_number.csv'

        try:
            # Loeme CSV faili
            with open(file_path, 'r', encoding='utf-8') as file:
                csv_reader = csv.reader(file)
                tabel_numbers = []

                # Jätame vahele tühjad read ja read, kus on vähem veerge
                for row in csv_reader:
                    if len(row) > 0:  # Veendu, et rida ei ole tühi
                        tabel_numbers.append(row[0])  # Eeldades, et esimeses veerus on tabelinumbrid

            # Uuendame andmebaasi
            existing_tabel_numbers = set(table_number.objects.values_list('tabel_number', flat=True))
            new_tabel_numbers = set(tabel_numbers)

            # Leidke uued ja kustutatud tabelinumbrid
            added_tabel_numbers = new_tabel_numbers - existing_tabel_numbers
            deleted_tabel_numbers = existing_tabel_numbers - new_tabel_numbers

            # Kustutame tabelinumbrid, mis enam CSV-s puuduvad
            for tabel_number_to_delete in deleted_tabel_numbers:
                table_number.objects.filter(tabel_number=tabel_number_to_delete).delete()

            # Lisame uued tabelinumbrid
            for tabel_number_to_add in added_tabel_numbers:
                table_number.objects.create(tabel_number=tabel_number_to_add)

            # Leidke kasutajad, kelle tabelinumbrid on kustutatud, ja blokeerige nad
            users_to_block = User.objects.filter(tabel_number__in=deleted_tabel_numbers)
            for user in users_to_block:
                user.blocked = True
                user.save()

            # Leidke kasutajad, kelle tabelinumbrid on kustutatud, ja kustutage nende tellimused
            canceled_orders = []
            for user in users_to_block:
                user_orders = order.objects.filter(user_id=user)
                canceled_orders.extend(user_orders)
                user_orders.delete()

            # Valmistame ette e-kirja sisu
            email_message = f"Tabelinumbrite uuendamise aruanne:\n\n"
            email_message += f"Lisatud tabelinumbrid:\n{', '.join(added_tabel_numbers) if added_tabel_numbers else 'Puudub'}\n\n"
            email_message += f"Kustutatud tabelinumbrid:\n{', '.join(deleted_tabel_numbers) if deleted_tabel_numbers else 'Puudub'}\n\n"
            email_message += f"Blokeeritud kasutajad:\n{', '.join([user.tabel_number for user in users_to_block]) if users_to_block else 'Puudub'}\n\n"

            # Valmistame ette CSV faili tühistatud tellimuste jaoks
            canceled_orders_csv = io.StringIO()
            canceled_orders_writer = csv.writer(canceled_orders_csv)
            canceled_orders_writer.writerow(['Tellimuse number', 'Kasutaja tabelinumber', 'Menüü ID', 'Kogus', 'Linn'])

            for order_obj in canceled_orders:
                canceled_orders_writer.writerow([
                    order_obj.order_number,
                    order_obj.user_id.tabel_number,
                    order_obj.menu_id.id,
                    order_obj.quantity,
                    order_obj.city.name
                ])

            # Lisame CSV sisule BOM-i
            canceled_orders_csv_content = codecs.BOM_UTF8.decode('utf-8') + canceled_orders_csv.getvalue()

            # Saadame e-kirja
            subject = 'Tabelinumbrite uuendamise aruanne'
            from_email = 'sookla@aquaphor.com'
            to_email = ['ee.it@aquaphor.com']

            email = EmailMessage(subject, email_message, from_email, to_email)
            email.attach('canceled_orders.csv', canceled_orders_csv_content, 'text/csv')
            email.send()

            self.stdout.write(self.style.SUCCESS('Tabelinumbrid ja tellimused uuendatud edukalt. E-kiri saadetud.'))
        except Exception as e:
            self.stderr.write(f"Viga: {e}")
