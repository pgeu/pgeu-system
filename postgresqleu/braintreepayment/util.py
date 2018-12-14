import braintree

from django.conf import settings


def initialize_braintree():
    # Set up braintree APIs
    braintree.Configuration.configure(
        settings.BRAINTREE_SANDBOX and braintree.Environment.Sandbox or braintree.Environment.Production,
        settings.BRAINTREE_MERCHANT_ID,
        settings.BRAINTREE_PUBLIC_KEY,
        settings.BRAINTREE_PRIVATE_KEY,
    )
