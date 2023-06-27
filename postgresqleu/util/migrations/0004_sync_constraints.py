from django.db import migrations, transaction
from django.conf import settings

import os


from postgresqleu.util.djangomigrations import scan_constraint_differences


def sync_constraint_names(apps, schema_editor):
    path = os.path.abspath(os.path.join(__file__, '../'))
    with transaction.atomic():
        errors = scan_constraint_differences(path, True)
        if errors:
            # We still commit what we could in case there were handlable errors,
            # but should print them.
            print("THERE WERE ERRORS")
            print("\n".join(errors))
            print("THERE WERE ERRORS")


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0001_initial'),
        ('adyen', '0004_alter_refund_transaction'),
        ('braintreepayment', '0003_decimal_amount'),
        ('confreg', '0097_digisign_contracts'),
        ('confsponsor', '0022_sponsorship_digital_contracts'),
        ('confwiki', '0003_signup_notify'),
        ('countries', '0002_europecountry'),
        ('digisign', '0001_initial'),
        ('elections', '0004_renameopen'),
        ('invoices', '0018_longer_invoice_history'),
        ('mailqueue', '0002_subject_and_time'),
        ('membership', '0008_membermail'),
        ('newsevents', '0004_tweet_news'),
        ('paypal', '0002_payment_refactor'),
        ('plaid', '0001_initial'),
        ('scheduler', '0002_command_unique'),
        ('stripepayment', '0002_stripe_payouts'),
        ('transferwise', '0005_transferwise_monthly_statements'),
        ('trustlypayment', '0004_trustlywithdrawal'),
        ('util', '0003_oauthapps'),
    ]

    operations = [
        migrations.RunPython(
            sync_constraint_names,
        )
    ]
