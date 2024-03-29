# Generated by Django 3.2.14 on 2023-11-14 13:54

from django.db import migrations, models
import django.db.models.deletion
import postgresqleu.util.fields


class Migration(migrations.Migration):

    dependencies = [
        ('digisign', '0002_contract_dates'),
    ]

    operations = [
        migrations.CreateModel(
            name='DigisignCompletedDocument',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('completedpdf', postgresqleu.util.fields.PdfBinaryField(blank=True, max_length=1000000, verbose_name='Document PDF')),
                ('document', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='digisign.digisigndocument')),
            ],
        ),
    ]
