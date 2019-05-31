from .benefitclasses import all_benefits

benefit_choices = [(k, v['description']) for k, v in all_benefits.items()]


def get_benefit_class(benefitid):
    if all_benefits[benefitid]['class'] is None:
        return None

    (mod, cl) = all_benefits[benefitid]['class'].split('.')
    mod = __import__("postgresqleu.confsponsor.benefitclasses.{}".format(mod), fromlist=[cl, ])
    return getattr(mod, cl)
