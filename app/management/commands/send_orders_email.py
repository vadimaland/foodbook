# app/management/commands/send_orders_email.py

import io
import csv
import codecs
from datetime import timedelta
from django.utils import timezone
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from app.models import order, category, dish  # Impordime mudelid


class Command(BaseCommand):
    help = "Saadab e-kirja järgmise tööpäeva tellimustega."

    def get_next_working_day(self, date):
        """
        Tagastab järgmise tööpäeva, kui antud päev on puhkuspäev.
        """
        while date.weekday() >= 5:  # 5 - laupäev, 6 - pühapäev
            date += timedelta(days=1)
        return date

    def handle(self, *args, **kwargs):
        # Saame homme oleva päeva
        tomorrow = timezone.now() + timedelta(days=1)

        # Kui homme on puhkuspäev, nihutame järgmisele tööpäevale
        next_working_day = self.get_next_working_day(tomorrow)

        # Moodustame order_number järgmise tööpäeva jaoks
        year = next_working_day.year
        week = next_working_day.isocalendar()[1]  # Saame nädala numbri
        day = next_working_day.isocalendar()[2]  # Saame nädala päeva numbri

        # Moodustame order_number eesliite
        order_number_prefix = f"{year:04d}{week:02d}{day:02d}"

        # Filtreerime järgmise tööpäeva tellimused
        orders = order.objects.filter(order_number__startswith=order_number_prefix)

        # Loome mällu CSV faili lähteandmete jaoks
        data_csv_file = io.StringIO()
        data_writer = csv.writer(data_csv_file)

        # Pealkirjad lähteandmetele
        data_writer.writerow(['Linn', 'Tellimuse number', 'Kategooria', 'Roog', 'Kogus', 'Hind'])

        # Täidame CSV faili lähteandmetega
        for order_item in orders:
            menu_item = order_item.menu_id  # Saame Menu objekti
            dish_item = menu_item.dish_id  # Saame Dish objekti
            category_item = dish_item.category  # Saame Category objekti
            dish_price = dish_item.dish_price  # Saame roa hinda

            data_writer.writerow([
                order_item.city.name,
                order_item.order_number,
                category_item.category_name,
                dish_item.dish_name,
                order_item.quantity,
                dish_price
            ])

        # Lisame lähteandmete stringi algusesse BOM-i
        data_csv_content = codecs.BOM_UTF8.decode('utf-8') + data_csv_file.getvalue()

        # Loome mällu CSV faili detailsete tellimuste jaoks
        csv_file = io.StringIO()
        writer = csv.writer(csv_file)

        # Pealkirjad detailsete tellimuste CSV-failile
        writer.writerow(['Linn', 'Kategooria', 'Roog', 'Kogus', 'Hind', 'Summa'])

        # Täidame CSV faili detailsete andmetega
        for order_item in orders:
            menu_item = order_item.menu_id  # Saame Menu objekti
            dish_item = menu_item.dish_id  # Saame Dish objekti
            category_item = dish_item.category  # Saame Category objekti
            dish_price = dish_item.dish_price  # Saame roa hinda
            total_cost = order_item.quantity * dish_price  # Rea summa

            writer.writerow([
                order_item.city.name,
                category_item.category_name,
                dish_item.dish_name,
                order_item.quantity,
                dish_price,
                total_cost  # Rea summa
            ])

        # Lisame detailsete tellimuste stringi algusesse BOM-i
        csv_content = codecs.BOM_UTF8.decode('utf-8') + csv_file.getvalue()

        # Kokku võtame roogade arvu ja kogukulu linnade, kategooriate ja roogade nimetuste kaupa
        city_category_dish_count = {}
        total_quantity = 0  # Koguarv
        total_cost = 0  # Kogukulu
        total_orders = orders.count()  # Kogutellimuste arv

        for order_item in orders:
            city_name = order_item.city.name
            category_id = order_item.menu_id.dish_id.category.id  # Saame kategooria ID
            dish_name = order_item.menu_id.dish_id.dish_name
            quantity = order_item.quantity
            dish_price = order_item.menu_id.dish_id.dish_price  # Roa hind
            cost = quantity * dish_price  # Rea summa

            total_quantity += quantity
            total_cost += cost

            if city_name not in city_category_dish_count:
                city_category_dish_count[city_name] = {}
            if category_id not in city_category_dish_count[city_name]:
                city_category_dish_count[city_name][category_id] = {}
            if dish_name not in city_category_dish_count[city_name][category_id]:
                city_category_dish_count[city_name][category_id][dish_name] = {
                    'quantity': 0,
                    'cost': 0
                }

            city_category_dish_count[city_name][category_id][dish_name]['quantity'] += quantity
            city_category_dish_count[city_name][category_id][dish_name]['cost'] += cost

        # Moodustame HTML-tabeli, mis kuvab roogade koguarvu linnade, kategooriate ja roogade kaupa
        message = f"""
        <p>Manuses on kaks CSV faili:</p>
        <ul>
            <li style="color: blue;"> <strong>data.csv</strong> – lähteandmed, mille põhjal kõik edasised arvutused toimuvad.</li>
            <li style="color: green;"><strong>aquaphor-order.csv</strong> – tellimus, mis on rühmitatud roogade > kategooriate > linnade kaupa.</li>
        </ul>
        <table border='1' cellpadding='5' cellspacing='0'>
            <tr>
                <th>Linn</th>
                <th>Kategooria</th>
                <th>Roog</th>
                <th>Kogus</th>
                <th>Hind</th>
                <th>Summa</th>
            </tr>
        """

        # Muutujad eelmise linna ja kategooria salvestamiseks
        previous_city = None
        previous_category = None

        # Sorteerime linnad, kategooriad ja road
        sorted_cities = sorted(city_category_dish_count.keys())
        for city in sorted_cities:
            for category_id in sorted(city_category_dish_count[city].keys()):  # Sorteerime kategooria ID järgi
                category_name = category.objects.get(id=category_id).category_name  # Saame kategooria nime ID järgi
                for dish, data in sorted(city_category_dish_count[city][category_id].items()):  # Sorteerime roogasid tähestiku järjekorras
                    quantity = data['quantity']
                    cost = data['cost']
                    dish_price = cost / quantity  # Arvutame roa hinna

                    # Kontrollime, kas linn on muutunud
                    if city != previous_city:
                        message += f"<tr><td>{city}</td>"
                        previous_city = city
                    else:
                        message += "<tr><td></td>"  # Tühi lahter linna jaoks

                    # Kontrollime, kas kategooria on muutunud
                    if category_name != previous_category:
                        message += f"<td>{category_name}</td>"
                        previous_category = category_name
                    else:
                        message += "<td></td>"  # Tühi lahter kategooria jaoks

                    # Lisame roa, koguse, hinna ja summa
                    message += f"<td>{dish}</td><td style='text-align: center;'>{quantity}</td><td style='text-align: center;'>{dish_price:.2f}</td><td style='text-align: center;'>{cost:.2f}</td></tr>"

        # Lisame üldkokkuvõtte
        message += f"""
        <tr>
            <td colspan='3'><strong>Kokku:</strong></td>
            <td style='text-align: center;'><strong>{total_quantity}</strong></td>
            <td></td>
            <td style='text-align: center;'><strong>{total_cost:.2f}</strong></td>
        </tr>
        """

        message += "</table>"

        # E-kirja saatmine manustega
        subject = f'Aquaphori lõunasöögitellimus {year}. aastal, {week}. nädal, {day}. päev, {total_orders} tellimust'
        from_email = 'sookla@aquaphor.com'  # E-post, kust kiri saadetakse
        to_email = ['ee.it@aquaphor.com']  # Vastuvõtja e-post

        email = EmailMessage(subject, message, from_email, to_email)
        email.attach('data.csv', data_csv_content, 'text/csv')  # Manus lähteandmetega
        email.attach('aquaphor-order.csv', csv_content, 'text/csv')  # Manus detailsete tellimustega
        email.content_subtype = 'html'  # Määrame sisu HTML formaadis
        email.send()

        self.stdout.write(self.style.SUCCESS("Kiri järgmise tööpäeva tellimustega on edukalt saadetud!"))
