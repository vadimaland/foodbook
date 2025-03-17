# app/management/commands/send_archived_orders_email.py

import io
import csv
import codecs
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.db.models import Sum, Subquery, OuterRef
from datetime import timedelta
from django.utils import timezone
from app.models import ArchivedOrder, User

class Command(BaseCommand):
    help = "Saadab e-kirja tellimustega, mille eest tuleb tasuda."

    def handle(self, *args, **kwargs):
        # Määrame eelmise kuu alguse ja lõpu
        now = timezone.now()
        first_day_of_current_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
        first_day_of_previous_month = last_day_of_previous_month.replace(day=1)

        # Muutujad tellimuste filtreerimiseks kuupäeva järgi
        start_date = first_day_of_previous_month
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999) - timedelta(days=1)  # last_day_of_previous_month

        # Alampäring kasutaja ees- ja perekonnanime hankimiseks tabelinumbri alusel
        user_subquery = User.objects.filter(
            tabel_number=OuterRef('user_tabel_number')
        ).values('first_name', 'last_name')[:1]

        # Saame kõik arhiveeritud tellimused, lisades alampäringu kasutaja ees- ja perekonnanime hankimiseks
        archived_orders = ArchivedOrder.objects.annotate(
            user_first_name=Subquery(user_subquery.values('first_name')),
            user_last_name=Subquery(user_subquery.values('last_name'))
        ).filter(
            archived_at__gte=start_date,
            archived_at__lte=end_date
        ).order_by('user_tabel_number', 'status')

        # Loome mällu CSV faili detailsete andmete jaoks
        detailed_csv_file = io.StringIO()
        detailed_writer = csv.writer(detailed_csv_file)

        # Pealkirjad CSV-failile detailsete andmete jaoks
        detailed_writer.writerow(['Tellimuse number', 'Tabelinumber', 'Eesnimi', 'Perekonnanimi', 'Roogad', 'Linn', 'Kogusumma', 'Staatus', 'Arhiveerimise kuupäev'])

        # Täidame CSV faili detailsete andmetega
        for order in archived_orders:
            detailed_writer.writerow([
                order.order_number,
                order.user_tabel_number,
                order.user_first_name,  # Eesnimi alampäringust
                order.user_last_name,   # Perekonnanimi alampäringust
                order.dishes,
                order.city_name,
                order.total_amount,
                order.status,           # Staatus lisatud
                order.archived_at
            ])

        # Lisame BOM-i detailsete andmete algusesse
        detailed_csv_content = codecs.BOM_UTF8.decode('utf-8') + detailed_csv_file.getvalue()

        # Koostame CSV faili tabelinumbrite kaupa summaandmetega
        summary_csv_file = io.StringIO()
        summary_writer = csv.writer(summary_csv_file, delimiter=';')

        # Pealkirjad CSV-failile tabelinumbrite kaupa
        summary_writer.writerow(['Tabelinumber', 'Summa', 'Eesnimi', 'Perekonnanimi'])

        # Filtreerime tellimused, jättes alles vaid need, mille staatus on 3 (aegunud)
        filtered_orders = archived_orders.filter(status=3)

        # Rühmitame tellimused tabelinumbrite kaupa ja arvutame summa
        summary_data = filtered_orders.values(
            'user_tabel_number',
            'user_first_name',
            'user_last_name'
        ).annotate(total_amount=Sum('total_amount')).order_by('user_tabel_number')

        # Täidame CSV faili tabelinumbrite kaupa summaandmetega
        for item in summary_data:
            summary_writer.writerow([
                item['user_tabel_number'],  # Tabelinumber
                item['total_amount'],       # Summa
                item['user_first_name'],    # Eesnimi
                item['user_last_name']      # Perekonnanimi
            ])

        # Lisame BOM-i summaandmete algusesse
        summary_csv_content = codecs.BOM_UTF8.decode('utf-8') + summary_csv_file.getvalue()

        # Summeerime tellimuste arvu ja kogusumma
        total_orders = archived_orders.count()
        total_amount = sum(order.total_amount for order in archived_orders)

        # Moodustame sõnumi, mis sisaldab tellimuste koguarvu ja kogusummat
        message = f"""
        <p>
            <span style="color: blue;"><strong>data.csv</strong></span> – fail, mis sisaldab kõiki kasutajate tellimusi eelmisel kuul staatustega "väljastatud" ja "aegunud". See fail esitab täieliku andmekogumi, mille alusel arvutatakse kõik muud näitajad.<br>
            <span style="color: green;"><strong>summary.csv</strong></span> – fail, mis sisaldab kokkuvõtteid tellimustest staatusega "aegunud" samal perioodil. Selles failis on loetletud summad, mida tuleb töötajate palgast maha arvestada, jaotatuna tabelinumbrite kaupa. Kohapeal makstud tellimused on sellest failist välja jäetud. Seda faili kasutatakse summade jaotamiseks palgaarvestustes.
        </p>
        """

        # Arvutame määratud perioodi tellimuste arvu ja kogusumma staatusete kaupa
        status_summary = {}
        for order in archived_orders:
            if order.status not in status_summary:
                status_summary[order.status] = {
                    'count': 0,
                    'total_amount': 0
                }
            status_summary[order.status]['count'] += 1
            status_summary[order.status]['total_amount'] += order.total_amount

        # Lisame staatusete statistika e-kirja kehasse
        message += "<h3>Staatusete statistika</h3>"
        message += "<table border='1' cellpadding='5' cellspacing='0'>"
        message += "<tr><th>Staatus</th><th>Koguarv</th><th>Summa</th></tr>"

        # Sorteerime staatused kasvavas järjekorras
        sorted_statuses = sorted(status_summary.keys())

        for status in sorted_statuses:
            data = status_summary[status]
            message += f"<tr><td>{status}</td><td>{data['count']}</td><td>{data['total_amount']} EUR</td></tr>"

        # Lisame kokkuvõtte rea (kogu tellimuste arv ja kogusumma)
        message += f"<tr><td><strong>Kokku:</strong></td><td><strong>{total_orders}</strong></td><td><strong>{total_amount} EUR</strong></td></tr>"
        message += "</table>"

        # Rühmitame tellimused tabelinumbri, ees- ja perekonnanime ning staatuse alusel
        grouped_orders = {}
        for order in archived_orders:
            key = (order.user_tabel_number, order.user_first_name, order.user_last_name)
            if key not in grouped_orders:
                grouped_orders[key] = {}
            if order.status not in grouped_orders[key]:
                grouped_orders[key][order.status] = {
                    'total_amount': 0,
                    'orders': []
                }
            grouped_orders[key][order.status]['total_amount'] += order.total_amount
            grouped_orders[key][order.status]['orders'].append((order.order_number, order.total_amount))

        # Kaardistame numbrilised staatused tekstilisteks väärtusteks
        STATUS_MAPPING = {
            1: "Väljastatud",
            3: "Aegunud",
        }
        # Kaardistame numbrilised staatused vastavate värvidega
        STATUS_COLORS = {
            1: "green",  # Väljastatud
            3: "red",    # Aegunud
        }

        # Moodustame HTML-tabeli
        message += "<h3>Tellimuste loend</h3>"
        message += "<table border='1' cellpadding='5' cellspacing='0'>"
        message += "<tr><th>Eesnimi Perekonnanimi (Tabelinumber)</th><th>Summa</th></tr>"

        for key, status_data in grouped_orders.items():
            tabel_number, first_name, last_name = key
            
            # Sorteerime staatused kasvavas järjekorras
            sorted_statuses = sorted(status_data.keys())
            
            # Kuvame ees- ja perekonnanime ning tabelinumbri eraldi real sinise taustaga
            message += f"<tr style='background-color: #43a0ff;'><td><strong>{first_name} {last_name} ({tabel_number})</strong></td><td></td></tr>"
            
            # Loetleme tellimuse numbrid ja nende summad samas veerus
            for status in sorted_statuses:
                data = status_data[status]
                status_color = STATUS_COLORS.get(status, "black")  # Saame staatusete värvi
                
                for order_number, total_amount in data['orders']:
                    message += f"<tr style='background-color: #FFFFFF;'><td style='color: {status_color};'>{order_number}</td><td style='text-align: center;'>{total_amount} EUR</td></tr>"
                
                # Kuvame staatusete kaupa kogusumma kohe pärast tellimuste rühma
                total_amount_for_status = sum(order[1] for order in data['orders'])
                status_text = STATUS_MAPPING.get(status, f"Tundmatu staatus {status}")  # Saame staatusete tekstilise väärtuse
                message += f"<tr style='background-color: #FFFFFF;'><td style='color: {status_color}; text-align: right;'><strong>{status_text}</strong></td><td style='color: {status_color};'><strong>{total_amount_for_status} EUR</strong></td></tr>"

        message += "</table>"

        # Saatame e-kirja manusitega
        subject = f'Lõunasöögid kantinis {start_date.strftime("%Y-%m")}'
        from_email = 'sookla@aquaphor.com'  # E-post, kust kiri saadetakse
        to_email = ['ee.it@aquaphor.com']  # Vastuvõtja e-post

        email = EmailMessage(subject, message, from_email, to_email)
        email.attach('data.csv', detailed_csv_content, 'text/csv')  # Manus lähteandmetega
        email.attach(f'summary.csv', summary_csv_content, 'text/csv')  # Manus summaandmetega
        email.content_subtype = 'html'  # Määrame, et sisu on HTML formaadis
        email.send()

        self.stdout.write(self.style.SUCCESS("Maksmiseks mõeldud tellimuste e-kiri saadetud edukalt!"))

        # Salvestame CSV faili SMB jagatud kausta
        file_path = f'/mnt/smb/summary_{start_date.strftime("%Y-%m")}.csv'

        # Kirjutame CSV faili sisu määratud teele
        with open(file_path, 'w', encoding='utf-8-sig') as f:
            f.write(summary_csv_content)

        self.stdout.write(self.style.SUCCESS(f"Fail {file_path} salvestatud edukalt SMB jagatud kausta!"))
