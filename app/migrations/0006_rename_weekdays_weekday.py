# Generated by Django 4.2.16 on 2024-11-08 12:10

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0005_weekdays'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='weekdays',
            new_name='weekday',
        ),
    ]
